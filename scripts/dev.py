#!/usr/bin/env python3
"""Supervise local processes; signal only children this command started."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--lan", action="store_true", help="Expose the authenticated device API to a trusted LAN")
args = parser.parse_args()
python = str(root / ".venv/bin/python")
env = {**os.environ, "STT_LAB_DATA": str(root / "data"), "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"}
commands = [
    [
        python,
        "-m",
        "uvicorn",
        "stt_lab.api:app_factory",
        "--factory",
        "--host",
        "0.0.0.0" if args.lan else "127.0.0.1",
        "--port",
        "8000",
    ],
    [python, "-m", "stt_lab.worker"],
    ["npm", "--prefix", "apps/web", "run", "dev"],
]
processes = []


def stop(*_):
    for process in processes:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
try:
    for command in commands:
        processes.append(subprocess.Popen(command, cwd=root, env=env, start_new_session=True))
    while True:
        for process in processes:
            if process.poll() is not None:
                raise SystemExit(process.returncode or 1)
        time.sleep(0.5)
finally:
    stop()
