# Midminton Phase 2: Shot Classification, Match Recap and Court Analytics

**Version:** 1.1  
**Date:** 26 October 2026  
**Status:** Detailed implementation specification, not a measured model capability.  
**Prerequisites:** [Overall specification](01_overall_specification.md) and [Phase 1](02_phase_1_scoring_and_video.md).

## 1. Purpose and prerequisites

Add useful analysis to the corrected Phase 1 timeline: name each player, classify contacts, reconstruct rally shot sequences and report shot/outcome/positioning metrics. The application should help Riz inspect evidence, not merely produce attractive but unsupported numbers.

Required Phase 1 inputs:

- Stable match/player/team IDs and court-end mapping.
- Source timestamps, calibrated view segments and image/court transforms.
- Player/shuttle observations with observed, inferred and missing states.
- Contact/rally/point proposals plus manual corrections and locks.
- Background-person roles, foreground-crossing intervals and visibility quality.
- Rules, score checkpoints, unresolved points and current edit revision.

If Phase 1 data is incomplete, compute only supported metrics and show why others are unavailable. Do not require all points to be resolved before allowing shot review.

## 2. Player names and stable identity

Allow names per video for P1-P4, team labels and optional racket-hand information. Preserve IDs when display names change or players swap court ends. Names are labels, not face recognition. A spectator/unknown person is never automatically added to the named roster.

### Example roster

```json
{
  "match_id": "midminton-demo-001",
  "players": [
    {"player_id": "P1", "team_id": "A", "display_name": "Riz"},
    {"player_id": "P2", "team_id": "A", "display_name": "Partner"},
    {"player_id": "P3", "team_id": "B", "display_name": "Opponent 1"},
    {"player_id": "P4", "team_id": "B", "display_name": "Opponent 2"}
  ],
  "edit_revision": 18
}
```

This is fictional example data. Naming P1 does not resolve an earlier identity swap. If P1/P2 tracks were mixed, correct their interval assignments first and invalidate the affected player statistics.

## 3. Shot vocabulary and representation

### 3.1 Families and modifiers

Use a stable family plus separate modifiers, rather than a different model class for every combination.

| Family | Meaning / variants | Examples of modifiers |
|---|---|---|
| `serve` | Low/short, high, flick, drive | subtype, forehand/backhand, target zone |
| `clear` | Overhead shot toward rear court; "toss" may be a display alias | straight/cross, high/attacking |
| `lift` | Upward return from forecourt toward rear court | straight/cross, forehand/backhand |
| `drop` | Overhead soft shot into forecourt | straight/cross, fast/slow, slice where supported |
| `smash` | Attacking downward stroke | standing/jump/half, straight/cross/body |
| `drive` | Flatter, faster exchange | straight/cross/body, forehand/backhand |
| `net_shot` | Shot played near net | straight/cross, tight/tumbling |
| `net_kill` | Finishing attack near net; "tap" may be an alias | forehand/backhand, direction |
| `push` | Placement into an open gap, often midcourt | straight/cross, destination zone |
| `block` | Soft defensive response | straight/cross, net destination |
| `unknown` | Insufficient evidence or unsupported class | reason, review status |

"Net drop" should normally map to a near-net `net_shot`, while an overhead drop remains `drop`. Confirm the owner's meaning of "dribble" before assigning it to tight/tumbling net play or creating a new class. Aliases are configurable and must not silently relabel historical training data.

### 3.2 Example classified contact

```json
{
  "contact_id": "contact-073",
  "rally_id": "rally-021",
  "time_s": 251.83,
  "hitter_player_id": "P2",
  "hitter_team_id": "A",
  "shot": {
    "family": "drop",
    "direction": "cross",
    "hand": "forehand",
    "subtype": "unknown",
    "display_label": "Cross-court drop"
  },
  "status": "proposed",
  "origin": "model",
  "confidence": 0.78,
  "visibility": "observed",
  "evidence_refs": ["contact-window-073"],
  "analysis_run_id": "run-004",
  "edit_revision": 18
}
```

The example confidence is illustrative. Family, direction and hitter can have different quality levels. A confident drop label does not imply a confident cross-court or individual-hitter label.

