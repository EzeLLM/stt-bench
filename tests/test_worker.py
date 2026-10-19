from stt_lab.experiments import claim_job
from stt_lab.worker import execute, run_once
from test_experiments import prepare_experiment


def test_missing_runtime_fails_without_fake_transcript(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path)
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    assert run_once(client.app.state.db, "test-worker")
    job = client.get(f"/api/v1/experiments/{experiment['id']}/jobs").json()[0]
    assert job["state"] == "failed"
    assert job["output"] is None
    assert "Runner exited" in job["error"]


def test_corrupted_audio_fails_before_model_execution(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path)
    db = client.app.state.db
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    job = claim_job(db, "w")
    (db.root / job["snapshot"]["recording"]["asset_path"]).write_bytes(b"corruption")
    try:
        execute(db, job)
        assert False, "Corruption must never reach inference"
    except ValueError as exc:
        assert "checksum" in str(exc)
