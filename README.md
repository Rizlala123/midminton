# Midminton Studio

Local Windows desktop application for reviewing recorded badminton matches. Phase 1 combines a Rust/Tauri shell, a TypeScript interface and a Python computer-vision worker. There is no paid API, cloud inference or mandatory Ollama dependency.

**Status: first authored implementation, not compiled or executed.** Per Riz's instruction, this PC is authoring only. All build, runtime, model and performance checks must happen on the other PC using [the dated testing handoff](testing/2026-11-12_13-15-49_IST/README.md). Do not treat this commit as a tested release or a claim of automatic scoring accuracy.

## What is included

- Native local-video/project selection; H.264 review proxy; local progress and cancellation.
- Court marking, singles/doubles roster suggestion, manual player confirmation and timed identity re-anchors.
- Sequential YOLOX person and temporal TrackNet ONNX passes with bounded frame buffers and SQLite observation caches.
- Experimental rally, hitter and winner proposals. Uncertain points remain pending. Automatic awards are **off by default** and require two corroborating heuristics when enabled.
- Seekable score overlay; add/edit/delete points at any time; trusted score checkpoints; undo/redo; downstream score replay; manual locks and deletion tombstones.
- MP4 score export from the original recording (maximum 1080p), original audio timing offset and a JSON document snapshot. Original files are preserved.

The first vision implementation requires a static, whole-court camera view. It does not robustly classify every floor/out/net fault, guarantee identity through indistinguishable crossings, or provide trained rally-end/winner accuracy. Long player gaps need a timed manual re-anchor and reanalysis. Shot classification, names and detailed match analytics remain Phase 2.

## Read next

- [Architecture, functionality and actual limitations](documentation/05_desktop_architecture.md)
- [Original Phase 1 FSD](documentation/02_phase_1_scoring_and_video.md)
- [Overall FSD](documentation/01_overall_specification.md) and [Phase 2 FSD](documentation/03_phase_2_shots_and_analytics.md)
- [PDF specification](documentation/Midminton_Application_Specification_v1.pdf)
- [Implementation plan](documentation/04_phase_1_implementation_plan.md)
- [Target-PC setup and model preparation](testing/2026-11-12_13-15-49_IST/requirements.md)
- [Detailed acceptance cases](testing/2026-11-12_13-15-49_IST/test_cases.md)
- [Dependency/model source notes](THIRD_PARTY_NOTICES.md)

## Layout

```text
src/                     TypeScript desktop interface
src-tauri/               Rust native shell, IPC and file scopes
python/midminton/        Python scoring, storage, media and vision
python/tests/            Authored tests; not run on this PC
models/                  Manifest examples only; no model weights
tools/                   Target-PC model registration/export and icon authoring
documentation/           All FSDs and architecture handoffs
testing/<date_time>/     Target-PC testing instructions and result templates
```

For target-PC development, install the prerequisites, create `.venv`, install `python[vision,export,test]`, run `tools/prepare_icons.py`, install npm dependencies and use `npm run desktop`. Full commands and the GPU alternative are in the handoff. The Rust shell launches the interpreter selected by `MIDMINTON_PYTHON`; a production installer still requires that local Python environment and FFmpeg. It is not yet a self-contained Python/CUDA installer.

No dependency resolution was performed here, so `package-lock.json` and `Cargo.lock` must be generated and checked on the target PC, then committed. They are intentionally not fabricated. Model weights, recordings, environments, databases, caches, build outputs and secrets are excluded from Git.
