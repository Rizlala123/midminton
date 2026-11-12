# Midminton Phase 1: Players, Points, Editable Score and Video Export

**Version:** 1.1  
**Date:** 26 October 2026  
**Status:** Detailed implementation specification, not implemented software.  
**Prerequisite:** [Overall design](01_overall_specification.md).  
**Next phase:** [Shot classification and analytics](03_phase_2_shots_and_analytics.md).

## 1. Phase 1 outcome

Given an 8-13 minute owner-recorded match, the application should identify the active players, propose singles/doubles, detect contacts and point endings, attribute hitters, build an automatically updating score and export a scored video. Every point and identity decision remains reviewable and correctable.

Phase 1 must operate on a laptop with 4 GB RTX 3050 VRAM and 16 GB RAM through staged local inference. It does not require Ollama: a text model is not the scoring authority. Model candidates and memory policies are in the overall document.

### Included

- Local video import, metadata/proxy preparation and court calibration.
- Stable P1-P4 roster IDs, teams, singles/doubles proposal and manual override.
- Background-person labelling, spectator-crossing detection and occlusion recovery.
- Shuttle/contact tracking, hitter attribution and rally/winner proposals.
- Editable event timeline, score/service-state engine, checkpoints, undo/redo and save/resume.
- Shared preview/export scoreboard and MP4/audio output.

### Deferred

- Friendly player names, shot-type classification and full statistical reports: Phase 2.
- Real-time camera capture, accurate 3D shuttle speed, line-judge precision and automatic technical coaching.

## 2. User journey

1. Import a local recording; show duration/resolution and warnings about unsupported/corrupt media.
2. Select the active court and confirm calibration on a clear frame. Split calibration if the camera moved.
3. Propose singles/doubles and active players. Let the user confirm/reassign P1-P4 and teams.
4. Enter starting score, initial server/receiver and rules when not inferable. A recording may begin mid-game.
5. Run analysis with stage progress, pause/cancel and resumable checkpoints.
6. Review point proposals, uncertainty intervals and identity issues beside the video.
7. Insert/correct/delete points or set a trusted score at any timestamp.
8. Preview the full score timeline, then export video plus corrected analysis data.

Manual editing must be available before all AI stages succeed. Failure of shuttle inference must not destroy an already reviewed score timeline.

## 3. Functional requirements

| ID | Function | Required behaviour |
|---|---|---|
| P1-01 | Video/timebase | Preserve source timestamps, duration and original media; map proxy frames back to source |
| P1-02 | Court/scene | Calibrate active court and net; detect changed views; distinguish camera movement from temporary obstruction |
| P1-03 | Discipline | Infer 2/4 active participants across clear intervals; allow uncertain/manual override |
| P1-04 | Identity | Stable roster IDs and teams through crossings, gaps and end changes; manual reassignment |
| P1-05 | Noise | Label background/unknown people and obstruction intervals; no spectator roster substitution |
| P1-06 | Shuttle/contact | Temporal shuttle observations, contact candidates, hitter/team and confidence |
| P1-07 | Point/winner | Separate rally boundary from winner evidence; unresolved is a valid result |
| P1-08 | Score | Rules-based replay from accepted points and trusted checkpoints |
| P1-09 | Correction | Edit anywhere; preserve manual locks; recalculate downstream state; selectively recheck AI |
| P1-10 | Preview/export | Same overlay/revision in review and MP4; original audio where present |
| P1-11 | Persistence | Save/reopen/resume with no duplicated points or lost edits |

## 4. Match and player identification

### 4.1 Bootstrap the roster

Detect people in several clear windows, project reliable footpoints to the active court, associate tracks and examine participation over time. Court location, clothing, motion and persistence are supporting signals. Do not assume that the most confident two/four detections are always the players.

Examples:

- Two players rally while a coach stands outside the sideline: propose singles, with a separate background track.
- Four players rally; one disappears behind their partner: keep doubles with one occluded identity.
- Three people visible during a long pause: preserve the established discipline, or remain uncertain if no roster exists yet.
- A true player runs outside a sideline to retrieve a shot: retain their player ID using history; do not permanently exclude them with a strict court polygon.

The roster is stable within a game/session unless an explicit substitution or correction is recorded. Physical people changing court ends does not change team membership.

### 4.2 Identity state machine

```text
candidate -> active/observed -> active/occluded -> active/observed
                                      |
                                      +-> active/lost -> review/reassociation

new bystander -> background or unknown track (not an automatic roster member)
```

Suggested identity resolver:

