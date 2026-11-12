"""Bounded two-pass analysis with explicit cache identity and restartable stages."""
import hashlib
import json
from .models import People, Shuttle, descriptor
from .logic import Roster, infer_rallies
from .geometry import Court


def open_capture(path, fps=None):
    import cv2
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise ValueError("Cannot decode the review video; prepare it again")
    actual = capture.get(cv2.CAP_PROP_FPS)
    if fps and abs(actual-fps) > 0.05:
        capture.release()
        raise ValueError("Proxy cadence differs from shuttle model; select its manifest and prepare again")
    return capture


def suggest(project):
    """Suggest from on-court feet only; a person count is never final confirmation."""
    doc = project.read()
    court = Court(doc.get("calibration", []))
    if not doc.get("models", {}).get("people"):
        raise ValueError("Select the person model and mark the court first")
    capture = open_capture(project.path/"review.mp4")
    try:
        ok, image = capture.read()
        if not ok:
            raise ValueError("Cannot decode the opening frame")
        detections = People(doc["models"]["people"]).detect(image)
    finally:
        capture.release()
    sides = [[], []]
    for detection in detections:
        box = detection["box"]
        xy = court.foot(box)
        if xy and all(0 <= n <= 1 for n in xy) and box[3]-box[1] < 0.85:
            sides[0 if xy[1] < 0.5 else 1].append(detection)
    if [len(s) for s in sides] not in ([1, 1], [2, 2]):
        raise ValueError("Opening-frame roster is ambiguous; draw P1/P3 or all four players manually")
    anchors = []
    for side, team in enumerate(("A", "B")):
        for offset, detection in enumerate(sorted(sides[side], key=lambda d: d["box"][0])):
            anchors.append({"id": f"P{side*2+offset+1}", "team": team, "box": detection["box"]})
    return project.edit("settings", {"anchors": anchors, "discipline": "singles" if len(anchors) == 2 else "doubles"}, doc["revision"])


