import json
import math
import random
import time
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .common import now, require, uid
from .db import Database, encode
from .evaluation import VERSION, score


class Settings(BaseModel):
    language_mode: Literal["auto", "forced"] = "auto"
    repetitions: int = Field(default=1, ge=1, le=100)
    warmups: int = Field(default=0, ge=0, le=20)
    temperature: float = Field(default=0, ge=0, le=1)
    max_new_tokens: int = Field(default=1024, ge=1, le=8192)
    timeout_seconds: int = Field(default=1800, ge=1, le=14400)
    allow_unsupported: bool = False


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    recording_ids: list[str] = Field(min_length=1, max_length=10000)
    model_ids: list[str] = Field(min_length=1, max_length=100)
    target: Literal["mac", "iphone"] = "mac"
    seed: int = Field(default=42, ge=0, le=2147483647)
    settings: Settings = Field(default_factory=Settings)


def experiment_view(conn, row):
    result = dict(row)
    result["settings"] = json.loads(result["settings"])
    result["counts"] = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT state,count(*) FROM jobs WHERE experiment_id=? GROUP BY state", (row["id"],)
        )
    }
    result["job_count"] = sum(result["counts"].values())
    return result


def list_experiments(db: Database):
    with db.connect() as conn:
        return [
            experiment_view(conn, r)
            for r in conn.execute("SELECT * FROM experiments ORDER BY created_at DESC")
        ]


def create_experiment(db: Database, value: ExperimentCreate, preview=False):
    jobs, exclusions = [], []
    experiment_id = uid()
    with db.transaction() as conn:
        for recording_id in dict.fromkeys(value.recording_ids):
            recording = dict(
                require(conn.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)).fetchone())
            )
            reference = conn.execute(
                "SELECT * FROM reference_revisions WHERE recording_id=? AND revision=?",
                (recording_id, recording["reference_revision"]),
            ).fetchone()
            if not reference or reference["status"] != "verified":
                raise HTTPException(422, f"Verified ground truth required: {recording['name']}")
            for model_id in dict.fromkeys(value.model_ids):
                row = require(
                    conn.execute("SELECT manifest FROM models WHERE id=?", (model_id,)).fetchone(),
                    "Install a verified checkpoint manifest before creating an experiment",
                )
                manifest = json.loads(row[0])
                languages = recording["language"].split("+")
                supported = all(lang in manifest["languages"] for lang in languages)
                if not supported and not value.settings.allow_unsupported:
                    exclusions.append(
                        {
                            "recording_id": recording_id,
                            "model_id": model_id,
                            "language": recording["language"],
                        }
                    )
                    continue
                if value.target == "iphone" and manifest["runtime"] not in ("whisperkit", "fluidaudio"):
                    raise HTTPException(422, "iPhone experiments require a native on-device adapter")
                snapshot = {
                    "reference": dict(reference),
                    "recording": {
                        k: recording[k]
                        for k in (
                            "id",
                            "name",
                            "asset_path",
                            "asset_sha256",
                            "source_sha256",
                            "language",
                            "duration",
                        )
                    },
                    "tags": json.loads(recording["tags"]),
                    "model": manifest,
                    "settings": value.settings.model_dump(),
                    "supported_language": supported,
                    "seed": value.seed,
                    "preprocessing": json.loads(recording["metadata"])["preprocessing"],
                }
                for repetition in range(value.settings.repetitions):
                    jobs.append((uid(), recording_id, model_id, repetition, snapshot))
        if not jobs:
            raise HTTPException(
                422,
                {
                    "message": "No compatible jobs; inspect language support and installed models",
                    "exclusions": exclusions,
                },
            )
        if preview:
            return {
                "job_count": len(jobs),
                "exclusions": exclusions,
                "recording_count": len(set(j[1] for j in jobs)),
            }
        random.Random(value.seed).shuffle(jobs)
        conn.execute(
            "INSERT INTO experiments VALUES(?,?,?,?,?,?,?,NULL)",
            (
                experiment_id,
                value.name,
                value.target,
                "draft",
                encode(value.settings.model_dump()),
                value.seed,
                now(),
            ),
        )
        for job_id, recording_id, model_id, repetition, snapshot in jobs:
            conn.execute(
                "INSERT INTO jobs(id,experiment_id,recording_id,model_id,repetition,state,snapshot,created_at) VALUES(?,?,?,?,?,'queued',?,?)",
                (job_id, experiment_id, recording_id, model_id, repetition, encode(snapshot), now()),
            )
        event(conn, "experiment.created", experiment_id, {"jobs": len(jobs), "exclusions": exclusions})
        return experiment_view(
            conn, conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        )


def event(conn, kind, entity_id, detail):
    conn.execute(
        "INSERT INTO events(kind,entity_id,detail,created_at) VALUES(?,?,?,?)",
        (kind, entity_id, encode(detail), now()),
    )


