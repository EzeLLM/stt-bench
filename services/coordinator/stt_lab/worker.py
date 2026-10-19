"""Independent, restartable worker. Native iPhone jobs are never executed here."""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .audio import sha256
from .common import uid
from .db import Database, encode
from .experiments import claim_job, complete_job, fail_job, heartbeat
from .registry import safe_path, verify_manifest

log = logging.getLogger("stt_lab.worker")


def execute(db: Database, job: dict):
    snapshot = job["snapshot"]
    model = verify_manifest(db, snapshot["model"])
    audio = safe_path(db.root, snapshot["recording"]["asset_path"])
    if not audio.is_file() or sha256(audio) != snapshot["recording"]["asset_sha256"]:
        raise ValueError("Canonical audio missing or checksum mismatch")
    request = {
        "schema_version": 1,
        "audio": str(audio),
        "audio_sha256": snapshot["recording"]["asset_sha256"],
        "model_root": str(safe_path(db.root, model["root"])),
        "model": model,
        "settings": snapshot["settings"],
        "language": snapshot["recording"]["language"],
    }
    request["seed"] = snapshot.get("seed", 0) + job["repetition"]
    work = db.root / "runtime"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as directory:
        request_path = Path(directory) / "request.json"
        request_path.write_text(encode(request))
        runtime = model["runtime"]
        if runtime in ("whisperkit", "fluidaudio"):
            executable = model.get("executable")
            if not executable or not Path(executable).is_file():
                raise ValueError("Build the Apple native runner and register its executable path on macOS")
            args = [executable, str(request_path)]
        else:
            args = [model.get("executable") or sys.executable, "-m", "stt_lab.runners", str(request_path)]
        env = {
            **os.environ,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "GRADIO_ANALYTICS_ENABLED": "False",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
        }
        deadline = time.monotonic() + snapshot["settings"]["timeout_seconds"]
        # Files avoid subprocess pipe deadlock and bound the in-memory log read.
        with (
            (Path(directory) / "stdout").open("w+") as stdout,
            (Path(directory) / "stderr").open("w+") as stderr,
        ):
            process = subprocess.Popen(args, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
            try:
                while process.poll() is None:
                    if time.monotonic() > deadline:
                        raise TimeoutError("Inference deadline exceeded")
                    if not heartbeat(db, job):
                        raise RuntimeError("Experiment cancelled or job lease revoked")
                    time.sleep(0.2)
                if process.returncode:
                    stderr.seek(max(0, stderr.tell() - 4000))
                    raise RuntimeError(f"Runner exited {process.returncode}: {stderr.read()[-4000:]}")
                stdout.seek(0)
                if (Path(directory) / "stdout").stat().st_size > 4 * 1024 * 1024:
                    raise ValueError("Runner output exceeded the 4 MiB protocol limit")
                results = [
                    line.removeprefix("STT_RESULT=") for line in stdout if line.startswith("STT_RESULT=")
                ]
                if len(results) != 1:
                    raise ValueError("Runner must emit exactly one STT_RESULT JSON envelope")
                return json.loads(results[0])
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()


def run_once(db: Database, owner: str) -> bool:
    job = claim_job(db, owner)
    if not job:
        return False
    try:
        output = execute(db, job)
        complete_job(db, job, output)
        log.info(encode({"event": "job.succeeded", "job_id": job["id"]}))
    except Exception as exc:
        fail_job(db, job, str(exc))
        log.error(encode({"event": "job.failed", "job_id": job["id"], "error": str(exc)}))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("STT_LAB_DATA", "data")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db, owner = Database(args.data), uid()
    while True:
        worked = run_once(db, owner)
        if args.once:
            return
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