## 4. Efficient classification pipeline

1. Reuse Phase 1 contact timestamps and tracks. Do not decode/track the whole match again merely to classify shots.
2. Extract short contact-centred windows with configurable temporal context.
3. Obtain lightweight player pose, shuttle trajectory and relative court geometry where valid.
4. Run a small temporal classifier or a compatible BST-style adapter as a candidate.
5. Emit family/modifier alternatives, confidence, evidence quality and unknown fields.
6. Resolve manual overrides last; version the effective labels separately from raw predictions.
7. Aggregate recaps and statistics deterministically from the selected effective revision.

Start with broad classes, then add variants after measuring per-class confusion on Midminton footage. Cross-court classification needs supported directional evidence; a single pose snapshot is insufficient. Geometry-only direction estimates are not true 3D shuttle trajectories.

On the target 4 GB GPU, run pose/classification in separate short-window passes and unload models before Ollama. Use cached features. Avoid a large full-match SlowFast model as the initial default. Existing weights may not support all requested families; absent classes require labelled data/training or remain unknown, not a renamed output neuron.

## 5. Occlusion-aware classification and recaps

- Exclude all background-person tracks from pose features, shot attribution and court occupancy.
- Do not classify a spectator's arm movement as a badminton stroke.
- If a contact is observed but the individual is hidden, allow team-only attribution.
- If the contact itself is unseen, do not manufacture a stroke to force alternating teams or a smooth rally.
- Mark uncertain direction/landing separately from known shot family.
- Keep short interpolations labelled inferred. They do not become labelled training truth automatically.
- A role/identity correction invalidates affected classifications, per-player recaps and metrics.

### Example recap with a hidden ending

The following is fictional, not a claim about an actual channel rally:

| Time | Player/team | Shot | Evidence |
|---|---|---|---|
| 04:08.20 | P1 / A | Low serve | Observed; confirmed |
| 04:08.74 | P3 / B | Net shot | Observed; proposed |
| 04:09.31 | P2 / A | Lift | Observed; confirmed |
| 04:10.05 | P4 / B | Smash | Observed; proposed |
| 04:12.00-04:13.40 | Unknown | End hidden by passer-by | No inferred final stroke |

Recap: `4 observed contacts; exact total unknown; point winner A manually confirmed; ending mechanism unknown.` Do not display "4 shots in the rally" as an exact total. The final point result can be known while the stroke count and ending mechanism remain uncertain.

Keep actual boundary time/uncertainty separate from the scoreboard transition time. A user-confirmed winner plus a manual display anchor does not establish exact rally duration. If the interruption is marked replay/no-point, recap it as interrupted with no score award, rather than assigning a winner.

## 6. Point outcomes: keep facts and judgments separate

Store at least:

1. `winner_team_id`: score outcome, possibly manually confirmed.
2. `last_hitter`: observed/unknown identity; not assumed from winner alone.
3. `ending_detail`: net failure, out long/wide, missed return, other or unknown.
4. `outcome_category`: winner, forced error, unforced error, fault or unknown.
5. Evidence, origin, confidence and reviewer override for each conclusion.

An opponent's good shot can cause a forced error. It is not necessary to choose between "the opponent played well" and "the player made an error" as if they were mutually exclusive explanations.

### Example judgments

- Visible routine return goes long; player was balanced: propose unforced error, subject to review.
- Wide defensive lunge followed by a failed return: propose forced error with movement/contact evidence.
- Winning team known, terminal shuttle hidden: retain unknown ending/category; include the point in score statistics only.
- Apparent service fault not visible clearly enough: unknown, rather than a definitive fault label.

Do not copy a fixed movement-speed threshold from another project as universally correct. A pressure proxy can assist review, but it is not proof of fault or avoidability. Ollama must not adjudicate these categories.

## 7. Metric definitions and examples

### 7.1 Counts and denominators

