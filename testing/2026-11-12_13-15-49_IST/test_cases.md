# Phase 1 acceptance cases — target PC only

Date: 12 November 2026. Initial status of every case: **NOT RUN**. No test footage or measured results are included in this commit. Record actual outcomes in [the results template](results_template.md).

## Gate A: automated and packaging checks

After [setup](requirements.md), run the supplied `run_checks.ps1 -ConfirmTargetMachine`. It installs nothing and stops on a nonzero command result. Unit tests cover score correction, pending/checkpoint behavior, replay exclusion, deuce/cap, doubles service uncertainty, validation, revision checks, history forks, lock/tombstone reconciliation, observation upserts, geometry, source changes and conservative vision rules. These are authored cases; their existence does not mean they pass.

Then run `npm run desktop` and, separately, `npm run desktop:build`. Check startup in both debug and installed NSIS builds. A Rust `cargo check` alone does not prove the packaged Python source/resource path works. Try a project path and interpreter path with spaces and Unicode. Verify Check setup reports the chosen interpreter, FFmpeg/ffprobe and expected packages. Deliberately remove/change the interpreter path and confirm the app gives a useful error.

## Gate B: manual scoring with no models

Use a short known video first. Keep CUDA and auto-awards off. Select video, prepare proxy and save a project location shown in the sidebar. Existing recordings must remain byte-identical; use a hash before/after if needed on this PC.

| ID | Action | Expected result |
|---|---|---|
| S01 | Add A at 10 s and B at 30 s | 0-0 before 10, 1-0 from 10, 1-1 from 30 |
| S02 | Insert missed A point at 20 s | Later score becomes 2-1 without editing the 30 s event |
| S03 | Change the 20 s point to B | Score at 30 becomes 1-2; earlier times unchanged |
| S04 | Delete the 20 s point | Score at 30 returns to 1-1; Delete remains enabled after loading and edits |
| S05 | Add pending point at 15 s | Later display shows last trusted 1-0 plus Provisional; later known awards remain stored |
| S06 | Add checkpoint at 35 s: A=2, B=1, server A, game 1 | Display certainty resumes at 35; missing physical contact/ending stays unknown |
| S07 | Correct an earlier point across an existing conflicting checkpoint | Checkpoint remains authoritative and conflict notice is visible |
| S08 | Change pending point to replay/no point | Neither score increments for that event |
| S09 | Undo, redo; undo then add a new point | State restores correctly; new edit forks history and old redo branch is unavailable |
| S10 | Start 20-20; award A twice | 21-20 is unfinished; 22-20 completes the game |
| S11 | Start 29-29; award B | Game ends at 29-30 |
| S12 | Add another award after game completion | New game starts; doubles serving player remains unknown rather than fabricated |
| S13 | Try fractional/negative scores, NaN via direct worker request, bad/duplicate IDs, invalid court corners | Input rejected with an error; prior committed state remains intact |
| S14 | Add multiple points at one timestamp | Deterministic ID order; a same-time checkpoint applies after points |
| S15 | Seek to end; use video time for a final award | Anchor is visible (0.1 s before end); manually typing exact duration is rejected |
| S16 | Close and reopen `project.sqlite3` | Score revision, settings, points, locks and history persist |

For hidden endings, distinguish the **display anchor** you choose from the unknown physical end window. Confirming a proposed winner must preserve its existing start/end-window/evidence metadata. Checkpoints use the same visible-time policy; setting one at playback end selects a display anchor 0.1 seconds before the end.

## Gate C: media and export

| ID | Input / action | Expected result / evidence |
|---|---|---|
| V01 | Ordinary 1080p landscape MP4, 30 fps, with audio | Proxy plays; original duration preserved within encoder/frame tolerance |
| V02 | 25/50/60 fps or variable-rate phone recording | Proxy becomes the selected model cadence; source-time events remain correct; compare beginning/middle/end |
| V03 | Silent video | Prepare and export succeed without inventing audio |
| V04 | Recording with measurable positive/negative audio offset | Preserve relative A/V alignment at start/middle/end; record ffprobe stream timestamps |
| V05 | HDR phone clip | Proxy and export both tone-map sensibly; HDR-capable FFmpeg build required |
| V06 | Portrait/rotation metadata, non-square pixels, odd dimensions | Verify orientation, corners and score placement manually; treat a mismatch as a release blocker for that format |
| V07 | Path contains spaces and non-ASCII characters | Picker, probe, model manifests, proxy, project reload and export work |
| V08 | Cancel proxy, analysis and export at different stages | UI remains usable; original intact; no completed MP4 falsely reported; export partial file removed |
| V09 | Close window during a job | Requests cancellation, keeps window open; close after stopping; no orphan worker/FFmpeg remains |
| V10 | Replace/modify source after import | Prepare/analyse/export reject it; open a new project for changed footage |
| V11 | Invalid/truncated proxy or corrupted model/checksum | Useful error; never report an empty/partial successful analysis |
| V12 | Run a second long job while one runs | Reject it; no simultaneous models/exports competing for resources |
| V13 | Export a reviewed revision with rapid score changes and same-time events | Compare frames just before/at/after each change against timeline; transitions within one output frame |
| V14 | Export last point and pending/replay/checkpoint states | Exported labels and scores match reviewed state, including visible final award and provisional label |
| V15 | Export 4K source | Output maximum 1920x1080 with even dimensions, original preserved, no crushed/washed-out HDR colours |

Record export revision from its adjacent JSON. Check duration, codec, audio tracks and dimensions with ffprobe. Compare audible racket/contact sync where visible; audio from other courts is not a rally truth source. Exporting is software H.264; elapsed export time is separate from model inference time. Existing export filenames are revision-specific; rerunning the same revision replaces its previous output, so copy a retained comparison export first.

