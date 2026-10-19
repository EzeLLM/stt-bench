import csv
import io
import sqlite3
import zipfile

from .analytics import comparison
from .common import now, require, uid
from .db import Database
from .experiments import list_jobs


def export_experiment(db: Database, experiment_id: str):
    with db.connect() as conn:
        experiment = dict(
            require(conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone())
        )
        reviews = [
            dict(r) for r in conn.execute("SELECT * FROM reviews WHERE experiment_id=?", (experiment_id,))
        ]
        artifacts = [
            dict(r)
            for r in conn.execute("SELECT * FROM profiling_artifacts WHERE experiment_id=?", (experiment_id,))
        ]
        evaluation_snapshots = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM evaluation_snapshots WHERE experiment_id=?", (experiment_id,)
            )
        ]
        evaluations = [
            dict(r)
            for r in conn.execute(
                "SELECT e.* FROM evaluations e JOIN outputs o ON o.id=e.output_id JOIN jobs j ON j.id=o.job_id WHERE j.experiment_id=?",
                (experiment_id,),
            )
        ]
    return {
        "schema_version": 1,
        "exported_at": now(),
        "experiment": experiment,
        "jobs": list_jobs(db, experiment_id),
        "comparison": comparison(db, experiment_id),
        "reviews": reviews,
        "profiling_artifacts": artifacts,
        "evaluation_snapshots": evaluation_snapshots,
        "evaluations": evaluations,
    }


def csv_export(db: Database, experiment_id: str):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "job_id",
            "recording_id",
            "model_id",
            "revision",
            "runtime",
            "repetition",
            "state",
            "supported_language",
            "wer",
            "cer",
            "inference_seconds",
            "error",
        ]
    )
    for job in list_jobs(db, experiment_id):
        metrics = job["scores"]["normalized"] if job["scores"] else None
        writer.writerow(
            [
                job["id"],
                job["recording_id"],
                job["model_id"],
                job["snapshot"]["model"]["revision"],
                job["snapshot"]["model"]["runtime"],
                job["repetition"],
                job["state"],
                job["snapshot"]["supported_language"],
                metrics["word"]["rate"] if metrics else "",
                metrics["character"]["rate"] if metrics else "",
                job["output"]["measurements"]["inference_seconds"] if job["output"] else "",
                job["error"] or "",
            ]
        )
    return output.getvalue()


def backup(db: Database):
    directory = db.root / "backups"
    directory.mkdir(exist_ok=True)
    name = uid()
    snapshot = directory / (name + ".sqlite3")
    archive = directory / (name + ".zip")
    try:
        with db.connect() as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
            paths = {
                r[0]
                for r in target.execute(
                    "SELECT source_path FROM recordings UNION SELECT asset_path FROM recordings UNION SELECT path FROM profiling_artifacts"
                )
            }
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(snapshot, "lab.sqlite3")
            for relative in sorted(paths):
                path = (db.root / relative).resolve()
                if not path.is_relative_to(db.root) or not path.is_file():
                    raise ValueError(f"Backup asset is missing or outside storage: {relative}")
                zip_file.write(path, relative)
        from .audio import sha256

        return {
            "id": name,
            "filename": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": sha256(archive),
            "note": "Consistent SQLite backup with originals, canonical audio and profiling artifacts; model binaries and pairing credentials excluded",
        }
    finally:
        snapshot.unlink(missing_ok=True)
