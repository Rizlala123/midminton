"""Explicit ONNX contracts. Never download or silently replace a user's model."""
from pathlib import Path
import hashlib
import json


def descriptor(path, expected):
    manifest_path = Path(path).resolve(strict=True)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("kind") != expected:
        raise ValueError(f"Expected {expected} model manifest")
    model = (manifest_path.parent / data["file"]).resolve(strict=True)
    digest = hashlib.sha256()
    with model.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != data.get("sha256"):
        raise ValueError(f"Model checksum differs from manifest: {model.name}")
    return data, model


def session(path, gpu=False):
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    available = ort.get_available_providers()
    if gpu and "CUDAExecutionProvider" not in available:
        raise ValueError("CUDA provider unavailable. Install the GPU runtime/dependencies or select CPU explicitly")
    providers = [("CUDAExecutionProvider", {"gpu_mem_limit": 3000 * 1024 * 1024,
                                          "arena_extend_strategy": "kSameAsRequested"})] if gpu else []
    return ort.InferenceSession(str(path), sess_options=options, providers=providers + ["CPUExecutionProvider"])


class People:
    def __init__(self, manifest):
        self.config, path = descriptor(manifest, "yolox")
        self.model = session(path, gpu=False)

    def detect(self, image):
        import cv2
        import numpy as np
        height, width = image.shape[:2]
        size = int(self.config.get("size", 416))
        ratio = min(size / height, size / width)
        resized = cv2.resize(image, (int(width * ratio), int(height * ratio)))
        padded = np.full((size, size, 3), 114, dtype=np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        tensor = padded.transpose(2, 0, 1)[None].astype(np.float32)
        prediction = self.model.run(None, {self.model.get_inputs()[0].name: tensor})[0]
        if prediction.ndim != 3 or prediction.shape[2] != 85:
            raise ValueError("YOLOX output must be [1,N,85] COCO format")
        values = prediction[0].copy()
        if not self.config.get("decoded_boxes", False):
            grids, strides = [], []
            for stride in (8, 16, 32):
                yy, xx = np.meshgrid(np.arange(size // stride), np.arange(size // stride), indexing="ij")
                grids.append(np.stack([xx, yy], -1).reshape(-1, 2))
                strides.append(np.full((len(grids[-1]), 1), stride))
            grid, scale = np.concatenate(grids), np.concatenate(strides)
            if len(values) != len(grid):
                raise ValueError("YOLOX grid size does not match manifest")
            values[:, :2] = (values[:, :2] + grid) * scale
            values[:, 2:4] = np.exp(np.clip(values[:, 2:4], -20, 20)) * scale
        boxes, scores = [], []
        for row in values:
            confidence = float(row[4] * row[5])
            if confidence < 0.35:
                continue
            cx, cy, bw, bh = row[:4] / ratio
            boxes.append([float(cx-bw/2), float(cy-bh/2), float(bw), float(bh)])
            scores.append(confidence)
        selected = cv2.dnn.NMSBoxes(boxes, scores, 0.35, 0.45)
        detections = []
        for index in np.asarray(selected).reshape(-1):
            x, y, bw, bh = boxes[int(index)]
            x1, y1 = max(0, int(x)), max(0, int(y))
            x2, y2 = min(width, int(x+bw)), min(height, int(y+bh))
            if x2 <= x1 or y2 <= y1:
                continue
            torso = image[y1+int((y2-y1)*0.25):y1+int((y2-y1)*0.65), x1:x2]
            appearance = np.median(torso.reshape(-1, 3), axis=0).tolist() if torso.size else [0, 0, 0]
            detections.append(dict(box=[x1/width, y1/height, x2/width, y2/height],
                                   confidence=scores[int(index)], appearance=appearance))
        return detections


class Shuttle:
    def __init__(self, manifest, gpu):
        self.config, path = descriptor(manifest, "tracknetv3")
        if self.config.get("bg_mode", "") not in {"", "concat"}:
            raise ValueError("Only RGB and RGB+median TrackNet contracts are supported")
        self.length = int(self.config["sequence_length"])
        if not 1 <= self.length <= 16:
            raise ValueError("Invalid temporal sequence length")
        self.model = session(path, gpu=gpu)

    def detect(self, frames, background=None):
        import cv2
        import numpy as np
        rgb = [cv2.cvtColor(cv2.resize(f, (512, 288)), cv2.COLOR_BGR2RGB).transpose(2, 0, 1) for f in frames]
        if self.config.get("bg_mode") == "concat":
            if background is None:
                raise ValueError("TrackNet concat model needs a median background")
            rgb.insert(0, background.transpose(2, 0, 1))
        tensor = np.concatenate(rgb, axis=0)[None].astype(np.float32) / 255.0
        output = self.model.run(None, {self.model.get_inputs()[0].name: tensor})[0]
        if output.shape != (1, self.length, 288, 512):
            raise ValueError("TrackNet output contract must be [1,sequence,288,512]")
        return [heatmap_observation(heatmap) for heatmap in output[0]]


def heatmap_observation(heatmap):
    import cv2
    import numpy as np
    mask = (heatmap > 0.5).astype(np.uint8)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    if count <= 1:
        return None
    best = 1+int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y = centers[best]
    confidence = float(heatmap[labels == best].max())
    return {"xy": [float(x/512), float(y/288)], "confidence": confidence, "visibility": "observed"}