## Gate D: models and real badminton footage

Prepare known-good local manifests. Validate ONNX/PyTorch heatmap parity for the same tensor, then inspect actual app preprocessing/detections on a short known rally. Tiny floating-point differences are expected; gross coordinate/preprocessing differences are not. Record model hashes, upstream commits and providers. The app's example manifests are not executable models.

Use original Midminton recordings where possible, not downloaded/transcoded YouTube copies. Prior reference videos in the FSD include [XaOaKURxe3s](https://www.youtube.com/watch?v=XaOaKURxe3s), [8ztbAE8YBqA](https://www.youtube.com/watch?v=8ztbAE8YBqA) and [UgrUFtS4vl8](https://www.youtube.com/watch?v=UgrUFtS4vl8). Ownership establishes access permission; it does not establish model accuracy. This implementation has not analysed them.

For a 30-60 second excerpt, manually label actual roster IDs, visible shuttle centers, contact times/hitters, rally boundaries, awarded winner/let and obstruction intervals. Annotate uncertainty explicitly. Include normal rallies, fast smashes, out shots, net shots, a final rally without a next serve and a replay. Expand to at least one singles and one doubles recording, then complete 8-13 minute videos.

| ID | Scenario | Required behavior |
|---|---|---|
| A01 | Clear singles opening frame, no extra on-court people | Suggest P1/P3 and singles; user can correct |
| A02 | Clear doubles opening frame | Suggest two players per side; retain P1/P2/P3/P4 identities after confirmation |
| A03 | Spectators in background or adjacent court | Remain background/unknown; do not increase roster to six or reassign IDs |
| A04 | Normal-size spectator walks across/onto court | Record noise; ambiguous IDs/hitters remain unassigned; verify no observed ID takeover |
| A05 | Foreground spectator covers most of camera | Freeze uncertain identities; mark contaminated candidates; do not award from disappearance |
| A06 | Player steps outside boundary to retrieve shuttle | Previously tracked continuity is preferred; not permanently reclassified as a new spectator |
| A07 | >0.8 s occlusion or identity loss | Show gap; draw same ID at recovery timestamp, save and reanalyse; earlier anchors remain |
| A08 | Two similar shirts overlap | Prefer unknown over confident swap; record any false swap as failure requiring improvement |
| A09 | Shuttle disappears behind player / leaves frame | No automatic award solely because it disappears |
| A10 | Resting shuttle followed by next serve | Suggest winner only when corroboration agrees; keep awards pending by default |
| A11 | Enable experimental awards after baseline measurement | Awards stay unlocked and reversible; compare every award with truth; hidden/contaminated cases stay reviewable |
| A12 | Next serve after a let/replay | Must not treat serve alone as proof; manually label let; report any false auto-award |
| A13 | Final rally with no next serve | Remains uncertain unless manually confirmed; final score can be exported visibly |
| A14 | Straight shot contact / smash blur | Misses remain measurable; no claim that reversal-only detection finds every hit |
| A15 | Cancel during shuttle pass and rerun | Resume from committed cursor without duplicate observations/points; short person pass may restart |
| A16 | Review a proposed point, shift display time, rerun with changed boundary | Keep manual lock and evidence; no duplicate overlapping rally |
| A17 | Delete a proposal, then rerun with shifted model ID | Keep deletion window; do not resurrect it under a new nearby ID |
| A18 | Change court/model/roster while reprocessing | Cache invalidated; stale settings cannot overwrite newer project choices |
| A19 | Camera movement/cut or switched court | Split into separate projects; do not claim reliable automatic camera-change support |

Automatic winner inference is experimental and opt-in. Even with corroboration it can confuse shuttle pickup/lets/rest with a terminal event. Do not certify automatic mode by testing only rallies on which the model already succeeded. Keep a held-out clip that was not used to tune thresholds.

## Metrics and performance record

- Shuttle: visible-frame recall and false detections, normalized pixel error, longest missed interval; label occluded frames separately.
- Roster: observed ID switches and identity coverage, especially near crossings; report missing periods rather than counting frozen boxes as correct tracking.
- Contacts: precision/recall within a declared timing tolerance (start with ±0.15 s), correct hitter rate, unknown rate and false confident hitter assignments.
- Rallies: count precision/recall, boundary-time error for observable endings, unresolved-boundary rate. Report merged/split windows.
- Winners: precision of auto-awarded subset **and** automatic coverage; unresolved rate. A conservative system cannot claim 100% whole-match accuracy from two correct awards and 40 pending points.
- Score: raw inferred sequence accuracy and fully reviewed/exported sequence accuracy separately. Fully reviewed score should match ground truth at every event/checkpoint.
- Resources: Task Manager peak process-tree RAM, dedicated GPU memory, wall time for proxy/people/shuttle/export separately, source/proxy/output sizes, observation DB size, and cancel latency. Include Python/FFmpeg/webview processes, not just Rust's process.

Design goals to evaluate: keep application process-tree RAM comfortably within 16 GB, GPU session budget within the 4 GB device, and avoid storage proportional to decoded full-frame count. A suggested initial acceptance ceiling is <=8 GB app-tree RAM and <=3.5 GB dedicated VRAM including overhead, but these are **unmeasured goals**, not guarantees. Record elapsed time per video minute; set a throughput target after the first measurements rather than inventing a “real-time” claim.

A ready-to-use **manual review/export workflow** requires gates A-C to pass. A useful **assisted analysis workflow** additionally requires D with known error/unknown rates. Fully automatic scoring is not accepted until false auto-awards, lets and spectator cases meet Riz's agreed accuracy/coverage target on held-out recordings.