```python
# Pseudocode: the scoring engine never depends on a guessed reassignment.
def resolve_identity(previous_roster, detections, scene_quality, history):
    candidates = gate_by_motion_appearance_and_team_context(detections, history)
    block_occluder_takeovers(candidates, scene_quality)
    assignments, conflicts = associate_with_existing_roster(candidates)
    preserve_missing_roster_members_as_occluded_or_lost(assignments)
    return assignments, conflicts
```

Temporal and appearance thresholds are configurable pilot parameters. A confidence number must not be presented as calibrated probability without evaluation.

## 5. Background people and foreground noise

### 5.1 Scene-quality output

Maintain person roles `active_player`, `background_person`, `unknown_person`, independently from visibility `observed`, `occluded`, `inferred`, `lost`. Track occlusion type separately, including foreground crossings, player overlap, static obstacles and whole-view blockage.

Emit the interval, affected players, affected image region, shuttle visibility, evidence, confidence and review status. The review UI should offer an optional debug overlay showing background tracks and obstruction flags. The default exported video should remain clean; no spectator labels or blur effect is required.

### 5.2 Example: accidental spectator crossing

| Time | Evidence | Required system result |
|---|---|---|
| 04:11.8 | P2 and shuttle visible | Normal observed tracking |
| 04:12.0 | B7 enters close to lens | Flag foreground crossing; B7 remains outside roster |
| 04:12.3 | P2 hidden behind B7 | Preserve P2 as occluded; do not copy B7's box into P2 |
| 04:12.7 | Shuttle disappears near apparent rally end | Mark end/winner evidence insufficient; no point from disappearance alone |
| 04:13.4 | B7 exits; player candidates reappear | Reassociate only with adequate evidence; otherwise request identity review |
| 04:20.0 | Next serve visible | May supply independent winner evidence if service identity and game continuity are established |

If a manual correction confirms Team A won the hidden rally, add/confirm its point event, replay scores and retain the obstruction record. Do not invent a final hit or landing time.

### 5.3 Other required cases

- A seated spectator is persistently detected: background, never a player simply because the bounding box projects into the court.
- A passer-by wears the same shirt as P1: appearance alone must not permit takeover.
- A teammate blocks a partner: player role stays active; visibility changes.
- A chair hides feet: retain image-space identity but mark court position unreliable.
- Entire view blocked: continue media time, preserve pending state, lower evidence quality and reacquire after the view clears.
- Camera bumped by a passer-by: close the old calibration segment, identify a new stable view and request calibration before using court-space measurements.
- Play interrupted and replayed because of a crossing: record `replay/no_point`, award neither team and keep the interrupted rally's evidence. The next serve is not proof that someone won the interrupted rally.

## 6. Shuttle and contact processing

1. Use a temporal heatmap tracker such as a compatible TrackNetV3 checkpoint. Read its supported input geometry and sequence length.
2. Evaluate 30 fps first; retain source timing. Validate any temporal-rate changes rather than feeding arbitrary strides into the same checkpoint.
3. Run microbatch 1 initially, with bounded decoding and chronological chunks. Overlap windows and deduplicate by canonical timestamp.
4. Keep detected coordinates, confidence, visibility and interpolation provenance.
5. Find contact candidates from directional/velocity changes plus nearby player/wrist evidence.
6. Run lightweight pose on short candidate windows where necessary; do not load a large pose model for the whole match by default.
7. Attribute a contact to an individual only if identity and proximity evidence support it. In doubles, team-only or unknown attribution is acceptable.
8. Reprocess low-confidence windows using supported higher-detail evidence; do not interpret interpolation as observed floor contact.

### Example contact record

```json
{
  "contact_id": "contact-073",
  "rally_id": "rally-021",
  "time_s": 251.83,
  "hitter_player_id": "P2",
  "hitter_team_id": "A",
  "shot_family": "unknown",
  "status": "proposed",
  "confidence": 0.81,
  "evidence": ["shuttle_direction_change", "visible_wrist_proximity"],
  "visibility": "observed",
  "analysis_run_id": "run-003"
}
```

Phase 1 leaves `shot_family` unknown. IDs and contact records carry forward to Phase 2. Team alternation is a plausibility check, not permission to insert phantom contacts.

## 7. Rally boundaries and point winners

Store `start`, `end` and `winner` as independently uncertain decisions. A boundary can be known while the winning side remains unknown, or vice versa.