| Metric | Definition | Example |
|---|---|---|
| Shot count | Effective, non-voided observed/confirmed contacts with the selected label | 12 smashes; 3 additional contacts have unknown family |
| Shot share | Family count / contacts with known family in the stated scope | 12 / 40 known-family contacts = 30%; also show unknown count |
| Immediate winner rate | Direct rally-ending winners of that family / eligible family contacts | 3 / 12 smashes = 25%, when all 12 have known immediate outcomes |
| Immediate error rate | Direct point-losing errors of that family / eligible family contacts | 2 / 12 = 16.7%; exclude/report unknown immediate outcomes |
| Rally conversion after shot | Won distinct resolved rallies containing the player's family / all distinct resolved rallies containing that family | 6 wins in 8 rallies containing a smash = 75%; do not count repeated smashes in one rally twice |
| Serve win rate | Resolved points won by serving team / resolved points with known server | 9 / 15 = 60%; unknown servers/outcomes reported |
| Rally duration | Supported end timestamp minus supported start timestamp | 7.4 s; unavailable if boundaries cannot be resolved |
| Stroke count per point | Exact only when contact coverage is sufficiently verified | 9 confirmed contacts, or "at least 7; gap present" |

Clarification for the conversion row: numerator is won distinct eligible rallies; denominator is all resolved distinct eligible rallies. Always show counts beside percentages. Do not mix contact-level and rally-level denominators.

Exclude `replay/no_point` rallies from scored-point, serve-win and rally-conversion denominators. Their observed strokes may remain in a separately labelled "all observed play" view; default scored-match shot statistics exclude them. Report excluded/interrupted rally and contact counts so the scopes are explicit.

### 7.2 Required analysis groups

- Score progression, points won/lost, scoring runs and lead changes, respecting provisional intervals.
- Winner/error/fault/unknown counts; net versus out; player/team and shot/zone splits.
- Shot distribution and forehand/backhand/straight/cross attributes where supported.
- Short/medium/long rally performance with configurable bins and valid-duration coverage.
- Serve/receive outcomes and opening sequences such as low serve -> net reply -> lift.
- Contact/destination maps with uncertainty; do not draw precise landing dots from unsupported airborne projections.
- Per-player court occupancy, front/mid/rear share, approximate distance and recovery.
- Doubles formations, spacing and rotations; later compare partners, opponents and sessions.

## 8. Court-position and movement calculations

Project reliable foot-contact estimates through the correct calibration segment. Preserve stable IDs across end changes. Offer camera-fixed maps and own-half normalised maps; label the coordinate convention and do not accidentally merge both teams.

### Coverage example

P1 is in live play for 120 s. Reliable observed court positions cover 90 s; 30 s are occluded/unreliable. P1 spends 27 of the valid seconds in the forecourt:

```text
Valid position coverage: 90 / 120 = 75%
Forecourt share of valid observations: 27 / 90 = 30%
Unobserved time: 30 s; actual whole-period forecourt share is unknown
```

Do not claim `27 / 120 = 22.5%` is the actual forecourt share or fill the missing 30 s at the last known position. Use time-weighted samples; frame counts alone can bias variable-rate or irregular sampling.

### Distance example

Observed positions (metres) at 10 Hz:

```text
t=0.0: (2.0, 2.0)
t=0.1: (2.3, 2.0)
t=0.2: missing due to spectator
t=0.3: (3.0, 2.0)
```

The first observed segment contributes 0.3 m. Do not bridge the missing interval with 0.7 m as if the true route were known. Default measured distance excludes that gap and reports coverage. An optional estimated trajectory must have a separate estimated-distance field, provenance and configurable gap limit.

Smooth jitter only within valid contiguous spans, preserving raw values. Report distance as approximate and quality-dependent; calibration errors, hidden feet, jumping and bounding-box jitter can distort it.

## 9. Doubles-specific requirements

- Four stable player IDs and two team IDs, independent of left/right/front/back roles.
- Front/back and side-by-side formation estimates from reliable paired positions.
- Missing partner visibility makes formation unknown, not automatically front/back or defensive.
- Rotation detection requires observed role transitions, not a spectator passing through a zone.
- Optional team middle-gap, overlap and spacing indicators; label them geometric estimates.
- Per-player contribution and shot participation must report unknown/team-only contacts.
- Preserve team attribution across game-end swaps and identity corrections.

