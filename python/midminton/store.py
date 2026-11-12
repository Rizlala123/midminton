"""Transactional project state, revision checks and undo without losing raw evidence."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time
import uuid
from .scoring import finite_time, validate_document


class Project:
    def __init__(self, directory):
        self.path = Path(directory).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.database = self.path / "project.sqlite3"

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.database, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def create(self, document):
        document = {"events": [], "checkpoints": [], "rules": {}, **document, "revision": 0}
        validate_document(document)
        with self.connection() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history (position INTEGER PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, time REAL, operation TEXT, data TEXT);
                CREATE TABLE IF NOT EXISTS observations (run TEXT, stage TEXT, frame INTEGER, data TEXT,
                    PRIMARY KEY(run,stage,frame));
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            """)
            if con.execute("SELECT 1 FROM state").fetchone():
                raise ValueError("Project already exists")
            data = json.dumps(document, allow_nan=False)
            con.execute("INSERT INTO state VALUES(1,?)", (data,))
            con.execute("INSERT INTO state VALUES(2,'0')")
            con.execute("INSERT INTO history VALUES(0,?)", (data,))
        return document

    def read(self):
        with self.connection() as con:
            row = con.execute("SELECT data FROM state WHERE id=1").fetchone()
            if row is None:
                raise ValueError("Not a Midminton project")
            return json.loads(row[0])

    @staticmethod
    def _write(con, doc, operation):
        validate_document(doc)
        old = json.loads(con.execute("SELECT data FROM state WHERE id=1").fetchone()[0])
        if doc == old:
            return old
        doc["revision"] = old["revision"] + 1
        cursor = int(con.execute("SELECT data FROM state WHERE id=2").fetchone()[0]) + 1
        data = json.dumps(doc, allow_nan=False)
        con.execute("DELETE FROM history WHERE position>=?", (cursor,))
        con.execute("INSERT INTO history VALUES(?,?)", (cursor, data))
        con.execute("UPDATE state SET data=? WHERE id=1", (data,))
        con.execute("UPDATE state SET data=? WHERE id=2", (str(cursor),))
        con.execute("INSERT INTO audit(time,operation,data) VALUES(?,?,?)", (time.time(), operation, data))
        return doc

    def edit(self, operation, payload, expected_revision):
        with self.connection() as con:
            doc = json.loads(con.execute("SELECT data FROM state WHERE id=1").fetchone()[0])
            if doc["revision"] != expected_revision:
                raise ValueError("Project changed; reload before applying this edit")
            if operation in {"point", "checkpoint"}:
                key = "events" if operation == "point" else "checkpoints"
                existing = next((e for e in doc[key] if e["id"] == payload.get("id")), {})
                item = {**existing, **payload}
                item["id"] = item.get("id") or uuid.uuid4().hex
                item["time"] = finite_time(item["time"])
                item.update(origin="manual", locked=True)
                if operation == "point":
                    item.setdefault("disposition", "point_awarded" if item.get("winner") else "point_pending")
                doc[key] = [e for e in doc[key] if e["id"] != item["id"]] + [item]
            elif operation == "delete":
                # Tombstones prevent a later analysis from resurrecting deleted proposals.
                doc["deleted_ids"] = sorted(set(doc.get("deleted_ids", [])) | {payload["id"]})
                deleted = next((e for e in doc["events"] if e["id"] == payload["id"]), None)
                if deleted:
                    doc.setdefault("deleted_windows", []).append({"start": deleted.get("start", deleted["time"]),
                        "time": deleted["time"], "end_window": deleted.get("end_window", [deleted["time"], deleted["time"]])})
                for key in ("events", "checkpoints"):
                    doc[key] = [e for e in doc[key] if e["id"] != payload["id"]]
            elif operation == "settings":
                allowed = {"rules", "calibration", "anchors", "reanchors", "discipline", "models", "analysis_options"}
                if set(payload) - allowed:
                    raise ValueError("Unsupported settings key")
                doc.update(payload)
            else:
                raise ValueError("Unknown edit operation")
            return self._write(con, doc, operation)

    def history(self, direction):
        if direction not in {-1, 1}:
            raise ValueError("History direction must be -1 or 1")
        with self.connection() as con:
            cursor = int(con.execute("SELECT data FROM state WHERE id=2").fetchone()[0])
            row = con.execute("SELECT data FROM history WHERE position=?", (cursor + direction,)).fetchone()
            current = json.loads(con.execute("SELECT data FROM state WHERE id=1").fetchone()[0])
            if not row:
                return current
            doc = json.loads(row[0])
            doc["revision"] = current["revision"] + 1
            data = json.dumps(doc, allow_nan=False)
            con.execute("UPDATE state SET data=? WHERE id=1", (data,))
            con.execute("UPDATE state SET data=? WHERE id=2", (str(cursor + direction),))
            con.execute("INSERT INTO audit(time,operation,data) VALUES(?,?,?)", (time.time(), "history", data))
            return doc

    def merge_proposals(self, proposals, summary=None):
        with self.connection() as con:
            doc = json.loads(con.execute("SELECT data FROM state WHERE id=1").fetchone()[0])
            events = {e["id"]: e for e in doc["events"]}
            # Replace superseded unlocked AI windows, retaining all historical
            # observations/audit snapshots. Never duplicate a manually reviewed rally.
            events = {key: value for key, value in events.items() if value.get("locked") or value.get("origin") != "model"}
            for proposal in proposals:
                identity = proposal["id"]
                if identity in doc.get("deleted_ids", []) or events.get(identity, {}).get("locked"):
                    continue
                windows = list(events.values()) + doc.get("deleted_windows", [])
                if any((e.get("locked") or "id" not in e) and self._same_rally(e, proposal) for e in windows):
                    continue
                events[identity] = {**proposal, "origin": "model", "locked": False}
            doc["events"] = list(events.values())
            if summary:
                doc["analysis"] = summary
            return self._write(con, doc, "analysis_merge")

    @staticmethod
    def _same_rally(a, b):
        if abs(a["time"]-b["time"]) < 0.5:
            return True
        if "start" not in a or "start" not in b:
            return False
        end_a, end_b = a.get("end_window", [a["time"]])[-1], b.get("end_window", [b["time"]])[-1]
        intersection = min(end_a, end_b)-max(a["start"], b["start"])
        shortest = min(end_a-a["start"], end_b-b["start"])
        return shortest > 0 and intersection/shortest > 0.7

    def write_rows(self, run, stage, rows):
        with self.connection() as con:
            con.executemany("INSERT OR REPLACE INTO observations VALUES(?,?,?,?)",
                            [(run, stage, frame, json.dumps(data, allow_nan=False)) for frame, data in rows])

    def rows(self, run, stage, start=0):
        # A read cursor streams rows, avoiding a decoded full-match array.
        con = sqlite3.connect(self.database)
        try:
            for frame, data in con.execute("SELECT frame,data FROM observations WHERE run=? AND stage=? AND frame>=? ORDER BY frame", (run, stage, start)):
                yield frame, json.loads(data)
        finally:
            con.close()

    def job(self, identity, data=None):
        with self.connection() as con:
            if data is not None:
                con.execute("INSERT OR REPLACE INTO jobs VALUES(?,?)", (identity, json.dumps(data)))
            row = con.execute("SELECT data FROM jobs WHERE id=?", (identity,)).fetchone()
            return json.loads(row[0]) if row else None
