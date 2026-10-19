from stt_lab.db import Database
from stt_lab.experiments import claim_job, complete_job
from test_experiments import prepare_experiment


def test_rescore_is_a_new_snapshot_and_original_scores_do_not_change(client, tmp_path):
    recording, experiment = prepare_experiment(client, tmp_path)
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    complete_job(
        client.app.state.db,
        claim_job(client.app.state.db, "w"),
        {"text": "hello world", "load_seconds": 0, "inference_seconds": 1, "runtime_version": "test-fixture"},
    )
    client.post(f"/api/v1/experiments/{experiment['id']}/finalize")
    client.put(
        f"/api/v1/recordings/{recording['id']}/reference",
        json={"text": "hello earth", "status": "verified", "expected_revision": 1},
    )
    response = client.post(f"/api/v1/experiments/{experiment['id']}/evaluations")
    assert response.status_code == 201, response.text
    snapshot = response.json()
    original = client.get(f"/api/v1/compare/{experiment['id']}").json()
    corrected = client.get(f"/api/v1/compare/{experiment['id']}?evaluation_id={snapshot['id']}").json()
    assert original["rows"][0]["metrics"]["word"]["rate"] == 0
    assert corrected["rows"][0]["metrics"]["word"]["rate"] == 0.5
    assert corrected["evaluation_id"] == snapshot["id"]
    assert client.get(f"/api/v1/experiments/{experiment['id']}/evaluations").json()[0]["id"] == snapshot["id"]
    assert (
        client.get(f"/api/v1/experiments/{experiment['id']}/jobs").json()[0]["scores"]["normalized"]["word"][
            "rate"
        ]
        == 0
    )


def test_database_migrations_are_repeatable(tmp_path):
    db = Database(tmp_path)
    Database(tmp_path)
    with db.connect() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
