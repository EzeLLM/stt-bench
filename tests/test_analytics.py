from stt_lab.experiments import claim_job, complete_job
from test_experiments import prepare_experiment


def test_language_filter_applies_to_human_reviews(client, tmp_path):
    recording, experiment = prepare_experiment(client, tmp_path)
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    complete_job(
        client.app.state.db,
        claim_job(client.app.state.db, "worker"),
        {"text": "hello", "load_seconds": 0, "inference_seconds": 1, "runtime_version": "test-fixture"},
    )
    review = client.post(
        "/api/v1/reviews", json={"experiment_id": experiment["id"], "recording_id": recording["id"]}
    ).json()
    label = review["outputs"][0]["id"]
    client.put(
        f"/api/v1/reviews/{review['id']}",
        json={"ratings": {label: {"faithfulness": 4, "readability": 4, "rank": 1}}},
    )
    client.post(f"/api/v1/reviews/{review['id']}/lock")
    assert len(client.get(f"/api/v1/compare/{experiment['id']}?language=en").json()["human_reviews"]) == 1
    assert client.get(f"/api/v1/compare/{experiment['id']}?language=ar").json()["human_reviews"] == []


def test_partial_review_progress_survives_but_cannot_lock(client, tmp_path):
    recording, experiment = prepare_experiment(client, tmp_path)
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    complete_job(
        client.app.state.db,
        claim_job(client.app.state.db, "worker"),
        {"text": "hello", "load_seconds": 0, "inference_seconds": 1, "runtime_version": "test-fixture"},
    )
    review = client.post(
        "/api/v1/reviews", json={"experiment_id": experiment["id"], "recording_id": recording["id"]}
    ).json()
    label = review["outputs"][0]["id"]
    assert (
        client.put(
            f"/api/v1/reviews/{review['id']}", json={"ratings": {label: {"faithfulness": 5}}}
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/reviews/{review['id']}").json()["ratings"][label]["faithfulness"] == 5
    assert client.post(f"/api/v1/reviews/{review['id']}/lock").status_code == 422