def analyse(project, cancel, progress):
    import cv2
    import numpy as np
    doc = project.read()
    from ..media import validate_source
    validate_source(doc)
    if not (project.path/"review.mp4").exists():
        raise ValueError("Prepare the review proxy first")
    anchors = doc.get("anchors", [])
    if len(anchors) not in {2, 4} or len(doc.get("calibration", [])) != 4:
        raise ValueError("Mark four court corners and confirm two/four player boxes at the opening frame")
    court = Court(doc["calibration"])
    if doc.get("discipline") not in {"singles", "doubles"}:
        raise ValueError("Confirm singles or doubles before analysis")
    expected = {"P1", "P3"} if doc["discipline"] == "singles" else {"P1", "P2", "P3", "P4"}
    if {a["id"] for a in anchors} != expected:
        raise ValueError("Singles needs P1/P3; doubles needs all four roster boxes")
    models = doc.get("models", {})
    for kind in ("people", "shuttle"):
        if not models.get(kind):
            raise ValueError(f"Choose the local {kind} model manifest first")
    person_contract, _ = descriptor(models["people"], "yolox")
    shuttle_contract, _ = descriptor(models["shuttle"], "tracknetv3")
    fps = int(shuttle_contract.get("fps", 30))
    if fps not in {25, 30, 50, 60}:
        raise ValueError("Shuttle manifest must declare a validated 25/30/50/60 fps contract")
    metadata_path = project.path/"review.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    source = {key: doc["media"][key] for key in ("path", "size", "modified")}
    if metadata.get("fps") != fps or metadata.get("source") != source:
        raise ValueError("Select the shuttle model and prepare the proxy again; its cadence/source contract changed")
    fingerprint = hashlib.sha256(json.dumps({"media": doc["media"], "anchors": anchors, "reanchors": doc.get("reanchors", []),
        "calibration": doc["calibration"], "models": [person_contract, shuttle_contract],
        "options": doc.get("analysis_options", {}), "pipeline": 2}, sort_keys=True).encode()).hexdigest()[:24]
    cursor = project.job(fingerprint) or {"people_done": False, "shuttle_frame": 0, "finished": False}
    proxy = str(project.path/"review.mp4")
    duration = doc["media"]["duration"]
    if not cursor["people_done"]:
        detector, roster = People(models["people"]), Roster(anchors, court)
        capture = open_capture(proxy, fps)
        rows, frame, decoded, last_sample = [], 0, 0, -1.0
        reanchors = iter(sorted(doc.get("reanchors", []), key=lambda a: a["time"]))
        upcoming = next(reanchors, None)
        try:
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                if cancel():
                    raise InterruptedError("Player pass cancelled; rerun restarts this lightweight pass")
                time = decoded/fps
                decoded += 1
                if time-last_sample < 0.095:
                    continue
                last_sample = time
                while upcoming and upcoming["time"] <= time:
                    roster.reanchor(upcoming)
                    upcoming = next(reanchors, None)
                result = roster.update(time, detector.detect(image))
                rows.append((frame, result))
                frame += 1
                if len(rows) >= 100:
                    project.write_rows(fingerprint, "players", rows)
                    rows.clear()
                    progress("players", time/duration, "Tracking roster and foreground obstructions")
            project.write_rows(fingerprint, "players", rows)
            if decoded < max(1, (duration-1)*fps):
                raise ValueError("Review video decoding stopped early during player pass")
        finally:
            capture.release()
            del detector
        cursor["people_done"] = True
        project.job(fingerprint, cursor)
    tracker = Shuttle(models["shuttle"], doc.get("analysis_options", {}).get("gpu", False))
    background = None
    if tracker.config.get("bg_mode") == "concat":
        sample = open_capture(proxy, fps)
        images = []
        try:
            for i in range(32):
                if cancel():
                    raise InterruptedError("Cancelled during background estimation")
                sample.set(cv2.CAP_PROP_POS_MSEC, i*duration/32*1000)
                ok, image = sample.read()
                if ok:
                    images.append(cv2.cvtColor(cv2.resize(image, (512, 288)), cv2.COLOR_BGR2RGB))
            if not images:
                raise ValueError("Cannot read background frames")
            background = np.median(np.stack(images), axis=0).astype(np.uint8)
        finally:
            sample.release()
    capture = open_capture(proxy, fps)
    start_frame = int(cursor["shuttle_frame"])
    if start_frame:
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        if abs(capture.get(cv2.CAP_PROP_POS_FRAMES)-start_frame) > 0.5:
            capture.release()
            raise ValueError("Decoder cannot seek accurately for resume; prepare a new proxy")
    pending, indices, rows = [], [], []
    last_index = start_frame-1
    try:
        while True:
            ok, image = capture.read()
            if not ok:
                break
            index = last_index+1
            time = index/fps
            if cancel():
                raise InterruptedError("Cancelled; shuttle pass resumes at its last saved sequence")
            last_index = index
            pending.append(image)
            indices.append(index)
            if len(pending) == tracker.length:
                found = tracker.detect(pending, background)
                rows.extend((n, {"time": n/fps, "shuttle": s}) for n,s in zip(indices, found))
                pending, indices = [], []
                if len(rows) >= fps*5:
                    project.write_rows(fingerprint, "shuttle", rows)
                    cursor["shuttle_frame"] = rows[-1][0]+1
                    project.job(fingerprint, cursor)
                    rows.clear()
                    progress("shuttle", time/duration, "Temporal shuttle inference; microbatch one")
        if pending:
            count = len(pending)
            found = tracker.detect(pending + [pending[-1]]*(tracker.length-count), background)
            rows.extend((n, {"time": n/fps, "shuttle": s}) for n,s in zip(indices, found[:count]))
        project.write_rows(fingerprint, "shuttle", rows)
        if rows:
            cursor["shuttle_frame"] = rows[-1][0]+1
        project.job(fingerprint, cursor)
        if last_index+1 < max(1, (duration-1)*fps):
            raise ValueError("Review video decoding stopped early during shuttle pass")
    finally:
        capture.release()
        del tracker
    player_rows = iter(project.rows(fingerprint, "players"))
    current = next(player_rows, (0, {"time": 0, "players": [], "noise": []}))[1]
    following = next(player_rows, None)
    def joined():
        nonlocal current, following
        for _, observation in project.rows(fingerprint, "shuttle"):
            while following and following[1]["time"] <= observation["time"]:
                current = following[1]
                following = next(player_rows, None)
            fresh = observation["time"]-current["time"] < 0.2
            yield {**observation, "players": current["players"] if fresh else [], "noise": current.get("noise", [])}
    inferred = infer_rallies(joined(), duration, court, doc.get("analysis_options", {}).get("auto_accept", False))
    # Settings changed during inference: keep observations but never merge stale proposals.
    latest = project.read()
    for key in ("calibration", "anchors", "reanchors", "models", "analysis_options", "discipline"):
        if latest.get(key) != doc.get(key):
            raise ValueError("Settings changed during analysis; observations saved, proposals not applied")
    project.write_rows(fingerprint, "contacts", [(i, e) for i,e in enumerate(inferred["contacts"])])
    summary = {"run": fingerprint, "points": len(inferred["points"]), "contacts": len(inferred["contacts"]),
               "serves": len(inferred["serves"]), "status": "experimental_proposals"}
    project.merge_proposals(inferred["points"], summary)
    (project.path/"analysis-report.json").write_text(json.dumps(inferred, indent=2), encoding="utf-8")
    cursor["finished"] = True
    project.job(fingerprint, cursor)
    return {"run": fingerprint, "point_candidates": len(inferred["points"]), "contacts": len(inferred["contacts"]),
            "notice": "Analysis saved. Review rally, hitter and winner proposals; experimental auto-awards remain unlocked."}
