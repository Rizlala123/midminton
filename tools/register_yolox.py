"""TARGET PC ONLY: validate static YOLOX ONNX dimensions and register its checksum."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--size", type=int, choices=[416, 640], default=416)
    parser.add_argument("--decoded-boxes", action="store_true", help="Set only for an export using --decode_in_inference")
    args = parser.parse_args()
    import onnxruntime as ort
    path = args.model.resolve(strict=True)
    manifest = path.with_suffix(".json")
    if manifest.exists():
        raise ValueError("Manifest already exists; choose a new model name to preserve provenance")
    model = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    if model.get_inputs()[0].shape != [1, 3, args.size, args.size]:
        raise ValueError("Export a fixed batch-one square YOLOX model matching --size")
    shape = model.get_outputs()[0].shape
    if len(shape) != 3 or shape[0] != 1 or shape[-1] != 85:
        raise ValueError("Expected COCO YOLOX output [1,N,85]")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest.write_text(json.dumps({"kind": "yolox", "file": path.name, "sha256": digest,
        "size": args.size, "decoded_boxes": args.decoded_boxes,
        "source": "https://github.com/Megvii-BaseDetection/YOLOX", "license": "Apache-2.0"}, indent=2)+"\n", encoding="utf-8")
    print(f"Created {manifest}; verify boxes on a known photograph before analysis.")


if __name__ == "__main__":
    main()
