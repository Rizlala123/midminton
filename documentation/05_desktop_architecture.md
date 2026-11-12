# Phase 1 desktop architecture and implementation handoff

Date: 12 November 2026. Status: authored, independently reviewed at source level, **not executed or compiled**. The [Phase 1 FSD](02_phase_1_scoring_and_video.md) remains the intended product scope. This document distinguishes the current implementation from that target.

## Product decisions

Use Tauri 2 for a native Windows desktop shell, vanilla TypeScript/Vite for the interface, and a separate Python worker for CV and scoring. Tauri uses the operating system webview rather than shipping a separate Chromium runtime. Rust handles native file selection, process management and scoped file access. The vision libraries execute optimized native kernels, so moving their orchestration to Rust would not by itself make inference faster. Electron remains a possible replacement shell without rewriting the Python engine.

No HTTP service, API key, hosted model or paid account is needed. Ollama is not the appropriate engine for locating a tiny shuttle frame by frame; it is deferred to optional Phase 2 narrative summaries. Model inference and recordings stay local. A first-time setup needs internet for free dependencies and weights; operation can be offline afterward.

## Current functional coverage

| Requirement | Current implementation | Remaining acceptance work |
|---|---|---|
| Import a normal recording | Native picker, ffprobe inspection, H.264 proxy at <=1280x720 | Codec/rotation/HDR/audio tests on target Windows PC |
| Singles/doubles | Opening-frame on-court person count suggests 2/4; user confirms type and roster | Perspective/spectator count accuracy; no automatic guarantee |
| Separate players | P1/P2 on A, P3/P4 on B; motion/torso-colour/size association and court-foot gating | Clothing similarity, overlaps and fast movement can cause gaps or ID errors |
| Background people | Outside-court people recorded separately; outsider history and crossing overlap gate roster assignment | Indistinguishable single detections cannot always be resolved from one view |
| Recover after occlusion | Brief ambiguous gaps stay unassigned; >0.8 seconds needs a timed same-ID re-anchor and rerun | Richer learned re-identification is deferred |
| Shuttle tracking | TrackNet heatmap ONNX at its declared cadence; streamed, batch one | Fine-tune/measure on Midminton; no InpaintNet interpolation |
| Rally ends / winner | Motion/rest windows, unknown boundaries, stationary court candidate plus next-serve corroboration | No trained floor/out/net classifier; last point and hidden endings often need manual review |
| Which player hit | Trajectory reversal near a unique observed player box | Proposal only; no racket model or pose/contact classifier |
| Automatic scores | Opt-in experimental corroborated awards; default proposals stay pending | Validate before enabling; lets, pickups and tracking mistakes can mislead heuristics |
| Editable score | Point CRUD, checkpoints, undo/redo, authoritative manual locks | Run deterministic tests and manual acceptance cases |
| Preview/export | Same Python score states and PNG sprites; FFmpeg MP4 and JSON snapshot | Frame transition parity, audio, colour and installer checks |

This is a review-assisted implementation, not a claim that fully automatic Phase 1 is solved. In particular, a shuttle apparently stationary in court is only a terminal hypothesis: its image projection cannot prove floor contact. A next server alone does not prove that the previous rally awarded a point. Opt-in corroborated awards still require human review and remain unlocked until confirmed. No benchmark or accuracy percentage has been measured.

## Modules and contracts

| Module | Responsibilities | Main inputs / outputs |
|---|---|---|
| `src/main.ts` | Video review, calibration/roster drawing, settings, point editor, checkpoints and progress | Rust commands -> project view / score PNG paths |
| `src-tauri/src/main.rs` | Native pickers, opened-project allowlist, one long job, cancellation flag, Python lifecycle | JSON request on stdin; JSON-lines result/progress/error on stdout |
| `python/midminton/worker.py` | Dispatch and view assembly | `create/load/edit/history/prepare/suggest/analyse/export/diagnostics` |
| `scoring.py` | Input validation and deterministic score replay | Editable document -> time-ordered snapshots |
| `store.py` | SQLite transactions, optimistic revisions, history, raw observations, resume cursors | Project directory -> `project.sqlite3` |
| `media.py` | ffprobe, shared tone-map/scale policy, CFR proxy, cancellable FFmpeg | Original video -> `review.mp4`, `review.json` |
| `render.py` | Shared scoreboard PNGs, full export | Reviewed revision -> <=1080p MP4 plus JSON |
| `vision/models.py` | Hash-checked model contracts and ONNX adapters | Local manifest + ONNX -> people/heatmaps |
| `vision/geometry.py` | Four-point homography for feet and court gating | Ordered image corners -> normalized court plane |
| `vision/logic.py` | Roster/noise association, rally/contact/serve proposals | Compact streamed observations -> review events |
| `vision/pipeline.py` | Sequential passes, caching, validation, cancellation/resume and merge | Configured project -> persisted observations/proposals |

