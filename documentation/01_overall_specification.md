# Midminton: Overall Specification and Processing Design

**Version:** 1.1  
**Date:** 26 October 2026  
**Status:** Implementation handoff; no application has been built or benchmarked.  
**Owner:** Riz / Midminton.

## 1. Purpose and reading order

Build a local application that converts an owner-recorded badminton match into an editable point timeline, a synchronised scoreboard video and, in Phase 2, shot and positioning analysis.

Read this document first, then:

1. [Phase 1: Scoring and Video](02_phase_1_scoring_and_video.md).
2. [Phase 2: Shots and Analytics](03_phase_2_shots_and_analytics.md).
3. [Concise PDF specification](Midminton_Application_Specification_v1.pdf). Its internal revision is 1.1; the filename is retained to preserve existing links.

The Markdown files contain more examples and implementation detail than the PDF. All examples are proposed contracts, not an existing API or tested application. Hardware budgets and accuracy thresholds are initial targets, not measured results.

## 2. Product workflow and constraints

```text
Original recording
  -> inspect and create review proxy
  -> calibrate active court / confirm roster
  -> player + scene-quality pass
  -> temporal shuttle pass
  -> contacts / rallies / winner proposals
  -> editable point timeline / deterministic scoring
  -> review and correct
  -> scored MP4 + analysis data
  -> Phase 2 shot classification / court analytics / optional text recap
```

- Input: typically 8-13 minutes, singles or doubles, fixed or segmented camera views.
- Initial mode: recorded-video processing. "Live score" means updating during playback, not a real-time camera guarantee.
- Preferred backend: Python. Final UI framework, database and exact model versions remain open.
- Target hardware: RTX 3050 laptop GPU with 4 GB VRAM and 16 GB system RAM.
- Required processing must be local and use free software/models. No mandatory API fees, paid GPU, subscription or paid checkpoint.
- Initial model downloads need internet. Existing hardware, storage and electricity are assumed.
- Original video must remain unchanged. Preserve original timestamps and audio synchronisation.
- The user must remain able to correct results even when AI inference is unavailable.

## 3. Phase boundaries

| Phase | Required result | Essential dependencies |
|---|---|---|
| Phase 1 | Singles/doubles proposal; 2/4 player identities; noise handling; contact/hitter and point proposals; editable scoreboard; MP4 export | Basic tracking, court calibration, shuttle analysis, event log, review UI, score engine |
| Phase 2 | Editable player names; shot classification; rally recaps; shot/outcome statistics; court occupancy/movement | Reuse Phase 1 identities, timebase, observations, corrections and scene-quality records |

Phase 1 uses stable labels P1-P4. Phase 2 adds names without changing IDs. Basic identity tracking is already required in Phase 1; Phase 2 makes its court-space history useful for analytics.

## 4. Non-negotiable correctness rules

1. A new detected person is not automatically a match participant.
2. Spectators and adjacent-court players never contribute to active-player counts or match statistics.
3. An occluded player remains the same player; a passer-by must not inherit their identity.
4. Missing visual evidence remains missing. Predictions and interpolation must be labelled.
5. Net contact alone does not mean a point ended; an airborne shuttle leaving view is not automatically out.
6. Each point award is represented once, with a stable ID and evidence/status.
7. Manual locked edits take precedence over model predictions.
8. Score is replayed from accepted point events and trusted checkpoints; it is not a free-floating counter.
9. The running score is provisional after an unresolved earlier point until a correction/checkpoint restores certainty.
10. A language model must not invent winners, numerical statistics or missing shots.

An interrupted rally may be marked `replay/no_point` by the user/official: keep its evidence, award neither team and do not infer a previous winner from the next serve. A known winner also does not establish an exact unseen end time; store an uncertainty interval and a separate score-display transition when needed.

## 5. Architecture and module contracts

Suggested function names describe responsibilities; they do not mandate a package layout.

| Module | Suggested functions | Outputs / constraints |
|---|---|---|
| `media` | `inspect_video`, `map_timestamp` | Media manifest, source fingerprint, variable-frame-rate mapping |
| `proxy` | `prepare_proxy` | SDR review proxy; source/proxy coordinate and time transforms |
| `court` | `calibrate_view`, `project_footpoint` | Court mask, net, calibration segments, quality |
| `players` | `track_players`, `resolve_identity` | Detection tracks, stable roster IDs, teams, observed/lost states |
| `scene_quality` | `assess_scene_quality`, `classify_person_role` | Background roles, occlusion intervals, affected identities/events |
| `shuttle` | `track_shuttle`, `refine_window` | Temporal detections, trajectory quality and observed/inferred provenance |
| `contacts` | `detect_contacts`, `attribute_hitter` | Contact proposals, player/team attribution, confidence |
| `rallies` | `segment_rallies`, `resolve_point` | Serve/start/end candidates, winner evidence, unresolved points |
| `scoring` | `replay_events`, `validate_checkpoint` | Derived score, serving order, game/end state, conflicts |
| `review` | `apply_edit`, `lock_decision`, `undo_edit` | Revisions, overrides, review clips and downstream invalidation |
| `render` | `render_overlay`, `export_video` | Preview/export parity, MP4/audio, export revision |
| `analytics` | `classify_shots`, `aggregate_metrics` | Phase 2 shot ledger, recaps, heatmaps, coverage |
| `recap` | `build_factual_report`, `generate_narrative` | Deterministic report; optional Ollama wording |
| `jobs` | `run_stage`, `resume_job` | Sequential GPU lease, progress, cancellation, cache/checkpoints |