| Evidence | What it can support | What it cannot prove alone |
|---|---|---|
| Shuttle visibly settles on floor | End-of-play candidate and approximate location | Last hitter or point winner without context |
| Shuttle appears outside boundary | Out only if terminal landing evidence and correct rules support it | A shuttle travelling outside the image/court while still airborne is not necessarily out |
| Shuttle touches net | Candidate interaction | Rally loss when it crosses legally and play continues |
| Players stop | Potential rally boundary | Which team won, or whether the pause was an interruption |
| Next server established | Previous winner within known match continuity | Final point, unidentified service, replay/no-point interruption or an unrecorded intervening rally |
| Existing broadcast scoreboard | Optional independent reconciliation | Required input: owner recordings may have no scoreboard |

Use singles/doubles and service-specific boundaries. Apply a line-uncertainty band rather than claiming centimetre accuracy. When evidence conflicts, keep an unresolved event and a short review clip.

## 8. Event model and manual correction

### 8.1 Point proposal

```json
{
  "point_id": "point-021",
  "rally_id": "rally-021",
  "end_time_s": null,
  "end_time_window_s": [252.0, 253.4],
  "boundary_status": "unresolved",
  "score_effective_time_s": null,
  "disposition": "point_pending",
  "winner_team_id": null,
  "status": "unresolved",
  "origin": "model",
  "locked": false,
  "evidence_refs": ["noise-007"],
  "revision": 1
}
```

After the user confirms the winner, preserve the original proposal and append an override:

```json
{
  "edit_id": "edit-014",
  "target_id": "point-021",
  "operation": "confirm_point_winner",
  "winner_team_id": "A",
  "disposition": "point_awarded",
  "score_effective_time_s": 253.4,
  "timing_origin": "manual_display_anchor",
  "origin": "manual",
  "locked": true,
  "edit_revision": 14
}
```

### 8.2 Correction operations

- Insert missed point with a timestamp and known winner.
- Change winner without creating a second point.
- Delete/void a duplicate while retaining history.
- Adjust rally/contact timestamps.
- Set a trusted score checkpoint at a timestamp.
- Correct initial server, receiver, discipline, rules or end mapping.
- Reassign an identity across a selected interval.
- Undo/redo, save and reload every correction.

The UI must distinguish score replay from AI reanalysis. Most point edits require no detector rerun. Winner confirmation does not confirm the hidden end time. In the example, 253.4 s is a manually selected overlay transition; the actual rally boundary remains an unresolved interval, so exact rally duration is unavailable.

Allow `point_pending`, `point_awarded` and `replay/no_point` dispositions. A no-point rally has no winning team and no score increment; it is resolved as a non-award, not left pending forever. Distinguish a badminton replay/let from replaying the video in the UI. Retain the interrupted contacts, but exclude that rally from scored-point outcome statistics.

### 8.3 Downstream replay example

| Event | Before insertion | After inserting A's missed point at 03:20 |
|---|---|---|
| 03:00 A wins | 5-4 | 5-4 |
| 03:20 A wins | Missing | 6-4 |
| 03:40 B wins | 5-5 | 6-5 |
| 04:00 A wins | 6-5 | 7-5 |

Changing an earlier winner from A to B subtracts one from later A totals and adds one to B, until a checkpoint boundary requires reconciliation. Recalculate serving order and game boundaries; flag impossible conflicts rather than silently rewriting locked events.

### 8.4 Unresolved score example

Last trusted score is 5-4. One hidden rally is unresolved; the following rally is confidently won by B. Keep B's event, but the cumulative score could be 6-5 or 5-6 depending on the hidden winner. Do not show 5-5 as definitive.

Recommended default overlay: `5-4 | Score provisional: 1 point to review`, with the last trusted score clearly labelled. The point list retains the later B winner. Resolving the hidden point replays both awards. A trusted later checkpoint can restore score certainty without fabricating the missing stroke sequence.

If a checkpoint is 10-8 but only 9-7 can be reconstructed, the two missing awards do not reveal their order or times. Record a reconciliation gap; do not invent two fully observed rallies.

### 8.5 Score engine contract

```python
# Pseudocode; rules and conflict resolution are explicit inputs.
def replay_score(points, checkpoints, manual_overrides, rules, at_time):
    events = resolve_versions_and_overrides(points, manual_overrides)
    state = start_from_latest_valid_checkpoint(checkpoints, at_time)
    for event in ordered_events_after_checkpoint(events, state, at_time):
        if event.is_replay_or_no_point:
            state.record_non_award(event.id)
        elif event.is_unresolved:
            state.mark_provisional(event.id)
        elif event.awards_known_point:
            state.apply_point(event.winner_team_id, rules)
        state.record_conflicts_without_overwriting_locks()
    return state
```

