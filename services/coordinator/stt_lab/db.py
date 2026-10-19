"""Small transactional store. Migrations are numbered, atomic and additive."""

import contextlib
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE recordings (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, source_sha256 TEXT NOT NULL UNIQUE,
 source_path TEXT NOT NULL, asset_path TEXT NOT NULL, asset_sha256 TEXT NOT NULL,
 duration REAL NOT NULL, language TEXT NOT NULL DEFAULT 'en', tags TEXT NOT NULL DEFAULT '[]',
 metadata TEXT NOT NULL, reference_revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE reference_revisions (
 recording_id TEXT NOT NULL REFERENCES recordings(id), revision INTEGER NOT NULL,
 text TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('draft','verified')), created_at TEXT NOT NULL,
 PRIMARY KEY(recording_id,revision));
CREATE TABLE models (id TEXT PRIMARY KEY, manifest TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE experiments (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, target TEXT NOT NULL CHECK(target IN ('mac','iphone')),
 state TEXT NOT NULL, settings TEXT NOT NULL, seed INTEGER NOT NULL,
 created_at TEXT NOT NULL, finalized_at TEXT);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id),
 recording_id TEXT NOT NULL REFERENCES recordings(id), model_id TEXT NOT NULL REFERENCES models(id),
 repetition INTEGER NOT NULL, state TEXT NOT NULL, snapshot TEXT NOT NULL,
 lease_owner TEXT, lease_until REAL, device_id TEXT, error TEXT, created_at TEXT NOT NULL,
 UNIQUE(experiment_id,recording_id,model_id,repetition));
CREATE TABLE attempts (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), state TEXT NOT NULL,
 started_at TEXT NOT NULL, ended_at TEXT, error TEXT);
CREATE TABLE outputs (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id), attempt_id TEXT NOT NULL REFERENCES attempts(id),
 text TEXT NOT NULL, measurements TEXT NOT NULL, provenance TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE evaluations (
 id TEXT PRIMARY KEY, output_id TEXT NOT NULL REFERENCES outputs(id),
 reference_revision INTEGER NOT NULL, reference_text TEXT NOT NULL, version TEXT NOT NULL,
 scores TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE reviews (
 id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id), recording_id TEXT NOT NULL,
 seed INTEGER NOT NULL, mapping TEXT NOT NULL, ratings TEXT NOT NULL DEFAULT '{}', locked INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE devices (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, details TEXT NOT NULL,
 last_seen TEXT NOT NULL);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
 detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE profiling_artifacts (id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id),
 name TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, measurement_kind TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX jobs_claim ON jobs(state,lease_until);
CREATE INDEX jobs_experiment ON jobs(experiment_id);
CREATE INDEX evaluations_output ON evaluations(output_id);
"""


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Database:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "lab.sqlite3"
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                version = 1
            if version == 1:
                conn.execute(
                    "CREATE TABLE evaluation_snapshots(id TEXT PRIMARY KEY,experiment_id TEXT NOT NULL REFERENCES experiments(id),version TEXT NOT NULL,created_at TEXT NOT NULL)"
                )
                conn.execute(
                    "ALTER TABLE evaluations ADD COLUMN snapshot_id TEXT REFERENCES evaluation_snapshots(id)"
                )
                conn.execute("PRAGMA user_version=2")
            elif version != 2:
                raise RuntimeError(
                    f"Unsupported database version {version}; do not downgrade this application"
                )

    @contextlib.contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