def action(db: Database, experiment_id: str, command: str):
    with db.transaction() as conn:
        row = require(conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone())
        if row["finalized_at"]:
            raise HTTPException(409, "Finalized experiments are immutable; create a new experiment")
        if command in ("start", "resume", "retry"):
            if command == "retry":
                conn.execute(
                    "UPDATE jobs SET state='queued',error=NULL WHERE experiment_id=? AND state='failed'",
                    (experiment_id,),
                )
            if command == "resume":
                conn.execute(
                    "UPDATE jobs SET state='queued',error=NULL WHERE experiment_id=? AND state='cancelled'",
                    (experiment_id,),
                )
            conn.execute("UPDATE experiments SET state='running' WHERE id=?", (experiment_id,))
        elif command == "pause":
            conn.execute("UPDATE experiments SET state='paused' WHERE id=?", (experiment_id,))
        elif command == "cancel":
            conn.execute("UPDATE experiments SET state='cancelled' WHERE id=?", (experiment_id,))
            conn.execute(
                "UPDATE jobs SET state='cancelled' WHERE experiment_id=? AND state IN ('queued','running')",
                (experiment_id,),
            )
            conn.execute(
                "UPDATE attempts SET state='cancelled',ended_at=? WHERE state='running' AND job_id IN (SELECT id FROM jobs WHERE experiment_id=?)",
                (now(), experiment_id),
            )
        elif command == "finalize":
            pending = conn.execute(
                "SELECT count(*) FROM jobs WHERE experiment_id=? AND state IN ('queued','running')",
                (experiment_id,),
            ).fetchone()[0]
            if pending:
                raise HTTPException(409, "Finish or cancel pending jobs before finalizing")
            conn.execute(
                "UPDATE experiments SET state='finalized',finalized_at=? WHERE id=?", (now(), experiment_id)
            )
        else:
            raise HTTPException(404, "Unknown experiment action")
        event(conn, "experiment." + command, experiment_id, {})
        return experiment_view(
            conn, conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        )


def claim_job(db: Database, owner: str, lease_seconds=120, device_id=None, installed_model_ids=None):
    with db.transaction() as conn:
        expired = conn.execute(
            "SELECT id FROM jobs WHERE state='running' AND lease_until<?", (time.time(),)
        ).fetchall()
        for row in expired:
            conn.execute(
                "UPDATE attempts SET state='interrupted',ended_at=?,error='Lease expired' WHERE job_id=? AND state='running'",
                (now(), row[0]),
            )
            conn.execute(
                "UPDATE jobs SET state='queued',lease_owner=NULL,lease_until=NULL,device_id=NULL WHERE id=?",
                (row[0],),
            )
        target = "iphone" if device_id else "mac"
        rows = conn.execute(
            "SELECT j.* FROM jobs j JOIN experiments e ON e.id=j.experiment_id WHERE e.state='running' AND e.target=? AND j.state='queued' ORDER BY j.rowid",
            (target,),
        ).fetchall()
        row = next(
            (r for r in rows if installed_model_ids is None or r["model_id"] in installed_model_ids), None
        )
        if row is None:
            return None
        job = dict(row)
        attempt_id = uid()
        conn.execute(
            "UPDATE jobs SET state='running',lease_owner=?,lease_until=?,device_id=?,error=NULL WHERE id=?",
            (owner, time.time() + lease_seconds, device_id, job["id"]),
        )
        conn.execute(
            "INSERT INTO attempts(id,job_id,state,started_at) VALUES(?,?,'running',?)",
            (attempt_id, job["id"], now()),
        )
        event(conn, "job.started", job["id"], {"attempt_id": attempt_id})
        job.update(
            state="running",
            lease_owner=owner,
            attempt_id=attempt_id,
            device_id=device_id,
            snapshot=json.loads(job["snapshot"]),
        )
        return job


def heartbeat(db: Database, job: dict, lease_seconds=120):
    with db.transaction() as conn:
        cursor = conn.execute(
            "UPDATE jobs SET lease_until=? WHERE id=? AND lease_owner=? AND state='running'",
            (time.time() + lease_seconds, job["id"], job["lease_owner"]),
        )
        return cursor.rowcount == 1


def validate_output(value: dict):
    if not isinstance(value.get("text"), str) or len(value["text"]) > 200000:
        raise ValueError("Runner must return a valid transcription string")
    for field in ("inference_seconds", "load_seconds"):
        number = value.get(field)
        if (
            isinstance(number, bool)
            or not isinstance(number, (float, int))
            or not math.isfinite(number)
            or number < 0
        ):
            raise ValueError(f"Runner returned invalid {field}")
    if not value.get("runtime_version"):
        raise ValueError("Runner must identify its runtime version")
    encode(value)  # rejects NaN in optional measurements too