Rust commands are not generic shell commands. Paths are passed as separate arguments or JSON. Only native-selected/opened projects and explicitly scoped media/sprite files are exposed to the webview. The content security policy restricts remote resources. `MIDMINTON_PYTHON` is an executable path, not a shell command string. It must point to the installed target-PC interpreter.

Example worker protocol (the desktop normally creates these messages):

```json
{"action":"edit","project":"D:/MidmintonProjects/example","revision":12,"operation":"point","payload":{"id":"rally-15200","time":24.3,"winner":"B","disposition":"point_awarded","timing_origin":"manual_display_anchor"}}
```

```json
{"type":"progress","stage":"shuttle","fraction":0.42,"message":"Temporal shuttle inference; microbatch one"}
```

Stdout is protocol only. Diagnostics/tracebacks go to stderr, whose retained Rust tail is bounded. FFmpeg stderr goes to project logs, with a bounded tail loaded on errors. A cancelled FFmpeg is terminated with a five-second wait then killed if needed. ONNX calls cancel at sequence boundaries; they cannot be interrupted mid-kernel. Closing during a job requests cancellation and keeps the window open; close again once stopped.

## Model preparation and replacement

Start with official YOLOX-tiny, fixed batch one, 416 square, COCO output `[1,N,85]`. Preprocessing is BGR, top-left letterbox with 114 padding and float32 values in 0-255. Set `decoded_boxes` according to the actual exporter option. Other YOLO families have different output/preprocessing contracts and cannot be substituted by renaming the file.

TrackNet uses RGB, 512x288, channels formed from consecutive frames and optionally a median-background frame first, normalized to 0-1. Fixed input is `[1,3*(sequence_length+background_frames),288,512]`; output is `[1,sequence_length,288,512]`. Original RGB and `concat` backgrounds are supported; `subtract` and `subtract_concat` are rejected. Missing observations remain null. The local exporter reads architecture parameters from the checkpoint rather than assuming an eight-frame model.

Every selected manifest declares file, SHA-256, model kind and contract parameters. Weight changes invalidate the checksum until registered again. The FPS field is a validation contract, not a performance dial. The proxy is explicitly resampled to that cadence; changing the shuttle manifest requires preparing it again. Duplicating 30 fps frames to 60 fps cannot recover unrecorded shuttle motion.

To add another model, implement a new adapter returning normalized observed coordinates/boxes, keep visibility and provenance fields, add contract checks and a parity fixture, and update the manifest kind. Keep the scoring/event API unchanged. See the dated handoff for target-PC conversion commands and upstream links.

## Processing and resource strategy

1. Inspect metadata and create the review proxy. Store source path, size and modification time; reject a changed source before prepare, analysis or export. This is a cheap integrity check, not a cryptographic source-video proof.
2. Mark four full-court corners in order: near-left, near-right, far-right, far-left. Suggested roster uses feet inside this area. Confirm P1/P3 for singles or P1/P2/P3/P4 for doubles. A/B stay team identities even after end changes.
3. Run person inference on CPU at roughly 10 Hz; track identities and save compact boxes/visibility/noise. Timed re-anchors reset uncertain identities during this pass. Release that model session.
4. Load only the shuttle session; optionally use CUDA with a roughly 3 GB allocator limit. Hold at most one temporal sequence (<=16 proxy frames), a 32-frame reduced background sample, and small write chunks. There is no whole-match decoded-frame array or extracted JPEG directory.
5. Write shuttle observations in roughly five-second batches. Save the last committed sequence cursor. Rerun resumes this stage at that frame after validating cadence; interrupted person passes restart. Decode-open and coverage checks reject empty/truncated passes. Cache identity includes media metadata, model contracts, court, anchors, options and pipeline version.
6. Join compact observations, propose contacts and rallies, reject stale settings, replace unlocked model events and preserve reviewed/manual events and deletion windows. Persist analysis report and compact raw evidence. Undo/redo affects the editable document, not raw observations.
7. Derive score snapshots and PNGs from the reviewed revision. Use those same snapshots for preview and export. Export starts from the original source, shares tone mapping, preserves relative audio offset, scales to <=1920x1080, writes a partial output and renames after success.