## 6. Background people and accidental camera crossings

### 6.1 Role is separate from visibility

Use three person-role values:

- `active_player`: a roster member in this match.
- `background_person`: spectator, adjacent-court player or other non-participant.
- `unknown_person`: insufficient evidence to assign a role.

Store occlusion separately: `none`, `foreground_crossing`, `player_overlap`, `static_obstruction` or `whole_view_blocked`. An active teammate can obscure another player; that does not turn them into a spectator. These labels identify a role, not a person's real-world identity. Face recognition is unnecessary.

### 6.2 Classification and recovery policy

Use a calibrated active-court region together with track persistence, motion continuity, appearance and roster history. Spatial gating alone is insufficient: a spectator may cross the court, and a real player may run outside the sidelines.

- Establish 2/4 persistent participants across several clear intervals. If there are three visible people in doubles, preserve the missing fourth player rather than declaring singles.
- Keep spectators/unknowns in separate person tracks. Do not allocate them to a free roster slot because a player disappeared.
- Detect likely foreground obstructions from relative image scale, motion, overlap and visibility changes. Large bounding boxes are evidence, not a universal exclusion threshold.
- Preserve an active identity during a gap. Any short motion prediction is tagged inferred; do not extend it indefinitely.
- Reassociate after a crossing only with plausible history and sufficient evidence. Otherwise ask for manual track reassignment through the review UI.
- If the camera moved, invalidate that segment's calibration. A stationary-camera crossing alone does not invalidate geometry.
- Recompute affected inference/analytics after a role or identity correction. Preserve unrelated manual point locks.

### 6.3 Example scene-quality record

```json
{
  "noise_id": "noise-007",
  "start_s": 252.0,
  "end_s": 253.4,
  "person_track_id": "B7",
  "person_role": "background_person",
  "occlusion_type": "foreground_crossing",
  "affected_player_ids": ["P2"],
  "affected_event_ids": ["rally-021"],
  "shuttle_visibility": "occluded",
  "status": "review_needed",
  "origin": "model",
  "confidence": 0.86
}
```

This illustrative confidence is not a measured accuracy. At 04:12, B7 hides P2 and the shuttle. P2 remains on the roster, their track becomes occluded, and an unseen point ending stays unresolved. A later known point can be retained while cumulative score remains provisional.

## 7. Data ownership, identifiers and revisions

| Layer | Contents | Mutation policy |
|---|---|---|
| Source | Original media and source manifest | Immutable |
| Observations | Boxes, pose, shuttle detections, visibility and raw model outputs | Immutable per inference run |
| Decisions | Rallies, contact attribution, point/shot proposals, no-point/replay and role decisions | Versioned; retain origin/evidence and independent timing quality |
| Overrides | Manual edits, locks, score checkpoints and identity assignments | Append revision; undo through a new edit |
| Derived outputs | Score timeline, statistics, heatmaps, reports and exports | Rebuild from selected run + overrides |

All event times use a canonical media timebase, for example integer microseconds from source presentation timestamps. Seconds in these examples are for readability. Do not assume `frame_index / 30` is correct for variable-frame-rate recordings.

Every derived artifact identifies `match_id`, `analysis_run_id`, `edit_revision`, calibration version and model/configuration checksums. Player IDs do not change when names, court ends or partners' positions change.

## 8. Local processing and memory plan

### 8.1 Provisional candidates

| Task | Candidate | Selection condition |
|---|---|---|
| People | YOLOX-Nano/Tiny ONNX | Adequate far-player detection on actual footage; code and weights licences checked |
| Tracking | Native MIT ByteTrack association plus roster logic | Does not by itself solve spectators or long-term re-identification |
| Shuttle | TrackNetV3, optional separate InpaintNet pass | Compatible checkpoint, input geometry and temporal sampling; measured 4 GB fit |
| Pose/contact evidence | Lightweight cropped pose, CPU first | Run near contact windows; preserve visibility/confidence |
| Shot type | Small temporal pose/trajectory classifier; BST-style adapter as candidate | Evaluate compatible weights before training; retain unknown labels |
| Text recap | Optional Ollama `qwen3:1.7b` Q4_K_M | Use structured aggregates only; deterministic report remains available |

The Qwen tag was documented at about 1.4 GB download during the earlier source check. Runtime memory is larger and depends on context. It is a candidate, not a required final choice.

### 8.2 Execution policy

1. Inspect metadata and create a 720p/1080p review proxy; retain original media for refinement/export.
2. Player/scene pass at an initial 8-12 observations/s; tracker predicts only short labelled gaps.
3. Unload person model, then run temporal shuttle inference at a validated rate, initially evaluating 30 fps.
4. Use chronological chunks with model-context overlap and timestamp-based deduplication.
5. Reprocess uncertain windows only, retaining coordinate transforms and model compatibility.
6. Compute score/review results without retaining decoded full-match frames.
7. Run optional pose/classifier and Ollama stages separately; release GPU memory between stages.

