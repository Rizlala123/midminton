# Phase 1 source review record

Date: 12 November 2026. Review method: direct source reading by implementer and an independent reviewer. No tests, compilation, imports of application code, dependency installation, UI launch, model execution or benchmarks occurred on the authoring PC.

## Findings addressed in source

| Finding | Authored change | Runtime status |
|---|---|---|
| Reanalysis could duplicate shifted/reviewed rallies | Replace unlocked model windows; reconcile reviewed/deleted intervals; preserve existing event evidence | Not run |
| Spectator could acquire nearby player identity | Court-foot gating, outsider continuity, overlap/appearance/size ambiguity gates | Not run; single-view ambiguity remains |
| Long identity gaps could not recover | Timed manual same-ID re-anchors and rerun path | Not run |
| Established players outside court became background | Prefer continuing tracked identity before outside-court classification | Not run |
| Model cadence was only relabeled | CFR proxy preparation, manifest/metadata cadence checks and frame-index resume | Not run |
| Decoder failure looked like successful EOF | Capture-open and decoded-duration coverage checks | Not run |
| Cancellation waited for FFmpeg stdout | Independent polling, terminate/kill boundary; close requests cancel active job | Not run |
| Audio/video origins reset independently | Retain stream offset; canonical video duration excludes an audio tail | Not run; verify offsets and formats |
| Export processing differed from preview | Shared HDR/scale filters, <=1080p export | Not run |
| Final points/checkpoints were outside visible export | Reject exact-duration anchors; choose a visible UI anchor | Not run |
| Doubles server fabricated after game/checkpoint | Explicit serving-player uncertainty | Not run |
| Delete buttons remained disabled | Include dynamic buttons in project/busy control updates | Not run |
| Hitter proposals were not visible | Seekable contact list in the sidebar | Not run |
| Stale hold/terminal facts could corroborate a later serve | Reset evidence on motion/gaps/noise/lost holder | Not run |
| Selected heatmap component used another pixel's confidence | Compute confidence within the chosen component | Not run |
| Source could change under old analysis | Live size/mtime validation before processing/export | Not run; not a cryptographic video hash |
| Error path loaded whole FFmpeg log | Seek/read bounded log tail | Not run |

The review found no definite Rust API/signature blocker by inspection. This is **not** compilation evidence. Third-party dependency resolution, generated icons, resource bundling and NSIS installation remain target-PC checks.

Twenty-nine unit test functions were authored across six files, covering score/state/storage/geometry/media and selected pure vision rules. Their results are unknown. The [timestamped test package](../testing/2026-11-12_13-15-49_IST/README.md) contains commands, prerequisites, manual cases and a NOT RUN result template.

## Remaining product limitations

The strongest remaining risk is model/heuristic accuracy on Midminton's footage. No learned floor/out/net classifier, robust learned identity recovery or ground-truth winner dataset is provided. Automatic awards remain opt-in and heuristic, missing shuttle observations stay missing, and manual decisions are authoritative. Camera cuts require separate projects. Python/FFmpeg/models are external prerequisites. Review the [architecture limitations](05_desktop_architecture.md) before accepting the first build.

All authored source, original FSD/PDF documents, this record, changes.md and the dated testing handoff are intended for the initial local commit. No remote publication is authorised until Riz supplies the repository.
