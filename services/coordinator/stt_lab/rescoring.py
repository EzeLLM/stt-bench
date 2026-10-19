import json

from fastapi import HTTPException

from .common import now, require, uid
from .db import Database, encode
from .evaluation import VERSION, score


def rescore(db: Database, experiment_id: str):
    snapshot_id = uid()
    with db.transaction() as conn:
        require(conn.execute("SELECT id FROM experiments WHERE id=?", (experiment_id,)).fetchone())
        rows = conn.execute(
            "SELECT o.id,o.text,r.id AS recording_id,r.reference_revision,j.snapshot FROM outputs o JOIN jobs j ON j.id=o.job_id JOIN recordings r ON r.id=j.recording_id WHERE j.experiment_id=?",
            (experiment_id,),
        ).fetchall()
        if not rows:
            raise HTTPException(422, "No successful outputs to rescore")
        conn.execute(
            "INSERT INTO evaluation_snapshots VALUES(?,?,?,?)", (snapshot_id, experiment_id, VERSION, now())
        )
        for row in rows:
            reference = require(
                conn.execute(
                    "SELECT * FROM reference_revisions WHERE recording_id=? AND revision=?",
                    (row["recording_id"], row["reference_revision"]),
                ).fetchone()
            )
            if reference["status"] != "verified":
                raise HTTPException(
                    422, "Verify all current references before creating an evaluation snapshot"
                )
            language = json.loads(row["snapshot"])["recording"]["language"]
            scores = score(reference["text"], row["text"], language)
            conn.execute(
                "INSERT INTO evaluations(id,output_id,reference_revision,reference_text,version,scores,created_at,snapshot_id) VALUES(?,?,?,?,?,?,?,?)",
                (
                    uid(),
                    row["id"],
                    reference["revision"],
                    reference["text"],
                    VERSION,
                    encode(scores),
                    now(),
                    snapshot_id,
                ),
            )
        return dict(conn.execute("SELECT * FROM evaluation_snapshots WHERE id=?", (snapshot_id,)).fetchone())


def snapshots(db: Database, experiment_id: str):
    with db.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM evaluation_snapshots WHERE experiment_id=? ORDER BY rowid DESC",
                (experiment_id,),
            )
        ]
