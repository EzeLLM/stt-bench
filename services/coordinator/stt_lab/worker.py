"""Independent, restartable worker. Native iPhone jobs are never executed here."""

import argparse
import json
import logging
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .audio import sha256
from .common import uid
from .db import Database, encode
from .experiments import claim_job, complete_job, fail_job, heartbeat
from .registry import safe_path, verify_manifest

log = logging.getLogger("stt_lab.worker")


NATIVE_RUNTIMES = ("whisperkit", "fluidaudio")
PROTOCOL_LIMIT = 4 * 1024 * 1024


def runner_environment() -> dict:
    return {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "GRADIO_ANALYTICS_ENABLED": "False",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
    }


def build_request(db: Database, job: dict) -> dict:
    snapshot = job["snapshot"]
    model = verify_manifest(db, snapshot["model"])
    audio = safe_path(db.root, snapshot["recording"]["asset_path"])
    if not audio.is_file() or sha256(audio) != snapshot["recording"]["asset_sha256"]:
        raise ValueError("Canonical audio missing or checksum mismatch")
    return {
        "schema_version": 1,
        "audio": str(audio),
        "audio_sha256": snapshot["recording"]["asset_sha256"],
        "model_root": str(safe_path(db.root, model["root"])),
        "model": model,
        "settings": snapshot["settings"],
        "language": snapshot["recording"]["language"],
        "seed": snapshot.get("seed", 0) + job["repetition"],
    }


def stop(process: subprocess.Popen):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def execute_native(db: Database, job: dict, request: dict):
    """One process per job: the Swift runners are not reused across jobs."""
    model = request["model"]
    executable = model.get("executable")
    if not executable or not Path(executable).is_file():
        raise ValueError("Build the Apple native runner and register its executable path on macOS")
    work = db.root / "runtime"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as directory:
        request_path = Path(directory) / "request.json"
        request_path.write_text(encode(request))
        deadline = time.monotonic() + job["snapshot"]["settings"]["timeout_seconds"]
        # Files avoid subprocess pipe deadlock and bound the in-memory log read.
        with (
            (Path(directory) / "stdout").open("w+") as stdout,
            (Path(directory) / "stderr").open("w+") as stderr,
        ):
            process = subprocess.Popen(
                [executable, str(request_path)],
                stdout=stdout,
                stderr=stderr,
                env=runner_environment(),
                start_new_session=True,
            )
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
                if (Path(directory) / "stdout").stat().st_size > PROTOCOL_LIMIT:
                    raise ValueError("Runner output exceeded the 4 MiB protocol limit")
                results = [
                    line.removeprefix("STT_RESULT=") for line in stdout if line.startswith("STT_RESULT=")
                ]
                if len(results) != 1:
                    raise ValueError("Runner must emit exactly one STT_RESULT JSON envelope")
                return json.loads(results[0])
            finally:
                stop(process)


class Engine:
    """A Python runner process that keeps one model loaded for consecutive jobs.

    Requests go in as JSON lines on stdin and each result comes back as one STT_RESULT line. Any failure,
    timeout or cancellation discards the process, so a damaged engine is never reused.
    """

    def __init__(self, db: Database):
        self.db = db
        self.process = None
        self.directory = None
        self.stderr = None
        self.lines = queue.Queue()

    def start(self, model: dict):
        work = self.db.root / "runtime"
        work.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=work)
        self.stderr = (Path(self.directory.name) / "stderr").open("w+")
        self.lines = queue.Queue()
        self.process = subprocess.Popen(
            [model.get("executable") or sys.executable, "-m", "stt_lab.runners", "--serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            env=runner_environment(),
            start_new_session=True,
            text=True,
        )
        threading.Thread(target=self.read, args=(self.process, self.lines), daemon=True).start()

    @staticmethod
    def read(process: subprocess.Popen, lines: queue.Queue):
        # Bounded reads: a runaway line cannot exhaust memory. Library chatter on stdout is ignored.
        try:
            while True:
                line = process.stdout.readline(PROTOCOL_LIMIT + 1)
                if not line:
                    break
                if len(line) > PROTOCOL_LIMIT and not line.endswith("\n"):
                    lines.put(ValueError("Runner output exceeded the 4 MiB protocol limit"))
                    break
                if line.startswith("STT_RESULT="):
                    lines.put(line.removeprefix("STT_RESULT="))
        finally:
            lines.put(None)

    def exited(self) -> RuntimeError:
        self.process.wait()
        self.stderr.seek(max(0, self.stderr.tell() - 4000))
        return RuntimeError(f"Runner exited {self.process.returncode}: {self.stderr.read()[-4000:]}")

    def run(self, job: dict, request: dict):
        if self.process is None:
            self.start(request["model"])
        deadline = time.monotonic() + job["snapshot"]["settings"]["timeout_seconds"]
        try:
            self.process.stdin.write(encode(request) + "\n")
            self.process.stdin.flush()
            while True:
                try:
                    line = self.lines.get(timeout=0.2)
                except queue.Empty:
                    if time.monotonic() > deadline:
                        raise TimeoutError("Inference deadline exceeded") from None
                    if not heartbeat(self.db, job):
                        raise RuntimeError("Experiment cancelled or job lease revoked") from None
                    continue
                if isinstance(line, Exception):
                    raise line
                if line is None:
                    raise self.exited()
                return json.loads(line)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                try:
                    self.process.stdin.close()
                    self.process.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            stop(self.process)
        finally:
            self.stderr.close()
            self.directory.cleanup()
            self.process = None


def execute(db: Database, job: dict, engine: Engine | None = None):
    request = build_request(db, job)
    if request["model"]["runtime"] in NATIVE_RUNTIMES:
        return execute_native(db, job, request)
    if engine is not None:
        return engine.run(job, request)
    single = Engine(db)
    try:
        return single.run(job, request)
    finally:
        single.close()


def run_job(db: Database, job: dict, engine: Engine | None) -> bool:
    try:
        output = execute(db, job, engine)
        complete_job(db, job, output)
        log.info(encode({"event": "job.succeeded", "job_id": job["id"]}))
        return True
    except Exception as exc:
        fail_job(db, job, str(exc))
        log.error(encode({"event": "job.failed", "job_id": job["id"], "error": str(exc)}))
        return False


def run_once(db: Database, owner: str) -> bool:
    """Run the next job, then keep going with every queued job that can share its loaded model."""
    job = claim_job(db, owner)
    if not job:
        return False
    if job["snapshot"]["model"]["runtime"] in NATIVE_RUNTIMES:
        run_job(db, job, None)
        return True
    engine = Engine(db)
    try:
        while job and run_job(db, job, engine):
            job = claim_job(db, owner, engine_of=job)
    finally:
        engine.close()
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
