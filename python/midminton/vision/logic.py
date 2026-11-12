"""Conservative proposals. Quality values are heuristics, not probabilities."""
from collections import deque
from copy import deepcopy
from math import dist


def center(box):
    return [(box[0]+box[2])/2, (box[1]+box[3])/2]


def area(box):
    return max(1e-6, (box[2]-box[0])*(box[3]-box[1]))


def overlap(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))


def nearest_hitter(players, xy):
    ranked = []
    for player in players:
        if player["visibility"] != "observed":
            continue
        a, b, c, d = player["box"]
        distance = dist(xy, [min(c, max(a, xy[0])), min(d, max(b, xy[1]))])
        ranked.append((distance, player["id"], player["team"]))
    ranked.sort()
    if not ranked or ranked[0][0] > 0.07 or (len(ranked) > 1 and ranked[1][0]-ranked[0][0] < 0.04):
        return None
    return ranked[0]


class Roster:
    def __init__(self, anchors, court=None):
        self.players = {a["id"]: {**deepcopy(a), "last_seen": -1, "appearance": None} for a in anchors}
        self.court = court
        self.outsiders = []

    def reanchor(self, anchor):
        self.players[anchor["id"]] = {**deepcopy(anchor), "last_seen": -1, "appearance": None}
        self.outsiders = [p for p in self.outsiders if overlap(p["box"], anchor["box"]) == 0]

    def update(self, time, detections):
        noise, usable, obscured = [], [], set()
        self.outsiders = [p for p in self.outsiders if time-p["time"] < 1.0]
        for detection in detections:
            box = detection["box"]
            outside = self.court and not self.court.contains([(box[0]+box[2])/2, box[3]])
            crossing = area(box) > 0.38 or box[3]-box[1] > 0.85
            continuing = any(p["last_seen"] >= 0 and time-p["last_seen"] <= 0.8 and
                             dist(center(p["box"]), center(box)) < 0.08 and
                             0.60 < area(box)/area(p["box"]) < 1.65 and
                             dist(p.get("appearance") or [0]*3, detection.get("appearance", [0]*3)) < 70
                             for p in self.players.values())
            known_outsider = any(dist(center(box), center(p["box"])) < 0.10 and
                                 dist(detection.get("appearance", [0]*3), p.get("appearance", [0]*3)) < 70
                                 for p in self.outsiders)
            if crossing or known_outsider or (outside and not continuing):
                role = "background_person" if outside and not crossing else "unknown_person"
                noise.append({**detection, "role": role, "occlusion_type": "foreground_crossing" if crossing or known_outsider else "none"})
                for identity, player in self.players.items():
                    if overlap(player["box"], box)/area(player["box"]) > 0.25:
                        obscured.add(identity)
            else:
                usable.append(detection)
        for identity, player in self.players.items():
            for detection in detections:
                box = detection["box"]
                if overlap(player["box"], box)/area(player["box"]) > 0.6 and area(box) > area(player["box"])*1.5:
                    obscured.add(identity)
        pairs = []
        for identity, player in self.players.items():
            if identity in obscured:
                continue
            gap = max(0, time-player["last_seen"])
            if player["last_seen"] >= 0 and gap > 0.8:
                continue
            for index, detection in enumerate(usable):
                location = dist(center(player["box"]), center(detection["box"]))
                appearance = 0 if player["appearance"] is None else dist(player["appearance"], detection.get("appearance", [0]*3))/442
                size_ratio = area(detection["box"])/area(player["box"])
                limit = 0.12 if player["last_seen"] < 0 else min(0.08, 0.018+gap*0.35)
                if location <= limit and appearance < 0.20 and 0.60 < size_ratio < 1.65:
                    pairs.append((location + appearance * 0.5, identity, index))
        assigned, used = set(), set()
        for cost, identity, index in sorted(pairs):
            if identity in assigned or index in used:
                continue
            alternatives = [p[0] for p in pairs if (p[1] == identity and p[2] != index) or (p[2] == index and p[1] != identity)]
            if alternatives and min(alternatives) - cost < 0.018:
                continue
            player = self.players[identity]
            player.update(box=usable[index]["box"], appearance=usable[index].get("appearance"), last_seen=time)
            assigned.add(identity)
            used.add(index)
        result = [{"id": identity, "team": p["team"], "box": p["box"],
                   "court_xy": self.court.foot(p["box"]) if self.court else None,
                   "visibility": "observed" if identity in assigned else "occluded", "role": "active_player"}
                  for identity, p in self.players.items()]
        noise += [{**detection, "role": "unknown_person", "occlusion_type": "identity_ambiguous"}
                  for i, detection in enumerate(usable) if i not in used]
        self.outsiders = [{**d, "time": time} for d in noise] + self.outsiders[:24]
        return {"time": time, "players": result, "noise": noise}


