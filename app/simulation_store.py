"""Append-only archive of event scenarios, isolated from the institutional ledger."""
from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from backend.dynamics.runtime.simulation import digest, SimulationError


class ScenarioStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS scenarios (case_id TEXT, id TEXT, payload TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(case_id,id))')
            for verb in ('UPDATE', 'DELETE'):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS no_{verb.lower()} BEFORE {verb} ON scenarios BEGIN SELECT RAISE(ABORT, 'Scenarios are immutable'); END")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, model, graph, result, evidence):
        payload = dict(result=result, graph=graph, mapping=model.mapping, evidence=evidence)
        self._record(model.case_id, result['id'], payload)

    def record_graph(self, simulation, result, evidence):
        payload = dict(result=result, transitionInputs=simulation.inputs, evidence=evidence)
        self._record(simulation.case_id, result['id'], payload)

    def _record(self, case_id, identity, payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        checksum = digest(payload)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO scenarios VALUES (?,?,?,?)', (case_id, identity, encoded, checksum))
            saved = db.execute('SELECT hash FROM scenarios WHERE case_id=? AND id=?', (case_id, identity)).fetchone()
            if saved[0] != checksum:
                raise SimulationError('The archived scenario identity conflicts with its recorded contents.')

    def read(self, case_id, identity):
        with self.connect() as db:
            row = db.execute('SELECT payload,hash FROM scenarios WHERE case_id=? AND id=?', (case_id, identity)).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if digest(payload) != row[1]:
            raise SimulationError('The archived scenario failed its integrity check.')
        return payload
