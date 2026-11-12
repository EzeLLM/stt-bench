import sqlite3

from stt_lab.db import Database
from stt_lab.experiments import claim_job, complete_job
from stt_lab.registry import register_manifest
from test_dataset import import_audio
from test_experiments import install_model


def output():
    return {"text": "hello world", "load_seconds": 0, "inference_seconds": 1, "runtime_version": "test-fixture"}


def two_model_experiment(client, tmp_path):
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
    for worker in "ab":
        complete_job(client.app.state.db, claim_job(client.app.state.db, worker), output())
    return recording, experiment


def lock_review(client, experiment, recording, ranks):
    review = client.post(
        "/api/v1/reviews", json={"experiment_id": experiment["id"], "recording_id": recording["id"]}
    ).json()
    ratings = {
        o["id"]: {"faithfulness": 4, "readability": 3, "rank": ranks[i], "comment": ""}
        for i, o in enumerate(review["outputs"])
    }
    assert client.put(f"/api/v1/reviews/{review['id']}", json={"ratings": ratings}).status_code == 200
    locked = client.post(f"/api/v1/reviews/{review['id']}/lock")
    assert locked.status_code == 200, locked.text
    return locked.json()


def test_shortlist_uses_only_locked_reviews(client, tmp_path):
    recording, experiment = two_model_experiment(client, tmp_path)
    url = f"/api/v1/experiments/{experiment['id']}/shortlist"
    before = client.get(url).json()["models"]
    assert {m["model_id"] for m in before} == {"test-model", "second-model"}
    assert all(m["reviews"] == 0 and m["mean_rank"] is None for m in before)

    review = client.post(
        "/api/v1/reviews", json={"experiment_id": experiment["id"], "recording_id": recording["id"]}
    ).json()
    client.put(
        f"/api/v1/reviews/{review['id']}",
        json={"ratings": {review["outputs"][0]["id"]: {"rank": 1, "comment": ""}}},
    )
    unlocked = client.get(url).json()["models"]
    assert all(m["reviews"] == 0 for m in unlocked)

    locked = lock_review(client, experiment, recording, ranks=[1, 2])
    winner = locked["outputs"][0]["model_id"]
    after = {m["model_id"]: m for m in client.get(url).json()["models"]}
    assert after[winner]["reviews"] == 1
    assert after[winner]["mean_rank"] == 1
    assert after[winner]["first_places"] == 1
    assert after[winner]["mean_faithfulness"] == 4
    assert after[winner]["mean_readability"] == 3
    loser = locked["outputs"][1]["model_id"]
    assert after[loser]["mean_rank"] == 2
    assert after[loser]["first_places"] == 0


def test_tied_first_place_counts_for_both(client, tmp_path):
    recording, experiment = two_model_experiment(client, tmp_path)
    lock_review(client, experiment, recording, ranks=[1, 1])
    models = client.get(f"/api/v1/experiments/{experiment['id']}/shortlist").json()["models"]
    assert [m["first_places"] for m in models] == [1, 1]


def test_candidate_flag_is_saved_and_can_be_changed(client, tmp_path):
    _, experiment = two_model_experiment(client, tmp_path)
    base = f"/api/v1/experiments/{experiment['id']}"
    saved = client.put(f"{base}/candidates/test-model", json={"advanced": True, "note": "best Arabic"})
    assert saved.status_code == 200
    models = {m["model_id"]: m for m in client.get(f"{base}/shortlist").json()["models"]}
    assert models["test-model"]["advanced"] is True
    assert models["test-model"]["note"] == "best Arabic"
    assert models["second-model"]["advanced"] is False
    client.put(f"{base}/candidates/test-model", json={"advanced": False})
    models = {m["model_id"]: m for m in client.get(f"{base}/shortlist").json()["models"]}
    assert models["test-model"]["advanced"] is False


def test_candidate_must_belong_to_the_experiment(client, tmp_path):
    _, experiment = two_model_experiment(client, tmp_path)
    response = client.put(
        f"/api/v1/experiments/{experiment['id']}/candidates/not-in-experiment", json={"advanced": True}
    )
    assert response.status_code == 404


def test_migration_from_v2_keeps_existing_data(tmp_path):
    root = tmp_path / "db"
    Database(root)
    conn = sqlite3.connect(root / "lab.sqlite3")
    conn.execute("DROP TABLE candidates")
    conn.execute("PRAGMA user_version=2")
    conn.commit()
    conn.close()
    upgraded = Database(root)
    with upgraded.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        conn.execute("SELECT count(*) FROM candidates").fetchone()
