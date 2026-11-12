"""Authoring-only: execute on target PC, never on the authoring machine."""
from midminton.scoring import replay, snapshots
import pytest


def event(identity, time, winner=None, disposition="point_awarded", **extra):
    return dict(id=identity, time=time, winner=winner, disposition=disposition, **extra)


def document(events, **extra):
    return dict(events=events, checkpoints=[], rules=dict(target=21, margin=2, cap=30,
                initial=[0, 0], server="A", initial_server="P1", initial_receiver="P3"), **extra)


def test_insert_missed_point_replays_later_awards():
    doc = document([event("a", 1, "A"), event("b", 3, "B")])
    doc["events"].append(event("missed", 2, "A"))
    assert replay(doc, 3)["score"] == [2, 1]
    assert replay(doc, 1)["score"] == [1, 0]


def test_unknown_taints_later_score_and_checkpoint_restores_certainty():
    doc = document([event("gap", 1, disposition="point_pending"), event("b", 2, "B")])
    assert replay(doc, 2)["provisional"]
    doc["checkpoints"] = [dict(id="cp", time=3, score=[1, 1], game=1, server="A")]
    assert not replay(doc, 3)["provisional"]
    assert replay(doc, 3)["score"] == [1, 1]


def test_replay_awards_neither_side():
    assert replay(document([event("let", 1, disposition="replay/no_point")]), 2)["score"] == [0, 0]


def test_pending_winner_and_unknown_boundary_are_independent():
    doc = document([event("a", 2, "A", end_time=None, boundary_status="unresolved")])
    assert replay(doc, 3)["score"] == [1, 0]


def test_game_transition_and_final_winner():
    doc = document([event(str(i), i + 1, "A") for i in range(21)])
    state = replay(doc, 21)
    assert state["completed_games"] == [[21, 0]]
    assert state["score"] == [21, 0]
    assert state["game_over"]


def test_same_timestamp_has_stable_order_and_snapshots():
    doc = document([event("b", 1, "B"), event("a", 1, "A")])
    assert snapshots(doc)[-1]["state"]["score"] == [1, 1]


def test_checkpoint_conflict_is_visible():
    doc = document([event("a", 1, "A")])
    doc["checkpoints"] = [dict(id="cp", time=2, score=[9, 9], game=1, server="B")]
    assert replay(doc, 2)["conflicts"]


def test_doubles_server_positions_and_game_transition_uncertainty():
    doc = document([event("a", 1, "A"), event("b", 2, "B")], discipline="doubles")
    assert replay(doc, 1)["serving_player"] == "P1"
    assert replay(doc, 2)["serving_player"] == "P4"
    doc["events"] = [event(str(i), i+1, "A") for i in range(22)]
    state = replay(doc, 22)
    assert state["game"] == 2
    assert state["serving_player"] is None


def test_cap_ends_at_thirty_and_deuce_requires_margin():
    doc = document([event("a", 1, "A")])
    doc["rules"]["initial"] = [20, 20]
    assert not replay(doc, 1)["game_over"]
    doc["rules"]["initial"] = [29, 29]
    assert replay(doc, 1)["score"] == [30, 29]
    assert replay(doc, 1)["game_over"]


def test_invalid_fractional_score_and_nonfinite_time_are_rejected():
    doc = document([])
    doc["rules"]["initial"] = [1.5, 0]
    with pytest.raises(ValueError):
        replay(doc, 0)
    with pytest.raises(ValueError):
        replay(document([event("x", float("nan"), "A")]), 2)


def test_end_only_point_is_rejected_for_export_visibility():
    doc = document([event("x", 10, "A")])
    doc["media"] = {"duration": 10}
    with pytest.raises(ValueError, match="visible"):
        replay(doc, 10)


def test_end_only_checkpoint_is_also_rejected():
    doc = document([])
    doc["media"] = {"duration": 10}
    doc["checkpoints"] = [dict(id="cp", time=10, score=[2, 1], game=1, server="A")]
    with pytest.raises(ValueError, match="visible"):
        replay(doc, 10)
