# Phase 1 desktop implementation plan

Date: 12 November 2026. Basis: [Phase 1 specification](02_phase_1_scoring_and_video.md).

## Decisions and constraints

- Tauri 2 (Rust shell/system webview), TypeScript interface, Python 3.11+ worker.
- Native file selection; explicitly scoped local media; no web server or cloud inference.
- This PC is AUTHORING ONLY. Do not install dependencies, run tests, compile, launch the app or execute inference here. Write tests for execution on the other PC. Static source review and Git/file inspection are allowed.
- The user authorises a local commit of all authored code, existing specifications and testing instructions. No remote/push.
- This is an unborn repository with only user-approved documentation; implement in this project folder rather than relocating those files to a separate checkout. No existing feature code is present.
- No model weights/video inputs/secrets committed. Model adapters require explicit local files and validate their contracts. Manual scoring works without models.
- Use specialist CV for analysis; Ollama is deferred to Phase 2.

## Interfaces

Rust invokes `python -m midminton.worker` with one JSON request on stdin. Stdout is newline-delimited `progress`, `result` or `error` JSON only. Rust emits `worker-message` events for long jobs; short commands return JSON. Model/runtime diagnostics go to stderr. No shell interpolation.

Project data uses SQLite transactions. The small editable document contains rules, calibration/roster anchors, points/checkpoints and settings. Raw observations and job cursors live separately. Manual locks survive AI merges. Score snapshots are derived in Python for both UI and export.

## Tasks

1. Author tests first for score replay, correction propagation, checkpoints, no-point rallies, undo/redo, scope/identity and chunk idempotence. Execution deferred by user instruction.
2. Implement standard-library event/store/worker contracts and bounded media/export operations.
3. Implement YOLOX ONNX person adapter, persistent manually confirmable roster, spectator/occlusion flags, temporal shuttle adapter and conservative rally/contact proposals. Preserve unknown results. Sequential, cached passes; cancellation/resume and stale-run rejection.
4. Implement Rust native picker, scoped asset protocol, worker lifecycle and progress/cancel routing.
5. Implement video import/open, configuration, court/roster picking, analysis progress, event editing/checkpoints/undo, video overlay and export.
6. Create dated remote-PC setup, model preparation, unit/manual/AI validation and acceptance instructions. Record not-run status explicitly.
7. Obtain independent static source review, fix actionable issues, inspect staged contents and commit locally. Do not claim tests pass.

## Review focus

- Unknown points must taint later scores; checkpoints restore certainty without inventing contacts.
- A spectator cannot acquire an established player's identity; long gaps remain missing.
- Model/geometry changes invalidate caches; resuming never duplicates points.
- Edits and inference cannot overwrite each other's committed changes.
- Unicode/spaced media paths, bounded frame buffers, cancellation and partial exports.

## Progress

Implementation and review status is recorded in changes.md and the dated testing handoff. All runtime verification is deferred to the target PC.
