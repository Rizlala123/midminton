"""TARGET PC ONLY: convert an official local TrackNet checkpoint to this adapter's ONNX contract."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Trusted upstream TrackNetV3 checkout containing model.py")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=int, choices=[25, 30, 50, 60], default=30,
                        help="Cadence validated for these weights; do not change merely to claim better tracking")
    args = parser.parse_args()
    import torch
    module_path = args.source.resolve(strict=True)/"model.py"
    spec = importlib.util.spec_from_file_location("trusted_tracknet_model", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checkpoint = torch.load(args.checkpoint.resolve(strict=True), map_location="cpu", weights_only=True)
    params = checkpoint["param_dict"]
    length, mode = int(params["seq_len"]), params["bg_mode"]
    if mode not in {"", "concat"} or not 1 <= length <= 16:
        raise ValueError("Unsupported checkpoint: use original RGB or median-concat TrackNet weights")
    channels = 3*(length+(1 if mode == "concat" else 0))
    model = module.TrackNet(in_dim=channels, out_dim=length).eval()
    model.load_state_dict(checkpoint["model"], strict=True)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(".json").exists():
        raise ValueError("Choose a new output name; existing models/manifests are preserved")
    with torch.inference_mode():
        torch.onnx.export(model, torch.zeros(1, channels, 288, 512), str(output),
                          input_names=["frames"], output_names=["heatmaps"], opset_version=17, dynamo=False)
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    output.with_suffix(".json").write_text(json.dumps({"kind": "tracknetv3", "file": output.name,
        "sha256": digest, "sequence_length": length, "bg_mode": mode, "fps": args.fps,
        "source": "https://github.com/qaz812345/TrackNetV3", "license": "MIT",
        "inpainting": False}, indent=2)+"\n", encoding="utf-8")
    print(f"Created {output} and {output.with_suffix('.json')}. Validate ONNX/PyTorch parity before use.")


if __name__ == "__main__":
    main()
