"""LAN protocol: paired devices own their jobs and execute inference locally."""

import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .common import now, require, uid
from .db import Database, encode
from .experiments import claim_job, complete_job, fail_job, heartbeat
from .registry import safe_path


def token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def pairing_token(db: Database) -> str:
    path = db.root / "pairing.key"
    if not path.exists():
        try:
            with path.open("x") as file:
                path.chmod(0o600)
                file.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    return path.read_text().strip()


class Pair(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    details: dict = Field(default_factory=dict)


class Claim(BaseModel):
    installed_model_ids: list[str] = Field(max_length=100)


class DeviceResult(BaseModel):
    attempt_id: str
    text: str = Field(max_length=200000)
    inference_seconds: float = Field(ge=0, allow_inf_nan=False)
    load_seconds: float = Field(ge=0, allow_inf_nan=False)
    runtime_version: str
    audio_sha256: str
    model_revision: str
    device_conditions: dict
    execution_location: str = Field(pattern="^device$")
    energy_joules: None = None
    measurements: dict = Field(default_factory=dict)


class DeviceFailure(BaseModel):
    attempt_id: str
    error: str = Field(min_length=1, max_length=4000)


def routes(db: Database):
    router = APIRouter(prefix="/api/v1/device")

    def authenticate(authorization: str = Header(default="")):
        token = authorization.removeprefix("Bearer ")
        with db.transaction() as conn:
            row = conn.execute("SELECT * FROM devices WHERE token_hash=?", (token_hash(token),)).fetchone()
            if not row:
                raise HTTPException(401, "Pair this device with the local coordinator")
            conn.execute("UPDATE devices SET last_seen=? WHERE id=?", (now(), row["id"]))
        return dict(row)

    def owned_job(device, job_id, allow_completed=False):
        with db.connect() as conn:
            row = require(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            if row["device_id"] != device["id"]:
                raise HTTPException(403, "This job belongs to another device")
            attempt = conn.execute(
                "SELECT * FROM attempts WHERE job_id=? ORDER BY rowid DESC LIMIT 1", (job_id,)
            ).fetchone()
        return {**dict(row), "snapshot": json.loads(row["snapshot"]), "attempt_id": attempt["id"]}

    @router.post("/pair", status_code=201)
    def pair(value: Pair, authorization: str = Header(default="")):
        if not secrets.compare_digest(authorization.removeprefix("Bearer "), pairing_token(db)):
            raise HTTPException(401, "Invalid local pairing token")
        device_id, token = uid(), secrets.token_urlsafe(32)
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO devices VALUES(?,?,?,?,?)",
                (device_id, value.name, token_hash(token), encode(value.details), now()),
            )
        return {"id": device_id, "token": token, "protocol_version": 1}

    @router.get("/models")
    def models(device=Depends(authenticate)):
        with db.connect() as conn:
            manifests = [json.loads(r[0]) for r in conn.execute("SELECT manifest FROM models")]
        return [m for m in manifests if m["runtime"] in ("whisperkit", "fluidaudio")]

    @router.get("/models/{model_id}/assets/{asset_path:path}")
    def model_asset(model_id: str, asset_path: str, device=Depends(authenticate)):
        with db.connect() as conn:
            manifest = json.loads(
                require(conn.execute("SELECT manifest FROM models WHERE id=?", (model_id,)).fetchone())[0]
            )
        if asset_path not in {a["path"] for a in manifest["files"]}:
            raise HTTPException(404, "Unknown checkpoint asset")
        path = safe_path(safe_path(db.root, manifest["root"]), asset_path)
        if not path.is_file():
            raise HTTPException(404, "Checkpoint asset is missing on coordinator")
        return FileResponse(path)

    @router.post("/claim")
    def claim(value: Claim, device=Depends(authenticate)):
        job = claim_job(
            db,
            "device:" + device["id"],
            lease_seconds=300,
            device_id=device["id"],
            installed_model_ids=value.installed_model_ids,
        )
        if not job:
            return None
        heartbeat(db, job, lease_seconds=max(3600, job["snapshot"]["settings"]["timeout_seconds"] + 3600))
        snapshot = job["snapshot"]
        return {
            "id": job["id"],
            "attempt_id": job["attempt_id"],
            "experiment_id": job["experiment_id"],
            "audio_url": f"/api/v1/device/jobs/{job['id']}/audio",
            "audio_sha256": snapshot["recording"]["asset_sha256"],
            "duration": snapshot["recording"]["duration"],
            "model": snapshot["model"],
            "settings": snapshot["settings"],
            "language": snapshot["recording"]["language"],
            "repetition": job["repetition"],
        }

    @router.get("/jobs/{job_id}/audio")
    def audio(job_id: str, device=Depends(authenticate)):
        job = owned_job(device, job_id)
        return FileResponse(
            safe_path(db.root, job["snapshot"]["recording"]["asset_path"]), media_type="audio/wav"
        )

    @router.post("/jobs/{job_id}/heartbeat")
    def beat(job_id: str, device=Depends(authenticate)):
        job = owned_job(device, job_id)
        if not heartbeat(db, job, 300):
            raise HTTPException(409, "Job cancelled or lease revoked")
        return {"state": "running"}

    @router.post("/jobs/{job_id}/result")
    def result(job_id: str, value: DeviceResult, device=Depends(authenticate)):
        job = owned_job(device, job_id)
        envelope = value.model_dump()
        if value.attempt_id != job["attempt_id"]:
            raise HTTPException(409, "Result belongs to an obsolete attempt")
        if (
            value.audio_sha256 != job["snapshot"]["recording"]["asset_sha256"]
            or value.model_revision != job["snapshot"]["model"]["revision"]
        ):
            raise HTTPException(422, "Input or checkpoint identity differs from the frozen experiment")
        with db.connect() as conn:
            existing = conn.execute(
                "SELECT text,measurements FROM outputs WHERE job_id=?", (job_id,)
            ).fetchone()
        if existing:
            if existing["text"] != value.text or json.loads(existing["measurements"]) != {
                k: v for k, v in envelope.items() if k != "text"
            }:
                raise HTTPException(409, "A different immutable result already exists")
            return {"status": "already-synchronized"}
        try:
            complete_job(db, job, envelope)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"status": "synchronized"}

    @router.post("/jobs/{job_id}/failure")
    def failure(job_id: str, value: DeviceFailure, device=Depends(authenticate)):
        job = owned_job(device, job_id)
        if value.attempt_id != job["attempt_id"]:
            raise HTTPException(409, "Obsolete attempt")
        fail_job(db, job, value.error)
        return {"status": "failed"}

    return router