Proposed budgets: one GPU inference job at a time; aim below 3.2 GB VRAM and 8-10 GB backend RAM; start with microbatch 1 and 0-2 data-loader workers. Treat these as targets. A batch-size-one out-of-memory condition requires CPU fallback or an explicitly validated smaller adapter, not silently discarded input.

Illustrative timing: 8-13 minutes at 30 fps means 14,400-23,400 frames. A shuttle pass at 10-20 effective video frames/s would take about 12-39 minutes before other stages/export. This is arithmetic, not an RTX 3050 benchmark.

## 9. Example job configuration

Values below are provisional starting points. Implementers must validate them rather than treat them as trained-model guarantees.

```yaml
schema_version: "1.1"
mode: recorded_video
input:
  path: "owner_match.mp4"
  preserve_original: true
analysis:
  discipline: auto_with_override
  player_sample_hz: 10
  shuttle_sample_fps: 30
  validate_checkpoint_sampling: true
  chunk_seconds: 45
  overlap: derive_from_model_context
resources:
  gpu_jobs: 1
  microbatch: 1
  loader_workers: 0
noise:
  enabled: true
  maintain_separate_background_tracks: true
  preserve_roster_during_occlusion: true
  infer_outcomes_from_missing_visibility: false
scoring:
  unknown_point_policy: provisional_until_resolved_or_checkpoint
  preserve_manual_locks: true
ollama:
  enabled: false
  candidate_model: "qwen3:1.7b"
  context_tokens: 2048
  keep_alive: 0
output:
  video: "match_scored.mp4"
  analysis: "match_analysis.json"
```

## 10. Incremental changes and cache invalidation

| Change | Recompute | Preserve |
|---|---|---|
| Player display name | Labels, report and exports | Observations, IDs, point decisions |
| Insert/change/delete point | Downstream score/service state and outcome aggregates | Raw tracking and unrelated manual locks |
| Reassign a track from P1 to P2 | Affected contacts, per-player stats and review conflicts | Team point locks unless explicitly changed |
| Mark spectator / obstruction | Affected roster proposals, visibility and analytics coverage | Original detections and unrelated events |
| Recalibrate a view | Court positions and dependent geometry/events | Source timestamps and manual overrides, with conflict review |
| Replace a vision model | Its observations and dependent proposals | Prior runs and all manual decisions |

Use atomic stage outputs and stable IDs. A resumed chunk must not award points twice. Regenerate exports against the selected edit revision; label older exports stale.

## 11. Reference footage and verification

- [20-10-2026 Match 2](https://www.youtube.com/watch?v=XaOaKURxe3s): singles reference.
- [11-10-2026 Match 3](https://www.youtube.com/watch?v=8ztbAE8YBqA): doubles reference.
- [27-09-2026 Match 3](https://www.youtube.com/watch?v=UgrUFtS4vl8): additional view/occlusion reference.

Prefer original files. Prior visual review sampled these videos; no inference or laptop benchmark has been performed. Do not claim the selected videos contain every required noise scenario. Label representative clips and add explicit spectator-crossing/blocked-view examples if absent. Controlled edited test clips must be labelled synthetic and evaluated separately from natural footage.

Keep a held-out match/session. Report identity switches, person-role mistakes, contact precision/recall, hitter accuracy, rally-boundary error, winner precision AND acceptance coverage, unresolved intervals, processing time and peak memory. The phase-specific documents define scenarios and provisional targets.

## 12. References and reuse constraints

These references informed the earlier source review; they are not verified drop-in implementations of this specification.

- [COURTSIDE / BadmintonAI](https://github.com/jayclim/BadmintonAI): score OCR, analytics and experimental doubles. Existing-scoreboard OCR is insufficient for raw-video winner inference.
- [Badminton CV Annotator](https://github.com/ahalp90/badminton_cv_annotator): rally/contact and winner evidence; inspect singles assumptions and LGPL/component terms.
- [Doubles review tool](https://github.com/nathan1658/badminton-video-analysis): event-derived scoring and correction UI ideas.
- [MDS06 backend](https://github.com/bryanlje/mds06-backend): action-recognition pipeline reference, not the complete score engine.
- [TrackNetV3](https://github.com/qaz812345/TrackNetV3): temporal shuttle tracking and optional inpainting.
- [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX), [ByteTrack](https://github.com/FoundationVision/ByteTrack), [MediaPipe Pose](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker).
- [Ollama memory FAQ](https://docs.ollama.com/faq), [Qwen3 candidate](https://ollama.com/library/qwen3:1.7b), [FFmpeg build/licence notes](https://ffmpeg.org/legal.html).

Check licences for each chosen code version AND weights. Preserve notices and dependency manifests. Do not introduce mandatory hosted services, embedded third-party API keys or paid-model fallbacks. Final stack decisions, exact confidence thresholds and model selection remain open to revision after the pilot.
