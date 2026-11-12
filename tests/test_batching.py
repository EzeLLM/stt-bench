import io
import sys
import wave
from pathlib import Path

import pytest
from stt_lab import runners
from stt_lab.analytics import comparison
from stt_lab.experiments import batch_key, claim_job, list_jobs
from stt_lab.worker import run_once
from test_experiments import install_model


def distinct_recording(client, frames):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * frames)
    response = client.post("/api/v1/recordings", files={"file": (f"clip{frames}.wav", buffer.getvalue())})
    assert response.status_code == 201, response.text
    recording = response.json()
    client.put(
        f"/api/v1/recordings/{recording['id']}/reference",
        json={"text": "hello world", "status": "verified", "expected_revision": 0},
    )
    return recording


def grouped_experiment(client, tmp_path, repetitions=2):
    recordings = [distinct_recording(client, 8000 + 800 * i) for i in range(3)]
    for model_id in ("model-a", "model-b"):
        install_model(client, tmp_path, model_id=model_id)
    response = client.post(
        "/api/v1/experiments",
        json={
            "name": "Grouped",
            "recording_ids": [r["id"] for r in recordings],
            "model_ids": ["model-a", "model-b"],
            "settings": {"repetitions": repetitions},
        },
    )
    assert response.status_code == 201, response.text
    client.post(f"/api/v1/experiments/{response.json()['id']}/start")
    return response.json()


def test_each_models_jobs_are_contiguous(client, tmp_path):
    experiment = grouped_experiment(client, tmp_path)
    models = [j["model_id"] for j in list_jobs(client.app.state.db, experiment["id"])]
    assert len(models) == 12
    assert models == sorted(models, key=models.index), "a model's jobs must never be interleaved"
    assert models[:6].count(models[0]) == 6


def test_order_is_reproducible_from_the_seed(client, tmp_path):
    first = grouped_experiment(client, tmp_path)
    recording_ids = [r["id"] for r in client.get("/api/v1/recordings").json()]
    second = client.post(
        "/api/v1/experiments",
        json={
            "name": "Again",
            "recording_ids": recording_ids,
            "model_ids": ["model-a", "model-b"],
            "settings": {"repetitions": 2},
            "seed": 42,
        },
    ).json()

    def order(experiment):
        return [(j["model_id"], j["recording_id"]) for j in list_jobs(client.app.state.db, experiment["id"])]

    assert len(order(first)) == 12
    assert sorted(order(first)) == sorted(order(second))
    assert [m for m, _ in order(first)] == [m for m, _ in order(second)]


def test_claim_continues_with_a_job_that_can_share_the_loaded_model(client, tmp_path):
    experiment = grouped_experiment(client, tmp_path)
    db = client.app.state.db
    first = claim_job(db, "worker")
    follow = claim_job(db, "worker", engine_of=first)
    assert follow["model_id"] == first["model_id"]
    assert follow["id"] != first["id"]
    # Exhaust this model's jobs; a continuation request must then report nothing, not move to the next model.
    for _ in range(4):
        assert claim_job(db, "worker", engine_of=first)["model_id"] == first["model_id"]
    assert claim_job(db, "worker", engine_of=first) is None
    assert claim_job(db, "worker")["model_id"] != first["model_id"], experiment


def test_changed_settings_cannot_share_an_engine(client, tmp_path):
    grouped_experiment(client, tmp_path, repetitions=1)
    db = client.app.state.db
    first = claim_job(db, "worker")
    other = {
        **first,
        "snapshot": {**first["snapshot"], "settings": {**first["snapshot"]["settings"], "temperature": 0.7}},
    }
    assert batch_key(other["snapshot"]) != batch_key(first["snapshot"])
    assert claim_job(db, "worker", engine_of=other) is None


def fake_runner(tmp_path):
    """A real serve loop around a stub model, so the worker protocol is exercised without weights."""
    script = tmp_path / "fake-runner"
    script.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        f"sys.path.insert(0, {str(Path(runners.__file__).parent.parent)!r})\n"
        "from stt_lab import runners\n"
        "loads = []\n"
        "def transcriber(request, details=None):\n"
        "    loads.append(1)\n"
        "    def run(item):\n"
        "        fail = os.environ.get('STT_FAKE_FAIL_ON_AUDIO')\n"
        "        if fail and item['audio'].endswith(fail):\n"
        "            sys.stderr.write('stub model crashed\\n')\n"
        "            sys.stderr.flush()\n"
        "            os._exit(3)\n"
        "        return 'hello world'\n"
        "    return run, 'test-fixture', 'stub'\n"
        "runners.transcriber = transcriber\n"
        "runners.seed_everything = lambda runtime, seed: None\n"
        "runners.serve(sys.stdin)\n"
    )
    script.chmod(0o755)
    return script