def infer_rallies(observations, duration, court=None, auto_accept=False):
    """Motion windows, reversal contacts and optional corroborated winner proposals.

    Disappearance alone never awards a point. Court projection is only a terminal
    hypothesis: it needs a stationary visible shuttle AND the next serve team.
    Even corroborated awards are experimental, unlocked and opt-in.
    """
    points, contacts, serves = [], [], []
    previous = None
    moving_since, last_motion, rally_start = None, None, None
    still_since, last_contact, contaminated = None, -100.0, False
    tail = deque(maxlen=24)
    held_by, held_count, burst_server = None, 0, None
    terminal = None
    for row in observations:
        time, shuttle = row["time"], row.get("shuttle")
        noisy = any(p.get("role") != "background_person" for p in row.get("noise", []))
        if noisy or not shuttle or not previous or not previous.get("shuttle") or time-previous["time"] >= 0.15:
            held_by, held_count, still_since = None, 0, None
        if noisy and rally_start is not None:
            contaminated = True
        if shuttle and previous and previous.get("shuttle"):
            dt = time-previous["time"]
            speed = dist(shuttle["xy"], previous["shuttle"]["xy"])/dt if 0 < dt < 0.15 else 0
            hitter = None if noisy else nearest_hitter(row.get("players", []), shuttle["xy"])
            if speed < 0.035 and hitter and shuttle.get("confidence", 0) >= 0.8:
                held_count = held_count+1 if held_by == hitter[2] else 1
                held_by = hitter[2]
            elif speed <= 0.10:
                held_by, held_count = None, 0
            if speed > 0.10:
                terminal = None
                if moving_since is None:
                    moving_since = time
                    burst_server = held_by if held_count >= 3 and still_since is not None and time-still_since >= 0.7 else None
                still_since = None
                held_count = 0
                last_motion = time
                if rally_start is None and time-moving_since >= 0.35:
                    rally_start, contaminated = moving_since, noisy
                    if burst_server:
                        serves.append({"time": moving_since, "team": burst_server, "evidence": "held_shuttle_then_motion"})
                        if points and not points[-1].get("contaminated") and points[-1].get("terminal_winner") == burst_server:
                            points[-1].update(suggested_winner=burst_server, evidence="stationary_court_candidate_and_next_serve")
                            if auto_accept:
                                points[-1].update(winner=burst_server, disposition="point_awarded", experimental=True)
            else:
                moving_since = None
                if still_since is None:
                    still_since = time
            older = previous.get("velocity")
            velocity = [(shuttle["xy"][i]-previous["shuttle"]["xy"][i])/max(dt, 0.001) for i in range(2)]
            row["velocity"] = velocity
            if older and time-last_contact >= 0.18:
                norm = (sum(v*v for v in velocity)*sum(v*v for v in older))**0.5
                if norm > 0.02 and sum(a*b for a,b in zip(velocity, older))/norm < 0.1:
                    contacts.append(dict(time=time, hitter=hitter[1] if hitter else None, team=hitter[2] if hitter else None,
                                         evidence="trajectory_reversal", quality="proposal", contaminated=noisy))
                    last_contact = time
            tail.append((time, shuttle["xy"], shuttle.get("confidence", 0)))
            if court and rally_start is not None and still_since is not None and time-still_since > 0.6 and not noisy:
                stable = [p for t,p,c in tail if time-t < 0.5 and c > 0.8]
                mapped = court.project(shuttle["xy"])
                if len(stable) >= 6 and max(dist(p, stable[0]) for p in stable) < 0.018 and mapped and all(0.04 < v < 0.96 for v in mapped):
                    landing_side = 0 if mapped[1] < 0.5 else 1
                    teams = [(p["team"], court.foot(p["box"])) for p in row.get("players", []) if p["visibility"] == "observed"]
                    losers = {team for team, xy in teams if xy and (0 if xy[1] < 0.5 else 1) == landing_side}
                    if len(losers) == 1:
                        terminal = "B" if losers.pop() == "A" else "A"
        if rally_start is not None and last_motion is not None and time-last_motion > 2.5:
            points.append(dict(id=f"rally-{round(rally_start*1000)}", time=last_motion,
                               start=rally_start, end_time=None, end_window=[last_motion, time],
                               boundary_status="unresolved", winner=None, disposition="point_pending", terminal_winner=terminal, contaminated=contaminated,
                               evidence="motion_then_rest_or_tracking_loss"))
            rally_start, moving_since, terminal = None, None, None
        previous = row
    if rally_start is not None:
        points.append(dict(id=f"rally-{round(rally_start*1000)}", time=max(0, min(last_motion or rally_start, duration-0.1)), start=rally_start,
                           end_time=None, end_window=[last_motion or rally_start, duration],
                           winner=None, disposition="point_pending", boundary_status="unresolved", contaminated=contaminated, evidence="final_window"))
    return {"points": points, "contacts": contacts, "serves": serves}
