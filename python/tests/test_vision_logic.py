from midminton.vision.logic import Roster, infer_rallies
from midminton.vision.geometry import Court


def test_foreground_person_does_not_replace_occluded_player():
    roster = Roster([{"id": "P1", "box": [0.1, 0.1, 0.2, 0.5], "team": "A"}])
    first = roster.update(0, [{"box": [0.1, 0.1, 0.2, 0.5], "appearance": [10, 10, 10]}])
    crossed = roster.update(0.1, [{"box": [0, 0, 0.95, 1], "appearance": [10, 10, 10]}])
    assert first["players"][0]["id"] == "P1"
    assert crossed["players"][0]["visibility"] != "observed"
    assert crossed["noise"]


def test_disappearance_is_not_automatic_point_award():
    observations = [{"time": i / 30, "shuttle": {"xy": [0.1 + i / 200, 0.2], "confidence": 0.9}, "players": []}
                    for i in range(30)]
    result = infer_rallies(observations, duration=5)
    assert all(point["winner"] is None for point in result["points"])


def test_missing_shuttle_does_not_create_auto_award_even_when_enabled():
    rows = [{"time": i/30, "shuttle": {"xy": [0.1+i/100, 0.2], "confidence": 0.9}} for i in range(30)]
    rows += [{"time": 1+i/30, "shuttle": None} for i in range(120)]
    result = infer_rallies(rows, 5, auto_accept=True)
    assert result["points"]
    assert all(p["disposition"] == "point_pending" for p in result["points"])


def test_long_occlusion_requires_timed_reanchor():
    anchor = {"id": "P1", "box": [0.1, 0.1, 0.2, 0.5], "team": "A"}
    detection = {"box": anchor["box"], "appearance": [10, 10, 10]}
    roster = Roster([anchor])
    roster.update(0, [detection])
    assert roster.update(2, [detection])["players"][0]["visibility"] == "occluded"
    roster.reanchor(anchor)
    assert roster.update(2.1, [detection])["players"][0]["visibility"] == "observed"


def test_established_player_can_step_outside_court_without_becoming_spectator():
    court = Court([[0.2, 0.9], [0.8, 0.9], [0.8, 0.2], [0.2, 0.2]])
    anchor = {"id": "P1", "box": [0.2, 0.4, 0.3, 0.8], "team": "A"}
    roster = Roster([anchor], court)
    for index in range(7):
        x = 0.2-index*0.03
        result = roster.update(index/10, [{"box": [x, 0.4, x+0.1, 0.8], "appearance": [10, 10, 10]}])
    assert result["players"][0]["visibility"] == "observed"


def test_prior_outsider_cannot_take_over_player_on_crossing():
    anchor = {"id": "P1", "box": [0.4, 0.2, 0.5, 0.6], "team": "A"}
    roster = Roster([anchor])
    for index in range(5):
        x = 0.1+index*0.075
        outsider = {"box": [x, 0.2, x+0.1, 0.6], "appearance": [10, 10, 10]}
        actual = {"box": anchor["box"], "appearance": [10, 10, 10]}
        result = roster.update(index/10, [actual, outsider] if index < 4 else [outsider])
    assert result["players"][0]["visibility"] != "observed"
    assert result["noise"]