def test_session_loads_once_and_labels_reused_engine(monkeypatch):
    loads = []

    def transcriber(request, details=None):
        loads.append(1)
        return (lambda item: "hello"), "test-fixture", "stub"

    monkeypatch.setattr(runners, "transcriber", transcriber)
    monkeypatch.setattr(runners, "seed_everything", lambda runtime, seed: None)
    request = {
        "audio": "a.wav",
        "model": {"runtime": "whisper-transformers"},
        "model_root": "root",
        "settings": {"warmups": 1},
    }
    session = runners.Session()
    first, second = session.handle(request), session.handle({**request, "audio": "b.wav"})
    assert len(loads) == 1
    assert first["load_seconds"] >= 0 and first["loading_condition"] == "new-process-os-cache-uncontrolled"
    assert second["load_seconds"] is None and second["loading_condition"] == "reused-loaded-engine"
    assert (first["engine_runs_before"], second["engine_runs_before"]) == (0, 1)
    with pytest.raises(ValueError, match="does not match"):
        session.handle({**request, "model_root": "other"})


def run_experiment_with_runner(client, tmp_path, runner, repetitions=2):
    recordings = [distinct_recording(client, 8000 + 800 * i) for i in range(3)]
    for model_id in ("model-a", "model-b"):
        install_model(client, tmp_path, model_id=model_id, executable=str(runner))
    experiment = client.post(
        "/api/v1/experiments",
        json={
            "name": "Batched",
            "recording_ids": [r["id"] for r in recordings],
            "model_ids": ["model-a", "model-b"],
            "settings": {"repetitions": repetitions},
        },
    ).json()
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    return experiment, recordings


def test_worker_serves_a_models_jobs_from_one_loaded_engine(client, tmp_path):
    experiment, _ = run_experiment_with_runner(client, tmp_path, fake_runner(tmp_path))
    db = client.app.state.db
    assert run_once(db, "w")  # one call drains a whole model
    done = [j for j in list_jobs(db, experiment["id"]) if j["state"] == "succeeded"]
    assert len(done) == 6 and len({j["model_id"] for j in done}) == 1
    assert sorted(j["output"]["measurements"]["engine_runs_before"] for j in done) == [0, 1, 2, 3, 4, 5]
    assert sum(j["output"]["measurements"]["load_seconds"] is not None for j in done) == 1
    assert run_once(db, "w")
    jobs = list_jobs(db, experiment["id"])
    assert all(j["state"] == "succeeded" for j in jobs)
    # The second model starts a new process, so it pays for its own load.
    assert sum(j["output"]["measurements"]["load_seconds"] is not None for j in jobs) == 2
    assert not run_once(db, "w")


def test_failed_job_discards_the_engine_and_others_still_run(client, tmp_path, monkeypatch):
    experiment, _ = run_experiment_with_runner(client, tmp_path, fake_runner(tmp_path), repetitions=1)
    db = client.app.state.db
    bad = list_jobs(db, experiment["id"])[1]["snapshot"]["recording"]
    monkeypatch.setenv("STT_FAKE_FAIL_ON_AUDIO", bad["asset_path"].rsplit("/", 1)[-1])
    while run_once(db, "w"):
        pass
    jobs = list_jobs(db, experiment["id"])
    failed = [j for j in jobs if j["state"] == "failed"]
    assert len(failed) == 2 and all(j["recording_id"] == bad["id"] for j in failed)
    assert all("Runner exited 3" in j["error"] and "stub model crashed" in j["error"] for j in failed)
    assert len([j for j in jobs if j["state"] == "succeeded"]) == 4
    # The crashed process is never reused, so no engine ever served more than the jobs around the crash.
    served = [j["output"]["measurements"]["engine_runs_before"] for j in jobs if j["state"] == "succeeded"]
    assert max(served) <= 1


def test_cancelled_experiment_stops_the_batch(client, tmp_path):
    experiment, _ = run_experiment_with_runner(client, tmp_path, fake_runner(tmp_path))
    db = client.app.state.db
    first = claim_job(db, "w")
    client.post(f"/api/v1/experiments/{experiment['id']}/cancel")
    assert claim_job(db, "w", engine_of=first) is None


def test_load_time_summary_counts_only_jobs_that_actually_loaded(client, tmp_path):
    experiment, _ = run_experiment_with_runner(client, tmp_path, fake_runner(tmp_path))
    db = client.app.state.db
    while run_once(db, "w"):
        pass
    rows = comparison(db, experiment["id"])["rows"]
    assert len(rows) == 2
    for row in rows:
        assert row["total_jobs"] == 6 and row["latency"]["count"] == 6
        assert row["load_time"]["count"] == 1
