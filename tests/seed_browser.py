"""Synthetic transcripts ONLY in the browser's isolated temporary database."""

import io
import json
import sys
import wave
from pathlib import Path

from fastapi.testclient import TestClient
from stt_lab.api import create_app
from stt_lab.experiments import claim_job, complete_job
from stt_lab.registry import register_manifest
from test_experiments import install_model

root = Path(sys.argv[1])
with TestClient(create_app(root)) as client:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x01\x00" * 32000)
    recording = client.post(
        "/api/v1/recordings", files={"file": ("Synthetic UI fixture — not evaluation.wav", buffer.getvalue())}
    ).json()
    client.put(
        f"/api/v1/recordings/{recording['id']}/reference",
        json={
            "text": "We benchmark speech in İzmir. مرحبا بالعالم.",
            "status": "verified",
            "expected_revision": 0,
        },
    )
    manifest = install_model(client, root)
    ids = []
    for index in range(5):
        model = {
            **manifest,
            "id": f"ui-fixture-{index}",
            "family": "Synthetic UI fixture",
            "variant": f"Fixture {index}",
        }
        register_manifest(client.app.state.db, model)
        ids.append(model["id"])
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Synthetic UI acceptance — not benchmark evidence",
            "recording_ids": [recording["id"]],
            "model_ids": ids,
        },
    ).json()
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    texts = [
        "We benchmark speech in İzmir. مرحبا بالعالم.",
        "We benchmark speech in Izmir. مرحبا بالعالم.",
        "We benchmark in İzmir.",
        "We benchmark speech in İzmir. مرحبا.",
        "",
    ]
    for index in range(5):
        job = claim_job(client.app.state.db, "ui-fixture-seeder")
        complete_job(
            client.app.state.db,
            job,
            {
                "text": texts[index],
                "load_seconds": 0.1,
                "inference_seconds": 1.0 + index * 0.1,
                "runtime_version": "test-fixture",
            },
        )
    print(json.dumps({"experiment_id": experiment["id"], "recording_id": recording["id"]}))
