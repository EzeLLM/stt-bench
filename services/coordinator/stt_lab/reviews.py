import json
import random
import secrets

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .common import now, require, uid
from .db import Database, encode


class ReviewCreate(BaseModel):
    experiment_id: str
    recording_id: str


class Rating(BaseModel):
    faithfulness: int | None = Field(default=None, ge=1, le=5)
    readability: int | None = Field(default=None, ge=1, le=5)
    rank: int | None = Field(default=None, ge=1)
    semantic_preservation: int | None = Field(default=None, ge=1, le=5)
    proper_nouns: int | None = Field(default=None, ge=1, le=5)
    technical_vocabulary: int | None = Field(default=None, ge=1, le=5)
    hallucination: bool = False
    missing_words: bool = False
    comment: str = Field(default="", max_length=10000)


class ReviewEdit(BaseModel):
    ratings: dict[str, Rating]


def view_review(db: Database, review_id: str):
    with db.connect() as conn:
        row = require(conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone())
        mapping = json.loads(row["mapping"])
        outputs = []
        for anonymous_id, output_id in mapping.items():
            output = conn.execute(
                "SELECT o.text,j.model_id,j.snapshot FROM outputs o JOIN jobs j ON j.id=o.job_id WHERE o.id=?",
                (output_id,),
            ).fetchone()
            item = {"id": anonymous_id, "text": output["text"]}
            stored = require(
                conn.execute(
                    "SELECT scores FROM evaluations WHERE output_id=? AND snapshot_id IS NULL ORDER BY rowid LIMIT 1",
                    (output_id,),
                ).fetchone(),
                "Original evaluation evidence is missing",
            )
            evaluated = json.loads(stored[0])
            item["alignment"] = evaluated["alignment"]
            item["character_alignment"] = evaluated["character_alignment"]
            if row["locked"]:
                item["model_id"] = output["model_id"]
            outputs.append(item)
        return {
            "id": row["id"],
            "experiment_id": row["experiment_id"],
            "recording_id": row["recording_id"],
            "locked": bool(row["locked"]),
            "ratings": json.loads(row["ratings"]),
            "outputs": outputs,
            "seed": row["seed"] if row["locked"] else None,
            "updated_at": row["updated_at"],
        }


def create_review(db: Database, value: ReviewCreate):
    with db.transaction() as conn:
        pending = conn.execute(
            "SELECT count(*) FROM jobs WHERE experiment_id=? AND recording_id=? AND repetition=0 AND state IN ('queued','running')",
            (value.experiment_id, value.recording_id),
        ).fetchone()[0]
        if pending:
            raise HTTPException(
                409, "Wait until every first-repetition job for this recording has finished or failed"
            )
        rows = conn.execute(
            "SELECT o.id FROM outputs o JOIN jobs j ON j.id=o.job_id WHERE j.experiment_id=? AND j.recording_id=? AND j.repetition=0 ORDER BY j.model_id",
            (value.experiment_id, value.recording_id),
        ).fetchall()
        output_ids = {r[0] for r in rows}
        existing = conn.execute(
            "SELECT id,mapping FROM reviews WHERE experiment_id=? AND recording_id=? ORDER BY rowid DESC LIMIT 1",
            (value.experiment_id, value.recording_id),
        ).fetchone()
        if existing and set(json.loads(existing["mapping"]).values()) == output_ids:
            review_id = existing[0]
        else:
            rows = conn.execute(
                "SELECT o.id FROM outputs o JOIN jobs j ON j.id=o.job_id WHERE j.experiment_id=? AND j.recording_id=? AND j.repetition=0 ORDER BY j.model_id",
                (value.experiment_id, value.recording_id),
            ).fetchall()
            if not rows:
                raise HTTPException(
                    422, "No successful first-repetition outputs available for this recording"
                )
            seed = secrets.randbelow(2147483647)
            ids = [r[0] for r in rows]
            random.Random(seed).shuffle(ids)
            # Anonymous labels are independent of model names, colors and timings.
            mapping = {f"Output {i + 1}": output_id for i, output_id in enumerate(ids)}
            review_id = uid()
            conn.execute(
                "INSERT INTO reviews(id,experiment_id,recording_id,seed,mapping,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (review_id, value.experiment_id, value.recording_id, seed, encode(mapping), now(), now()),
            )
    return view_review(db, review_id)


def edit_review(db: Database, review_id: str, edit: ReviewEdit | None = None, lock=False):
    with db.transaction() as conn:
        row = require(conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone())
        if row["locked"]:
            if lock:
                return view_review(db, review_id)
            raise HTTPException(409, "Locked reviews are immutable")
        mapping = json.loads(row["mapping"])
        if lock:
            pending = conn.execute(
                "SELECT count(*) FROM jobs WHERE experiment_id=? AND recording_id=? AND repetition=0 AND state IN ('queued','running')",
                (row["experiment_id"], row["recording_id"]),
            ).fetchone()[0]
            current_ids = {
                r[0]
                for r in conn.execute(
                    "SELECT o.id FROM outputs o JOIN jobs j ON j.id=o.job_id WHERE j.experiment_id=? AND j.recording_id=? AND j.repetition=0",
                    (row["experiment_id"], row["recording_id"]),
                )
            }
            if pending or set(mapping.values()) != current_ids:
                raise HTTPException(
                    409,
                    "The output set changed. Reopen this recording for a new blind session; previous evidence is preserved.",
                )
        ratings = {k: v.model_dump() for k, v in edit.ratings.items()} if edit else json.loads(row["ratings"])
        if not set(ratings).issubset(mapping):
            raise HTTPException(422, "Rating includes an unknown anonymous output")
        if lock and set(ratings) != set(mapping):
            raise HTTPException(422, "Rate and rank every output before locking; ties may share a rank")
        if lock and any(
            not rating.get(field)
            for rating in ratings.values()
            for field in ("faithfulness", "readability", "rank")
        ):
            raise HTTPException(422, "Faithfulness, readability and rank are required for every output")
        if any(v.get("rank") is not None and v["rank"] > len(mapping) for v in ratings.values()):
            raise HTTPException(422, "Rank exceeds the number of outputs")
        conn.execute(
            "UPDATE reviews SET ratings=?,locked=?,updated_at=? WHERE id=?",
            (encode(ratings), int(lock), now(), review_id),
        )
    return view_review(db, review_id)
