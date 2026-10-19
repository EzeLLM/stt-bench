"""Opt-in hardware/runtime smoke check. Synthetic silence is not evaluation data."""

import errno
import json
import os
import shutil
from pathlib import Path

import pytest
from stt_lab.experiments import list_jobs
from stt_lab.registry import register_manifest
from stt_lab.worker import run_once
from test_dataset import import_audio


@pytest.mark.skipif(
    os.environ.get("STT_REAL_INFERENCE") != "1",
    reason="Opt-in: requires the pinned 1.6 GB Whisper checkpoint and reference environment",
)
def test_actual_whisper_coordinator_worker_scoring_round_trip(client, tmp_path):
    run_reference(client, "whisper-reference-manifest.json")


@pytest.mark.skipif(
    os.environ.get("STT_ALL_REFERENCES") != "1",
    reason="Opt-in: requires all original checkpoints and isolated reference environments",
)
@pytest.mark.parametrize("name", ["qwen-0.6b", "qwen-1.7b", "parakeet-v3", "parakeet-ultra"])
def test_additional_original_coordinator_worker_scoring_round_trip(client, name):
    run_reference(client, name + "-manifest.json")


def run_reference(client, manifest_name):
    repo = Path(__file__).resolve().parents[1]
    manifest = json.loads((repo / "data" / manifest_name).read_text())
    target = client.app.state.db.root / manifest["root"]
    target.mkdir(parents=True)
    for asset in manifest["files"]:
        source = repo / "data" / manifest["root"] / asset["path"]
        destination = target / asset["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            shutil.copyfile(source, destination)
    register_manifest(client.app.state.db, manifest)
    recording = import_audio(client)
    client.put(
        f"/api/v1/recordings/{recording['id']}/reference",
        json={"text": "", "status": "verified", "expected_revision": 0},
    )
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Synthetic silence runtime check — not owner evaluation",
            "recording_ids": [recording["id"]],
            "model_ids": [manifest["id"]],
            "settings": {"max_new_tokens": 32},
        },
    ).json()
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    assert run_once(client.app.state.db, "real-inference-test")
    job = list_jobs(client.app.state.db, experiment["id"])[0]
    assert job["state"] == "succeeded", job["error"]
    assert isinstance(job["output"]["text"], str)
    assert job["output"]["measurements"]["runtime_version"] == manifest["runtime_version"]
    assert job["scores"]["normalized"]["word"]["rate"] is None
    assert len(job["attempts"]) == 1
