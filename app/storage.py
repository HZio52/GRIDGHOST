"""SQLite audit store. Atomic timestamp check + belief update + decision insert."""
import json
import sqlite3
import uuid
from pathlib import Path
from .schemas import Belief, DecisionRequest, Policy, State
from .engine import decide

class Conflict(Exception): pass

class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, policy TEXT NOT NULL,
              belief TEXT NOT NULL, last_timestamp REAL);
            CREATE TABLE IF NOT EXISTS decisions (
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
              timestamp REAL NOT NULL, input TEXT NOT NULL, output TEXT NOT NULL,
              UNIQUE(run_id,timestamp), FOREIGN KEY(run_id) REFERENCES runs(id));
            ''')
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c
    def create(self, request):
        run_id = str(uuid.uuid4())
        with self.connect() as c:
            c.execute('INSERT INTO runs VALUES (?,?,?,?,NULL)',
                      (run_id, request.name, request.policy.model_dump_json(), Belief().model_dump_json()))
        return self.get(run_id)
    def get(self, run_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None: raise KeyError(run_id)
        result = dict(row)
        for k in ('policy', 'belief'): result[k] = json.loads(result[k])
        return result
    def step(self, run_id, state: State):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if row is None: raise KeyError(run_id)
            if row['last_timestamp'] is not None and state.timestamp_s <= row['last_timestamp']:
                raise Conflict('Timestamp must strictly increase; duplicate/out-of-order update rejected')
            output = decide(DecisionRequest(state=state, policy=Policy.model_validate_json(row['policy']),
                            belief=Belief.model_validate_json(row['belief'])))
            c.execute('INSERT INTO decisions (run_id,timestamp,input,output) VALUES (?,?,?,?)',
                      (run_id, state.timestamp_s, state.model_dump_json(), output.model_dump_json()))
            c.execute('UPDATE runs SET belief=?, last_timestamp=? WHERE id=?',
                      (output.belief.model_dump_json(), state.timestamp_s, run_id))
        return output
    def history(self, run_id, limit=100, offset=0):
        self.get(run_id)
        with self.connect() as c:
            rows = c.execute('SELECT id,timestamp,input,output FROM decisions WHERE run_id=? '
                             'ORDER BY id LIMIT ? OFFSET ?', (run_id, limit, offset)).fetchall()
        return [{'id': r['id'], 'timestamp_s': r['timestamp'],
                 'input': json.loads(r['input']), 'output': json.loads(r['output'])} for r in rows]
