"""Deterministic score state shared by the desktop preview and video export."""
from bisect import bisect_right
from copy import deepcopy
import math


def finite_time(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Time must be a finite, non-negative number")
    return value


def validate_document(doc):
    rules = doc.get("rules", {})
    target, margin, cap = (rules.get(k, d) for k, d in (("target", 21), ("margin", 2), ("cap", 30)))
    if any(type(v) is not int for v in (target, margin, cap)) or not 1 <= target <= cap <= 999 or not 1 <= margin <= 10:
        raise ValueError("Invalid scoring rules")
    initial = rules.get("initial", [0, 0])
    if len(initial) != 2 or any(type(x) is not int or not 0 <= x <= cap for x in initial):
        raise ValueError("Starting scores must be integers within the scoring cap")
    server = rules.get("server", "A")
    if server not in {"A", "B"}:
        raise ValueError("Serving team must be A or B")
    for key, team in (("initial_server", server), ("initial_receiver", "B" if server == "A" else "A")):
        if key in rules and rules[key] not in ({"P1", "P2"} if team == "A" else {"P3", "P4"}):
            raise ValueError(f"{key} must belong to team {team}")
    if doc.get("discipline", "auto") not in {"auto", "singles", "doubles"}:
        raise ValueError("Unknown match type")
    anchors = doc.get("anchors", [])
    roster = {}
    for anchor in anchors + doc.get("reanchors", []):
        identity, team, box = anchor["id"], anchor["team"], anchor["box"]
        key = (identity, finite_time(anchor.get("time", 0)))
        if key in roster or identity not in {"P1", "P2", "P3", "P4"} or team != ("A" if identity in {"P1", "P2"} else "B"):
            raise ValueError("Roster IDs must be unique and match their team")
        if len(box) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in box) or box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("Player boxes must have positive normalized dimensions")
        roster[key] = team
    if doc.get("calibration"):
        from .vision.geometry import Court
        Court(doc["calibration"])
    duration = doc.get("media", {}).get("duration", math.inf)
    ids = set()
    for event in doc.get("events", []):
        if not event.get("id") or event["id"] in ids:
            raise ValueError("Point IDs must be nonempty and unique")
        ids.add(event["id"])
        finite_time(event["time"])
        if event["time"] >= duration:
            raise ValueError("Point display time must be within visible video frames")
        kind = event.get("disposition", "point_pending")
        if kind not in {"point_awarded", "point_pending", "replay/no_point"}:
            raise ValueError("Unknown point disposition")
        if kind == "point_awarded" and event.get("winner") not in {"A", "B"}:
            raise ValueError("Awarded points need a winning team")
    for cp in doc.get("checkpoints", []):
        finite_time(cp["time"])
        if not cp.get("id") or cp["id"] in ids or cp["time"] >= duration:
            raise ValueError("Checkpoint needs a unique ID and a visible time before video end")
        ids.add(cp["id"])
        if len(cp["score"]) != 2 or any(type(x) is not int or not 0 <= x <= cap for x in cp["score"]):
            raise ValueError("Checkpoint score is outside the scoring rules")
        if cp.get("server") not in {"A", "B"} or type(cp.get("game", 1)) is not int or not 1 <= cp.get("game", 1) <= 99:
            raise ValueError("Checkpoint needs a server and valid game number")


def game_won(score, rules):
    return max(score) >= rules.get("target", 21) and (abs(score[0]-score[1]) >= rules.get("margin", 2) or max(score) >= rules.get("cap", 30))


def snapshots(doc):
    validate_document(doc)
    rules = doc.get("rules", {})
    score = list(rules.get("initial", [0, 0]))
    server = rules.get("server", "A")
    state = dict(score=score, trusted_score=list(score), game=1, server=server,
                 serving_player=rules.get("initial_server", "P1" if server == "A" else "P3"),
                 provisional=False, pending=[], conflicts=[], completed_games=[], game_over=game_won(score, rules))
    # Own-right/own-left positions are independent of camera direction.
    slots = {"A": ["P1", "P2"], "B": ["P3", "P4"]}
    service_uncertain = False
    serving = rules.get("initial_server", slots[server][0])
    receiving = rules.get("initial_receiver", slots["B" if server == "A" else "A"][0])
    for team, person in ((server, serving), ("B" if server == "A" else "A", receiving)):
        if person in slots[team] and slots[team][score[0 if team == "A" else 1] % 2] != person:
            slots[team].reverse()
    result = [{"time": 0.0, "state": deepcopy(state)}]
    entries = [(finite_time(e["time"]), 0, e["id"], e) for e in doc.get("events", [])]
    entries += [(finite_time(c["time"]), 1, c["id"], c) for c in doc.get("checkpoints", [])]
    for time, kind, identity, event in sorted(entries, key=lambda row: row[:3]):
        if kind == 1:
            if not state["provisional"] and (state["score"] != event["score"] or state["game"] != event.get("game", 1)):
                state["conflicts"].append(f"Checkpoint {identity} overrides a different reconstructed score")
            state.update(score=list(event["score"]), trusted_score=list(event["score"]),
                         game=int(event.get("game", 1)), server=event["server"],
                         serving_player=None, provisional=False, pending=[], game_over=game_won(event["score"], rules))
            # A score checkpoint alone does not reconstruct doubles player positions.
            if doc.get("discipline") == "doubles":
                state["conflicts"].append("Doubles serving player needs confirmation after checkpoint")
                service_uncertain = True
        elif event.get("disposition") == "point_pending":
            state["provisional"] = True
            state["pending"].append(identity)
        elif event.get("disposition") == "point_awarded":
            if state["game_over"]:
                state["game"] += 1
                state["score"] = [0, 0]
                state["game_over"] = False
                state["serving_player"] = None
                if doc.get("discipline") == "doubles":
                    service_uncertain = True
            winner = event["winner"]
            index = 0 if winner == "A" else 1
            state["score"][index] += 1
            if doc.get("discipline") == "doubles":
                if winner == state["server"]:
                    slots[winner].reverse()
                state["serving_player"] = None if service_uncertain else slots[winner][state["score"][index] % 2]
            else:
                state["serving_player"] = "P1" if winner == "A" else "P3"
            state["server"] = winner
            a, b = state["score"]
            won = game_won([a, b], rules)
            if won and not state["provisional"]:
                state["completed_games"].append([a, b])
                state["game_over"] = True
            if not state["provisional"]:
                state["trusted_score"] = list(state["score"])
        result.append({"time": time, "state": deepcopy(state)})
    return result


def replay(doc, time):
    timeline = snapshots(doc)
    index = max(0, bisect_right([entry["time"] for entry in timeline], finite_time(time)) - 1)
    return timeline[index]["state"]
