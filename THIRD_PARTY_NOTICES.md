# Third-party sources and model contracts

Date: 12 November 2026. No upstream model code or weights are redistributed in this source tree. The adapters and export helpers are newly authored integration code. Keep notices supplied with anything downloaded or bundled later.

| Component | Purpose / source | Licence note |
|---|---|---|
| Tauri 2 / dialog plugin | [Tauri](https://v2.tauri.app/) desktop shell and native picker | MIT / Apache-2.0; retain resolved dependency notices |
| YOLOX | [Official repository](https://github.com/Megvii-BaseDetection/YOLOX), [ONNX exporter](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/tools/export_onnx.py) | Apache-2.0; acquire official weights separately |
| TrackNetV3 | [Official model](https://github.com/qaz812345/TrackNetV3/blob/master/model.py), [dataset preprocessing](https://github.com/qaz812345/TrackNetV3/blob/master/dataset.py), [checkpoint instructions](https://github.com/qaz812345/TrackNetV3#inference) | [Upstream MIT licence](https://github.com/qaz812345/TrackNetV3/blob/master/LICENSE) explicitly includes pretrained checkpoints; retain it with local copies |
| ONNX Runtime | [Official documentation](https://onnxruntime.ai/docs/) | MIT; GPU dependency versions must match the provider matrix |
| FFmpeg | [Official download](https://ffmpeg.org/download.html) and [legal page](https://ffmpeg.org/legal.html) | Licence depends on build options; libx264-enabled builds may be GPL. Free use does not remove redistribution obligations |
| OpenCV, NumPy, Pillow, SQLite, Python, TypeScript, Vite | Runtime/build dependencies | Retain their resolved notices before distributing an installer |

TrackNet integration here implements the heatmap network only. It does **not** claim upstream InpaintNet rectification or upstream published accuracy. Missing shuttle observations stay missing. Do not replace this with a generic object detector and assume identical temporal performance.

The original `KiranYelisetti/badminton-ai-analysis` review found a design-only README at inspected commit `b5cc40b4`; no runnable application was copied from it. Earlier candidate repositories are research references in the FSD, not imported dependencies.

The main application's repository includes Riz's [MIT licence](LICENSE), retained from the GitHub initial commit during integration on 20 November 2026. Dependency and model licences remain separate. There are no subscription or inference charges in this implementation; initial dependency/weight downloads require internet access on the target PC.