The RTX 3050 / 16 GB machine is the design target, **not a measured minimum or guaranteed real-time result**. ORT's allocator limit does not cap all GPU/driver/webview memory. CUDA OOM must be handled by retrying with CPU or a validated smaller temporal model; no silent provider switch is promised. H.264 software export uses CPU and can be slower than inference. Duration, resolution, disk bandwidth and model length govern runtime.

Disk usage is dominated by the proxy and exported video. Revision PNG folders and historical observation runs are retained for traceability and can accumulate; automatic cache cleanup is not implemented. Do not delete the active project's database/WAL files while open. For backup/transfer, close the app first and copy the whole project folder plus the original recording and models. Absolute paths currently require preserving their locations or importing a new project; a relink wizard is deferred.

## Correction example

At 30 seconds A wins; at 45 seconds B wins. The displayed score is 1-1. Insert a missed A point at 38 seconds: replay becomes A at 30 -> 1-0, A at 38 -> 2-0, B at 45 -> 2-1. No later point records need manual renumbering.

If an obscured rally at 38 seconds is pending, later known awards are retained but the displayed score remains the last trusted score with a **Provisional** label. Resolve the gap or add a trusted checkpoint, for example 2-1 at 46 seconds. A checkpoint restores score certainty from its timestamp without inventing missing shots or an exact hidden ending. Earlier corrections replay up to it; a conflicting explicit checkpoint remains authoritative and raises a conflict notice.

A replay/no-point event awards neither side. Manually confirming an AI candidate locks its ID and preserves start/end-window/evidence metadata. Reanalysis replaces superseded unlocked windows and reconciles overlapping reviewed/deleted windows conservatively. A mistakenly merged/split rally still needs manual inspection; this is not a learned stable-rally identity model.

Point `time` is a scoreboard display anchor; `end_time` and `end_window` represent physical-boundary knowledge separately. A point at the exact media duration has no visible exported frame and is rejected; the UI's “Use video time” selects a visible time 0.1 seconds before the end when necessary. Final unknown candidates remain reviewable. Same-timestamp points have stable ID ordering and checkpoints apply afterward.

## Handoff and known gaps

- No model weights, dependency installs, builds, tests, UI launch or inference were performed on this PC. Source review is not runtime verification.
- No package locks were invented. Resolve and commit npm/Cargo locks on the testing PC; record Python and CUDA dependency versions and model SHA-256 values.
- Desktop source and NSIS configuration are included. Python/FFmpeg/CUDA are external prerequisites, not bundled redistributables. Author the icon using the supplied target-PC helper before the first build.
- Static camera and opening-frame calibration only. Split recordings with camera cuts/movement into separate projects. Rotation metadata, unusual SAR and HDR require manual parity checks; no camera-cut detector is included.
- No reliable automated line judging, net-fault classification, let/fault reasoning, racket detection, learned hitter classifier, learned re-identification, or multi-camera triangulation.
- Contacts can be missed (including straight trajectory contacts) or spurious; court projection is valid for grounded feet and only hypothetical for a stationary shuttle. High-speed blur and YouTube compression cannot be reversed by the software.
- Marking boxes currently requires a pointer; buttons/forms have labels, keyboard focus and status messages, but a full accessibility audit is pending.
- No true live-camera capture, match-name management, custom player names, shot classes, heatmaps or Phase 2 performance advice yet.

Runtime acceptance is specified in [the timestamped testing package](../testing/2026-11-12_13-15-49_IST/README.md). Do not promote this first commit to a tested release until those results are recorded.
