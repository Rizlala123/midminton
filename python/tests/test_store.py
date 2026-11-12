from midminton.store import Project
import pytest


def test_undo_redo_and_optimistic_revision(tmp_path):
    project = Project(tmp_path)
    project.create({"events": [], "checkpoints": [], "rules": {}})
    original = project.read()
    changed = project.edit("point", {"time": 2, "winner": "A"}, original["revision"])
    assert len(changed["events"]) == 1
    with pytest.raises(ValueError, match="changed"):
        project.edit("point", {"time": 3, "winner": "B"}, original["revision"])
    assert not project.history(-1)["events"]
    assert len(project.history(1)["events"]) == 1


def test_ai_merge_preserves_manual_locks_and_is_idempotent(tmp_path):
    project = Project(tmp_path)
    project.create({"events": [], "checkpoints": [], "rules": {}})
    project.edit("point", {"id": "r1", "time": 1, "winner": "A"}, 0)
    project.merge_proposals([dict(id="r1", time=1, winner="B", disposition="point_awarded")])
    assert project.read()["events"][0]["winner"] == "A"
    project.merge_proposals([dict(id="r2", time=2, winner=None, disposition="point_pending")])
    project.merge_proposals([dict(id="r2", time=2, winner=None, disposition="point_pending")])
    assert len(project.read()["events"]) == 2


def test_shifted_rally_preserves_manual_evidence_and_deleted_windows(tmp_path):
    project = Project(tmp_path)
    project.create({"events": [], "checkpoints": [], "rules": {}})
    project.merge_proposals([dict(id="old", start=2, time=10, end_window=[10, 12], winner=None, disposition="point_pending")])
    doc = project.read()
    saved = project.edit("point", {"id": "old", "time": 11, "winner": "A", "disposition": "point_awarded"}, doc["revision"])
    assert saved["events"][0]["end_window"] == [10, 12]
    project.merge_proposals([dict(id="shifted", start=2.2, time=10.3, winner=None, disposition="point_pending")])
    assert len(project.read()["events"]) == 1
    project.edit("delete", {"id": "old"}, project.read()["revision"])
    project.merge_proposals([dict(id="another", start=2.1, time=10.1, winner=None, disposition="point_pending")])
    assert not project.read()["events"]


def test_undo_fork_and_streaming_observation_upsert(tmp_path):
    project = Project(tmp_path)
    project.create({"events": [], "checkpoints": [], "rules": {}})
    project.edit("point", {"id": "a", "time": 1, "winner": "A"}, 0)
    project.history(-1)
    project.edit("point", {"id": "b", "time": 2, "winner": "B"}, project.read()["revision"])
    assert [e["id"] for e in project.history(1)["events"]] == ["b"]
    project.write_rows("run", "shuttle", [(0, {"time": 0}), (1, {"time": 1})])
    project.write_rows("run", "shuttle", [(1, {"time": 1, "updated": True})])
    rows = list(project.rows("run", "shuttle"))
    assert len(rows) == 2
    assert rows[-1][1]["updated"]