Example: P1 is at the net while P2 is hidden for 2 s. Report `formation unknown for 2 s`; do not infer P2 is at the back merely because P1 is in front.

## 10. Reports, video review and exports

Required views:

1. Match overview with reviewed score, data coverage and unresolved counts.
2. Per-rally recap: ordered contacts, hitters, labels, count quality and outcome evidence.
3. Per-player/team shot and outcome statistics.
4. Court heatmaps and movement/formation views.
5. Review queue for low confidence, background/identity conflicts and missing evidence.

Every chart should link to its contributing rallies/contact windows. Support filtering by shot family, player, team, outcome, confidence and visibility. Correcting a label updates the recap and aggregates without rerunning tracking.

Export structured JSON and flat CSV tables with stable IDs and provenance; keep the scored video from Phase 1. PDF/human-readable match reports and highlight reels may be added as optional presentation features after the core analytics work.

## 11. Optional Ollama narrative

Feed the local text model a compact factual packet, not an entire 13-minute video. Candidate: `qwen3:1.7b` Q4_K_M with short context/output and sequential GPU ownership; exact selection remains open.

```json
{
  "match_id": "midminton-demo-001",
  "edit_revision": 18,
  "score_status": "reviewed",
  "player": "P1",
  "facts": [
    {"metric": "smash_count", "value": 12, "contact_ids": ["c001", "c008", "c013", "c018", "c023", "c028", "c033", "c038", "c043", "c048", "c053", "c058"]},
    {"metric": "direct_smash_winners", "value": 3, "rally_ids": ["r003", "r009", "r014"]}
  ],
  "quality": {"unclassified_contacts": 3, "position_coverage": 0.75},
  "instruction": "Describe only supplied aggregates; do not infer hidden shots or causation."
}
```

The IDs are fictional, but the evidence list contains all 12 counted contacts. Actual reports must preserve a complete machine-checkable evidence index, or explicitly declare truncation and provide a link to the complete index.

Validate narrative numbers against the packet. Require evidence links for observations, and identify small samples. A failed language-model run must leave a complete deterministic report available. Never let narrative generation alter events, scores or manual labels.

## 12. Acceptance and regression examples

| Test | Expected result |
|---|---|
| Rename P1 to Riz | Same ID and counts; only labels/report/export presentation change |
| Correct contact from smash to drop | Shot count/share and affected recaps update; score unchanged |
| Background person swings arm | No roster stroke or heatmap contribution |
| Spectator hides a contact | Unknown contact/label evidence retained; no fabricated sequence |
| Interrupted rally marked replay/no-point | No point outcome contribution; interrupted strokes kept outside default scored-match aggregates |
| Track interval corrected P1 -> P2 | Relevant per-player statistics move; unrelated manual point locks survive |
| Point winner changed | Outcome-based metrics refresh; raw observations unchanged |
| 25% missing court time | Coverage visible; occupancy denominators exclude missing time |
| Partner hidden in doubles | Formation unknown; no confident rotation inferred from gap |
| Multiple smashes in one rally | Contact count increases; rally conversion denominator counts one rally |
| Missing classifier/Ollama | Manual labelling and deterministic recap remain usable |

Evaluate shot family and modifier precision/recall separately, with confusion matrices and accepted/unknown coverage. Evaluate singles/doubles and clear/occluded clips separately. Hold out a different match/session; no adjacent windows from the same rally may leak across training and test sets.

All statistical examples above are fictional arithmetic illustrations. They are not measured results for the Midminton channel. Do not claim a trained classifier supports variants until its labels, weights and evaluation demonstrate that support.

## 13. Delivery sequence and extension points

1. Names + editable shot ledger + deterministic recap using hand-labelled example contacts.
2. Broad shot classifier pilot on cached Phase 1 windows.
3. Validity-aware court occupancy and movement.
4. Outcome statistics, serve/receive and doubles formation analysis.
5. Optional local narrative and richer variants after validation.

Keep taxonomy, aliases, model adapters and metrics versioned. A future statistics model may suggest improvement themes from the same factual exports. It must add recommendations with evidence and uncertainty, without replacing the corrected event log or erasing historical model outputs.