Persist a rules profile rather than hardcoding one format: points to win, win-by margin, cap, games, end changes and service order. If a correction changes a game ending, present affected later game assignments for review. Service-court parity is a check, not a unique server identifier.

## 9. Review UI and export

Required controls: play/pause, seek, speed, frame step, point list, pending-review filter, edit winner, add/delete point, checkpoint, identity correction, undo/redo and save/export.

- A compact high-contrast corner scoreboard must avoid active play and remain within safe margins.
- Seek backward and forward must derive the same score from the event log, not depend on previously played frames.
- Show provisional score status and unresolved counts. A non-numeric status is preferable to a misleading definitive score.
- Optional debug mode can show IDs, spectator labels, quality masks and observed/inferred tracks.
- Preview and export share the same score renderer and selected edit revision.
- Export includes source-timed audio when present. Default to 1080p without upscaling smaller inputs; retain aspect ratio.
- Export clean video by default; debug annotations are opt-in. Background labelling does not require facial recognition or anonymisation.
- Name outputs by match/revision; mark older exports stale after corrections.

Example output bundle:

```text
match_2026_10_20/
  manifest.json
  analysis_run_003.json
  manual_edits.json
  corrected_timeline_rev014.json
  match_scored_rev014.mp4
```

## 10. Jobs, failures and selective reanalysis

- Process in bounded chunks; unload GPU models between stages. Resume from the last completed checkpoint.
- Ensure deterministic chunk deduplication and atomic event writes.
- A score-only edit invalidates score/service state and exports, not raw tracking.
- A spectator/identity correction invalidates affected contacts and related geometry; preserve manual point locks and surface inconsistencies.
- An out-of-memory error pauses the stage with an actionable CPU/smaller-adapter option. Do not silently skip analysis frames.
- Missing model assets must not trigger paid/cloud processing. Continue manual review/export where possible.
- Whole-view blockage is a quality interval, not proof of a rally boundary.

## 11. Acceptance examples and measurements

These are proposed tests to implement. They have not been run against an application.

| Case | Expected result |
|---|---|
| Singles + background third person | Discipline remains singles; third track excluded from roster |
| Doubles + one hidden player | Preserve four roster IDs; mark missing person, no spectator substitution |
| Same-colour spectator crosses lens | No player ID takeover; record affected interval |
| Player briefly leaves court | Retain established identity through plausible history |
| Net touch followed by continued rally | No point awarded solely for contact with net |
| End hidden by passer-by | Point/winner unresolved; cumulative score provisional |
| Spectator interruption marked replay/no-point | No award, no winner inferred from next serve; retain interrupted rally history |
| Resolve hidden point manually | Later known events replay; lock survives AI recheck |
| Insert/change/delete point | Later scores/service state update once, including after reload |
| Conflicting later checkpoint | Visible conflict; no silent overwrite of manual data |
| Cancel/resume at chunk boundary | No duplicate contacts or point awards |
| Seek/export parity | Score at time T matches across seek order and exported frame |
| Final rally | Resolve from evidence/manual review without depending on a next serve |

Initial pilot targets: rally boundaries within +/-0.5 s and at least 90% end recall; contact matching one-to-one within +/-3 analysis frames at 30 fps (about 100 ms), with source-timestamp mapping; at least 95% precision among automatically accepted point winners, with acceptance coverage reported. Report all targets separately for clear/obstructed and singles/doubles footage. No target implies measured performance.

Hard correctness requirements: reviewed final score and export agree; locked edits survive reanalysis; unknown events remain explicit; repeated resume is idempotent. Check audio sync within 100 ms at early/middle/late cues.

Do not satisfy an accuracy target by accepting almost no events without disclosure. Report unresolved coverage, correction effort per match, false participant assignments, player ID switches, contacts missed/duplicated during crossings, peak memory and stage time.

## 12. Suggested delivery order

1. Build the manual event editor, score reducer and export path first.
2. Verify correction/checkpoint/seek behaviour with synthetic event logs.
3. Add calibration, roster and explicit spectator/obstruction handling.
4. Benchmark player/shuttle/contact inference on short Midminton clips.
5. Add rally/winner proposals and confidence-based acceptance.
6. Validate a complete 8-13 minute match, including interruptions and manual corrections.

Keep every step usable. There is no requirement to finish all AI automation before manual scoring/export can work. Refer to the overall document for reference repositories, footage links, model candidates and licensing constraints.
