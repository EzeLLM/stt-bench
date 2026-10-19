import json
import os
import sqlite3
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, Field

from .audio import prepare, sha256
from .common import now, require, uid
from .db import Database, encode

MAX_BYTES = 1024 * 1024 * 1024


class Labels(BaseModel):
    language: str = Field(min_length=1, max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=50)


class ReferenceEdit(BaseModel):
    text: str = Field(max_length=200000)
    status: str = Field(pattern="^(draft|verified)$")
    expected_revision: int = Field(ge=0)


def serialize(conn, row) -> dict:
    value = dict(row)
    value.update(json.loads(value.pop("metadata")))
    value["tags"] = json.loads(value["tags"])
    revision = conn.execute(
        "SELECT * FROM reference_revisions WHERE recording_id=? AND revision=?",
        (value["id"], value["reference_revision"]),
    ).fetchone()
    value["reference"] = dict(revision) if revision else {"revision": 0, "text": "", "status": "draft"}
    value["benchmark_count"] = conn.execute(
        "SELECT count(*) FROM outputs o JOIN jobs j ON j.id=o.job_id WHERE j.recording_id=?", (value["id"],)
    ).fetchone()[0]
    value.pop("source_path")
    value.pop("asset_path")
    return value


def get_recording(db: Database, recording_id: str) -> dict:
    with db.connect() as conn:
        return serialize(
            conn, require(conn.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)).fetchone())
        )


def list_recordings(db: Database, q: str = "", language: str = "", tag: str = "") -> list[dict]:
    with db.connect() as conn:
        rows = [
            serialize(conn, row) for row in conn.execute("SELECT * FROM recordings ORDER BY created_at DESC")
        ]
    return [
        r
        for r in rows
        if (not q or q.casefold() in (r["name"] + " " + " ".join(r["tags"])).casefold())
        and (not language or language == r["language"])
        and (not tag or tag in r["tags"])
    ]


def import_recording(db: Database, upload: UploadFile) -> dict:
    temporary = db.root / "tmp" / uid()
    temporary.mkdir(parents=True)
    source, canonical = temporary / "original", temporary / "audio.wav"
    try:
        size = 0
        with source.open("wb") as out:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Maximum recording size is 1 GiB")
                out.write(chunk)
        source_hash = sha256(source)
        with db.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM recordings WHERE source_sha256=?", (source_hash,)
            ).fetchone()
        if existing:
            raise HTTPException(
                409, {"message": "This original recording is already imported", "recording_id": existing[0]}
            )
        try:
            metadata = prepare(source, canonical)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc
        metadata["size_bytes"] = size
        original_path = db.root / "originals" / source_hash
        asset_path = db.root / "processed" / (metadata["canonical"]["sha256"] + ".wav")
        original_path.parent.mkdir(exist_ok=True)
        asset_path.parent.mkdir(exist_ok=True)
        recording_id = uid()
        try:
            with db.transaction() as conn:
                existing = conn.execute(
                    "SELECT id FROM recordings WHERE source_sha256=?", (source_hash,)
                ).fetchone()
                if existing:
                    raise HTTPException(
                        409, {"message": "Recording already imported", "recording_id": existing[0]}
                    )
                # Content-addressed canonical assets may be shared by distinct originals.
                if not original_path.exists():
                    os.replace(source, original_path)
                if not asset_path.exists():
                    os.replace(canonical, asset_path)
                conn.execute(
                    "INSERT INTO recordings(id,name,source_sha256,source_path,asset_path,asset_sha256,duration,metadata,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        recording_id,
                        Path(upload.filename or "Recording").name,
                        source_hash,
                        str(original_path.relative_to(db.root)),
                        str(asset_path.relative_to(db.root)),
                        metadata["canonical"]["sha256"],
                        metadata["duration"],
                        encode(metadata),
                        now(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "This original recording is already imported") from exc
        return get_recording(db, recording_id)
    finally:
        for file in temporary.iterdir():
            file.unlink()
        temporary.rmdir()


def edit_labels(db: Database, recording_id: str, labels: Labels) -> dict:
    tags = sorted({t.strip() for t in labels.tags if t.strip()})
    if any(len(t) > 80 for t in tags):
        raise HTTPException(422, "Tags must be 80 characters or fewer")
    with db.transaction() as conn:
        require(conn.execute("SELECT id FROM recordings WHERE id=?", (recording_id,)).fetchone())
        conn.execute(
            "UPDATE recordings SET language=?,tags=? WHERE id=?",
            (labels.language, encode(tags), recording_id),
        )
    return get_recording(db, recording_id)


def edit_reference(db: Database, recording_id: str, edit: ReferenceEdit) -> dict:
    with db.transaction() as conn:
        row = require(
            conn.execute("SELECT reference_revision FROM recordings WHERE id=?", (recording_id,)).fetchone()
        )
        if row[0] != edit.expected_revision:
            raise HTTPException(409, "Ground truth changed in another editor. Reload before saving.")
        revision = row[0] + 1
        conn.execute(
            "INSERT INTO reference_revisions VALUES(?,?,?,?,?)",
            (recording_id, revision, edit.text, edit.status, now()),
        )
        conn.execute("UPDATE recordings SET reference_revision=? WHERE id=?", (revision, recording_id))
        # Return precisely this transaction's revision. A later read could adopt another editor's CAS token.
        return serialize(
            conn, conn.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)).fetchone()
        )