def complete_job(db: Database, job: dict, output: dict):
    validate_output(output)
    if output["runtime_version"] != job["snapshot"]["model"]["runtime_version"]:
        raise ValueError("Runtime version differs from the frozen model manifest")
    snapshot = job["snapshot"]
    scores = score(snapshot["reference"]["text"], output["text"], snapshot["recording"]["language"])
    with db.transaction() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
        attempt = conn.execute("SELECT * FROM attempts WHERE id=?", (job["attempt_id"],)).fetchone()
        if (
            not row
            or row["state"] != "running"
            or row["lease_owner"] != job["lease_owner"]
            or not attempt
            or attempt["state"] != "running"
        ):
            raise ValueError("Job lease is no longer owned by this runner")
        output_id = uid()
        measurements = {k: v for k, v in output.items() if k != "text"}
        conn.execute(
            "INSERT INTO outputs VALUES(?,?,?,?,?,?,?)",
            (
                output_id,
                job["id"],
                job["attempt_id"],
                output["text"],
                encode(measurements),
                encode(
                    {
                        "model": snapshot["model"],
                        "asset_sha256": snapshot["recording"]["asset_sha256"],
                        "settings": snapshot["settings"],
                    }
                ),
                now(),
            ),
        )
        conn.execute(
            "INSERT INTO evaluations(id,output_id,reference_revision,reference_text,version,scores,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                uid(),
                output_id,
                snapshot["reference"]["revision"],
                snapshot["reference"]["text"],
                VERSION,
                encode(scores),
                now(),
            ),
        )
        conn.execute("UPDATE jobs SET state='succeeded',lease_until=NULL WHERE id=?", (job["id"],))
        conn.execute(
            "UPDATE attempts SET state='succeeded',ended_at=? WHERE id=?", (now(), job["attempt_id"])
        )
        event(conn, "job.succeeded", job["id"], {"output_id": output_id})
        _finish_experiment(conn, row["experiment_id"])


def _finish_experiment(conn, experiment_id):
    pending = conn.execute(
        "SELECT count(*) FROM jobs WHERE experiment_id=? AND state IN ('queued','running')", (experiment_id,)
    ).fetchone()[0]
    if not pending:
        conn.execute(
            "UPDATE experiments SET state='completed' WHERE id=? AND state='running'", (experiment_id,)
        )


def fail_job(db: Database, job: dict, error: str):
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT state,lease_owner,experiment_id FROM jobs WHERE id=?", (job["id"],)
        ).fetchone()
        if row and row["state"] == "running" and row["lease_owner"] == job["lease_owner"]:
            conn.execute(
                "UPDATE jobs SET state='failed',error=?,lease_until=NULL WHERE id=?",
                (error[-4000:], job["id"]),
            )
            conn.execute(
                "UPDATE attempts SET state='failed',error=?,ended_at=? WHERE id=? AND state='running'",
                (error[-4000:], now(), job["attempt_id"]),
            )
            event(conn, "job.failed", job["id"], {"error": error[-4000:]})
            _finish_experiment(conn, row["experiment_id"])


def list_jobs(db: Database, experiment_id: str, evaluation_id: str | None = None):
    with db.connect() as conn:
        require(conn.execute("SELECT id FROM experiments WHERE id=?", (experiment_id,)).fetchone())
        if evaluation_id:
            require(
                conn.execute(
                    "SELECT id FROM evaluation_snapshots WHERE id=? AND experiment_id=?",
                    (evaluation_id, experiment_id),
                ).fetchone(),
                "Evaluation snapshot not found in this experiment",
            )
        result = []
        for row in conn.execute(
            "SELECT j.*,r.reference_revision FROM jobs j JOIN recordings r ON r.id=j.recording_id WHERE experiment_id=? ORDER BY j.rowid",
            (experiment_id,),
        ):
            value = dict(row)
            current_revision = value["reference_revision"]
            value["snapshot"] = json.loads(value["snapshot"])
            value["stale_reference"] = (
                value.pop("reference_revision") != value["snapshot"]["reference"]["revision"]
            )
            output = conn.execute("SELECT * FROM outputs WHERE job_id=?", (row["id"],)).fetchone()
            value["output"], value["scores"] = None, None
            if output:
                value["output"] = dict(output)
                value["output"]["measurements"] = json.loads(output["measurements"])
                value["output"]["provenance"] = json.loads(output["provenance"])
                evaluation = conn.execute(
                    "SELECT scores,reference_revision,reference_text,version FROM evaluations WHERE output_id=? AND snapshot_id IS ? ORDER BY rowid LIMIT 1",
                    (output["id"], evaluation_id),
                ).fetchone()
                value["scores"] = json.loads(evaluation["scores"]) if evaluation else None
                value["evaluation_reference"] = (
                    {
                        "revision": evaluation["reference_revision"],
                        "text": evaluation["reference_text"],
                        "version": evaluation["version"],
                    }
                    if evaluation
                    else None
                )
                if evaluation:
                    value["stale_reference"] = current_revision != evaluation["reference_revision"]
            value["attempts"] = [
                dict(a)
                for a in conn.execute("SELECT * FROM attempts WHERE job_id=? ORDER BY rowid", (row["id"],))
            ]
            result.append(value)
        return result
