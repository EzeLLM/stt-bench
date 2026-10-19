import hashlib
import json

import pytest
from stt_lab.experiments import claim_job, complete_job, fail_job
from stt_lab.registry import register_manifest
from test_dataset import import_audio


def install_model(client, tmp_path, languages=None, runtime="whisper-transformers"):
    db = client.app.state.db
    folder = db.root / "models" / "test-checkpoint"
    folder.mkdir(parents=True, exist_ok=True)
    asset = folder / "config.json"
    asset.write_text("{}")
    manifest = {
        "id": "test-model",
        "family": "Whisper Turbo",
        "variant": "test fixture",
        "repository": "openai/whisper-large-v3-turbo",
        "revision": "a" * 40,
        "license": "MIT",
        "original_publisher": "OpenAI",
        "conversion_publisher": None,
        "source_checkpoint": "openai/whisper-large-v3-turbo@" + "a" * 40,
        "runtime": runtime,
        "runtime_version": "test-fixture",
        "root": "models/test-checkpoint",
        "languages": languages or ["en", "tr", "ar"],
        "components": [{"name": "all", "precision": "fp32", "quantization": "none"}],
        "files": [{"path": "config.json", "sha256": hashlib.sha256(b"{}").hexdigest()}],
        "parity": "not-validated",
        "parameter_count": 809000000,
    }
    register_manifest(db, manifest)
    return manifest


def prepare_experiment(client, tmp_path, target="mac"):
    r = import_audio(client)
    client.put(
        f"/api/v1/recordings/{r['id']}/reference",
        json={"text": "hello world", "status": "verified", "expected_revision": 0},
    )
    install_model(client, tmp_path, runtime="whisperkit" if target == "iphone" else "whisper-transformers")
    response = client.post(
        "/api/v1/experiments",
        json={"name": "Accuracy", "recording_ids": [r["id"]], "model_ids": ["test-model"], "target": target},
    )
    assert response.status_code == 201, response.text
    return r, response.json()


def test_verified_ground_truth_required(client, tmp_path):
    r = import_audio(client)
    install_model(client, tmp_path)
    response = client.post(
        "/api/v1/experiments", json={"name": "Draft", "recording_ids": [r["id"]], "model_ids": ["test-model"]}
    )
    assert response.status_code == 422


def test_snapshots_stay_fixed_and_finalized_is_immutable(client, tmp_path):
    r, experiment = prepare_experiment(client, tmp_path)
    db = client.app.state.db
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    job = claim_job(db, "worker")
    assert job["snapshot"]["reference"]["text"] == "hello world"
    complete_job(
        db,
        job,
        {
            "text": "hello word",
            "inference_seconds": 0.2,
            "load_seconds": 0.1,
            "runtime_version": "test-fixture",
            "measurement_kind": "observed",
        },
    )
    client.put(
        f"/api/v1/recordings/{r['id']}/reference",
        json={"text": "new reference", "status": "verified", "expected_revision": 1},
    )
    jobs = client.get(f"/api/v1/experiments/{experiment['id']}/jobs").json()
    assert jobs[0]["stale_reference"] is True
    assert jobs[0]["scores"]["normalized"]["word"]["rate"] == 0.5
    assert client.post(f"/api/v1/experiments/{experiment['id']}/finalize").status_code == 200
    assert client.post(f"/api/v1/experiments/{experiment['id']}/retry").status_code == 409


def test_lease_recovery_preserves_interrupted_attempt(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path)
    db = client.app.state.db
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    first = claim_job(db, "old", lease_seconds=-1)
    second = claim_job(db, "new")
    assert first["id"] == second["id"]
    assert first["attempt_id"] != second["attempt_id"]
    with pytest.raises(ValueError, match="lease"):
        complete_job(
            db,
            first,
            {
                "text": "obsolete",
                "inference_seconds": 1,
                "load_seconds": 0,
                "runtime_version": "test-fixture",
            },
        )
    with db.connect() as c:
        assert (
            c.execute("SELECT state FROM attempts WHERE id=?", (first["attempt_id"],)).fetchone()[0]
            == "interrupted"
        )


def test_invalid_output_and_failure_never_success(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path)
    db = client.app.state.db
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    job = claim_job(db, "worker")
    with pytest.raises(ValueError):
        complete_job(db, job, {"text": "text", "inference_seconds": -1})
    fail_job(db, job, "model loading failed")
    result = client.get(f"/api/v1/experiments/{experiment['id']}/jobs").json()[0]
    assert result["state"] == "failed" and result["output"] is None
    assert client.post(f"/api/v1/experiments/{experiment['id']}/retry").status_code == 200
    assert claim_job(db, "worker")["id"] == job["id"]


def test_iphone_jobs_never_claimed_by_mac(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path, target="iphone")
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    assert claim_job(client.app.state.db, "mac-worker") is None


def test_blind_review_hides_identity_and_requires_complete_ranking(client, tmp_path):
    r, experiment = prepare_experiment(client, tmp_path)
    db = client.app.state.db
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    complete_job(
        db,
        claim_job(db, "w"),
        {
            "text": "hello world",
            "inference_seconds": 0.2,
            "load_seconds": 0.1,
            "runtime_version": "test-fixture",
        },
    )
    response = client.post(
        "/api/v1/reviews", json={"experiment_id": experiment["id"], "recording_id": r["id"]}
    )
    assert response.status_code == 201, response.text
    review = response.json()
    serialized = json.dumps(review)
    assert (
        "test-model" not in serialized
        and "inference_seconds" not in serialized
        and "scores" not in serialized
    )
    assert client.post(f"/api/v1/reviews/{review['id']}/lock").status_code == 422
    anonymous_id = review["outputs"][0]["id"]
    ratings = {anonymous_id: {"faithfulness": 5, "readability": 4, "rank": 1, "comment": "good"}}
    assert client.put(f"/api/v1/reviews/{review['id']}", json={"ratings": ratings}).status_code == 200
    locked = client.post(f"/api/v1/reviews/{review['id']}/lock").json()
    assert locked["outputs"][0]["model_id"] == "test-model"
    assert client.put(f"/api/v1/reviews/{review['id']}", json={"ratings": ratings}).status_code == 409


def test_checkpoint_hash_is_checked(client, tmp_path):
    manifest = install_model(client, tmp_path)
    (client.app.state.db.root / manifest["root"] / "config.json").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        register_manifest(client.app.state.db, manifest)


def test_unsupported_language_excluded(client, tmp_path):
    r = import_audio(client)
    client.patch(f"/api/v1/recordings/{r['id']}", json={"language": "ar", "tags": []})
    client.put(
        f"/api/v1/recordings/{r['id']}/reference",
        json={"text": "مرحبا", "status": "verified", "expected_revision": 0},
    )
    install_model(client, tmp_path, languages=["en"])
    response = client.post(
        "/api/v1/experiments",
        json={"name": "Unsupported", "recording_ids": [r["id"]], "model_ids": ["test-model"]},
    )
    assert response.status_code == 422
