import asyncio
import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from .analytics import comparison
from .common import require
from .dataset import (
    Labels,
    ReferenceEdit,
    edit_labels,
    edit_reference,
    get_recording,
    import_recording,
    list_recordings,
)
from .db import Database
from .devices import pairing_token
from .devices import routes as device_routes
from .experiments import ExperimentCreate, action, create_experiment, list_experiments, list_jobs
from .exports import backup, csv_export, export_experiment
from .registry import Manifest, candidates, installed, register_manifest
from .rescoring import rescore, snapshots
from .reviews import ReviewCreate, ReviewEdit, create_review, edit_review, view_review


def create_app(data_root: Path | None = None) -> FastAPI:
    db = Database(data_root or Path(os.environ.get("STT_LAB_DATA", "data")))
    app = FastAPI(title="STT Benchmark Lab", version="0.1.0")
    app.state.db = db
    prefix = "/api/v1"

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        local = request.client and request.client.host in ("127.0.0.1", "::1", "testclient")
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are not permitted"}, status_code=403)
        if not local and not request.url.path.startswith(prefix + "/device/"):
            configured = os.environ.get("STT_LAB_LAN_TOKEN", "")
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not configured or not secrets.compare_digest(supplied, configured):
                return JSONResponse({"detail": "Desktop API is restricted to this computer"}, status_code=403)
        if request.url.path == prefix + "/pairing" and not local:
            return JSONResponse({"detail": "Pairing token is only visible locally"}, status_code=403)
        return await call_next(request)

    app.include_router(device_routes(db))

    @app.get(prefix + "/health")
    def health():
        with db.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        return {"status": "ok", "database_version": version, "inference": "local-only"}

    @app.get(prefix + "/recordings")
    def recordings(q: str = "", language: str = "", tag: str = ""):
        return list_recordings(db, q, language, tag)

    @app.post(prefix + "/recordings", status_code=201)
    def upload(file: UploadFile = File(...)):
        return import_recording(db, file)

    @app.get(prefix + "/recordings/{recording_id}")
    def recording(recording_id: str):
        return get_recording(db, recording_id)

    @app.get(prefix + "/recordings/{recording_id}/audio")
    def audio(recording_id: str, original: bool = False):
        with db.connect() as conn:
            row = require(conn.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)).fetchone())
        return FileResponse(
            db.root / row["source_path" if original else "asset_path"],
            media_type="application/octet-stream" if original else "audio/wav",
            filename=row["name"] if original else "canonical.wav",
        )

    @app.patch(prefix + "/recordings/{recording_id}")
    def labels(recording_id: str, value: Labels):
        return edit_labels(db, recording_id, value)

    @app.put(prefix + "/recordings/{recording_id}/reference")
    def reference(recording_id: str, value: ReferenceEdit):
        return edit_reference(db, recording_id, value)

    @app.get(prefix + "/recordings/{recording_id}/reference/history")
    def history(recording_id: str):
        get_recording(db, recording_id)
        with db.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM reference_revisions WHERE recording_id=? ORDER BY revision DESC",
                    (recording_id,),
                )
            ]

    @app.get(prefix + "/models")
    def models():
        return {"installed": installed(db), "candidates": candidates()}

    @app.post(prefix + "/models", status_code=201)
    def register_model(value: Manifest):
        try:
            return register_manifest(db, value.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get(prefix + "/experiments")
    def experiments():
        return list_experiments(db)

    @app.post(prefix + "/experiments", status_code=201)
    def experiment(value: ExperimentCreate):
        return create_experiment(db, value)

    @app.post(prefix + "/experiments/preview")
    def preview(value: ExperimentCreate):
        return create_experiment(db, value, preview=True)

    @app.get(prefix + "/experiments/{experiment_id}/jobs")
    def jobs(experiment_id: str, evaluation_id: str | None = None):
        return list_jobs(db, experiment_id, evaluation_id)

    @app.get(prefix + "/experiments/{experiment_id}/evaluations")
    def evaluation_snapshots(experiment_id: str):
        return snapshots(db, experiment_id)

    @app.post(prefix + "/experiments/{experiment_id}/evaluations", status_code=201)
    def new_evaluation(experiment_id: str):
        return rescore(db, experiment_id)

    @app.post(prefix + "/experiments/{experiment_id}/artifacts", status_code=201)
    def attach_artifact(
        experiment_id: str, file: UploadFile = File(...), measurement_kind: str = Form("external-trace")
    ):
        from .audio import sha256
        from .common import now, uid

        if measurement_kind not in ("external-trace", "system-estimate", "battery-observation"):
            raise HTTPException(422, "Specify an external trace, system estimate or battery observation")
        artifact_id = uid()
        directory = db.root / "artifacts"
        directory.mkdir(exist_ok=True)
        path = directory / artifact_id
        try:
            with path.open("xb") as target:
                size = 0
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 2 * 1024**3:
                        raise HTTPException(413, "Profiling artifact exceeds 2 GiB")
                    target.write(chunk)
            if not size:
                raise HTTPException(422, "Profiling artifact is empty")
            digest = sha256(path)
            with db.transaction() as conn:
                experiment = require(
                    conn.execute(
                        "SELECT finalized_at FROM experiments WHERE id=?", (experiment_id,)
                    ).fetchone()
                )
                if experiment["finalized_at"]:
                    raise HTTPException(409, "Finalized experiments are immutable")
                conn.execute(
                    "INSERT INTO profiling_artifacts VALUES(?,?,?,?,?,?,?)",
                    (
                        artifact_id,
                        experiment_id,
                        Path(file.filename or "profile.zip").name,
                        str(path.relative_to(db.root)),
                        digest,
                        measurement_kind,
                        now(),
                    ),
                )
                return dict(
                    conn.execute("SELECT * FROM profiling_artifacts WHERE id=?", (artifact_id,)).fetchone()
                )
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    @app.get(prefix + "/experiments/{experiment_id}/artifacts")
    def artifacts(experiment_id: str):
        with db.connect() as conn:
            require(conn.execute("SELECT id FROM experiments WHERE id=?", (experiment_id,)).fetchone())
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM profiling_artifacts WHERE experiment_id=? ORDER BY created_at",
                    (experiment_id,),
                )
            ]

    @app.get(prefix + "/artifacts/{artifact_id}")
    def artifact(artifact_id: str):
        with db.connect() as conn:
            row = require(
                conn.execute("SELECT * FROM profiling_artifacts WHERE id=?", (artifact_id,)).fetchone()
            )
        return FileResponse(db.root / row["path"], filename=row["name"])

    @app.post(prefix + "/experiments/{experiment_id}/{command}")
    def experiment_action(experiment_id: str, command: str):
        return action(db, experiment_id, command)

    @app.get(prefix + "/compare/{experiment_id}")
    def compare(experiment_id: str, language: str = "", tag: str = "", evaluation_id: str | None = None):
        return comparison(db, experiment_id, language, tag, evaluation_id)

    @app.post(prefix + "/reviews", status_code=201)
    def new_review(value: ReviewCreate):
        return create_review(db, value)

    @app.get(prefix + "/reviews/{review_id}")
    def review(review_id: str):
        return view_review(db, review_id)

    @app.put(prefix + "/reviews/{review_id}")
    def save_review(review_id: str, value: ReviewEdit):
        return edit_review(db, review_id, value)

    @app.post(prefix + "/reviews/{review_id}/lock")
    def lock_review(review_id: str):
        return edit_review(db, review_id, lock=True)

    @app.get(prefix + "/pairing")
    def pairing():
        return {
            "token": pairing_token(db),
            "protocol_version": 1,
            "instructions": "Use this Mac's LAN IP and coordinator port 8000. Start coordinator with --host 0.0.0.0 on a trusted private LAN.",
        }

    @app.get(prefix + "/devices")
    def devices():
        with db.connect() as conn:
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "details": json.loads(r["details"]),
                    "last_seen": r["last_seen"],
                }
                for r in conn.execute("SELECT * FROM devices ORDER BY last_seen DESC")
            ]

    @app.get(prefix + "/events")
    async def events(request: Request, after: int = 0):
        async def stream():
            cursor = after
            while not await request.is_disconnected():
                with db.connect() as conn:
                    rows = conn.execute(
                        "SELECT * FROM events WHERE id>? ORDER BY id LIMIT 100", (cursor,)
                    ).fetchall()
                for row in rows:
                    cursor = row["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(dict(row))}\n\n"
                if not rows:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.get(prefix + "/export/{experiment_id}")
    def export(experiment_id: str, format: str = "json"):
        if format == "csv":
            return Response(
                csv_export(db, experiment_id),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{experiment_id}.csv"'},
            )
        return export_experiment(db, experiment_id)

    @app.post(prefix + "/backup", status_code=201)
    def create_backup():
        return backup(db)

    @app.get(prefix + "/backup/{backup_id}")
    def download_backup(backup_id: str):
        from uuid import UUID

        try:
            safe_id = str(UUID(backup_id))
        except ValueError:
            raise HTTPException(404, "Backup not found")
        path = db.root / "backups" / (safe_id + ".zip")
        if not path.is_file():
            raise HTTPException(404, "Backup not found")
        return FileResponse(path, filename="stt-lab-backup-" + safe_id + ".zip")

    return app


def app_factory():
    return create_app()
