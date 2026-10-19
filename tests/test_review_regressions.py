import pytest
from fastapi import HTTPException
from stt_lab import dataset
from stt_lab.experiments import claim_job, complete_job, fail_job
from stt_lab.registry import register_manifest
from test_dataset import import_audio
from test_experiments import install_model, prepare_experiment


def output():
    return {
        "text": "hello world",
        "load_seconds": 0,
        "inference_seconds": 1,
        "runtime_version": "test-fixture",
    }


def test_reference_save_response_never_adopts_another_writers_revision(client, monkeypatch):
    recording = import_audio(client)
    db = client.app.state.db
    original_read = dataset.get_recording
    interleaved = False

    def read_with_other_writer(db, recording_id):
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            dataset.edit_reference(
                db,
                recording_id,
                dataset.ReferenceEdit(text="B verified", status="verified", expected_revision=1),
            )
        return original_read(db, recording_id)

    monkeypatch.setattr(dataset, "get_recording", read_with_other_writer)
    saved = dataset.edit_reference(
        db, recording["id"], dataset.ReferenceEdit(text="A draft", status="draft", expected_revision=0)
    )
    assert saved["reference"]["revision"] == 1
    assert saved["reference"]["text"] == "A draft"
    if not interleaved:
        dataset.edit_reference(
            db,
            recording["id"],
            dataset.ReferenceEdit(text="B verified", status="verified", expected_revision=1),
        )
    with pytest.raises(HTTPException) as conflict:
        dataset.edit_reference(
            db,
            recording["id"],
            dataset.ReferenceEdit(
                text="A stale", status="draft", expected_revision=saved["reference"]["revision"]
            ),
        )
    assert conflict.value.status_code == 409


def test_blind_review_waits_for_all_first_repetitions_and_revisions_after_retry(client, tmp_path):
    recording = import_audio(client)
    client.put(
        f"/api/v1/recordings/{recording['id']}/reference",
        json={"text": "hello world", "status": "verified", "expected_revision": 0},
    )
    manifest = install_model(client, tmp_path)
    register_manifest(client.app.state.db, {**manifest, "id": "second-model"})
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Two models",
            "recording_ids": [recording["id"]],
            "model_ids": [manifest["id"], "second-model"],
        },
    ).json()
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    first, second = claim_job(client.app.state.db, "a"), claim_job(client.app.state.db, "b")
    complete_job(client.app.state.db, first, output())
    body = {"experiment_id": experiment["id"], "recording_id": recording["id"]}
    assert client.post("/api/v1/reviews", json=body).status_code == 409
    fail_job(client.app.state.db, second, "temporary model failure")
    partial = client.post("/api/v1/reviews", json=body).json()
    assert len(partial["outputs"]) == 1
    client.post(f"/api/v1/experiments/{experiment['id']}/retry")
    complete_job(client.app.state.db, claim_job(client.app.state.db, "b"), output())
    assert client.post(f"/api/v1/reviews/{partial['id']}/lock").status_code == 409
    full = client.post("/api/v1/reviews", json=body).json()
    assert full["id"] != partial["id"]
    assert len(full["outputs"]) == 2
    assert client.get(f"/api/v1/reviews/{partial['id']}").status_code == 200


def test_explicit_turkish_code_switch_casing_policy():
    from stt_lab.evaluation import score

    result = score("İZMİR IĞDIR", "izmir ığdır", "en+tr")
    assert result["normalized"]["word"]["rate"] == 0


def test_blind_alignment_retains_the_original_evaluation_version(client, tmp_path):
    from stt_lab.db import encode
    from stt_lab.evaluation import score

    recording, experiment = prepare_experiment(client, tmp_path)
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    complete_job(client.app.state.db, claim_job(client.app.state.db, "w"), output())
    historical = score("İZMİR IĞDIR", "izmir ığdır", "mixed")
    historical["version"] = "unicode-v1"
    with client.app.state.db.transaction() as conn:
        conn.execute("UPDATE evaluations SET scores=?,version='unicode-v1'", (encode(historical),))
    review = client.post(
        "/api/v1/reviews", json={"experiment_id": experiment["id"], "recording_id": recording["id"]}
    ).json()
    assert review["outputs"][0]["alignment"] == historical["alignment"]
