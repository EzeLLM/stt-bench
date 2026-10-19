from test_experiments import prepare_experiment


def pair(client):
    secret = client.get("/api/v1/pairing").json()["token"]
    response = client.post(
        "/api/v1/device/pair",
        headers={"Authorization": "Bearer " + secret},
        json={"name": "Physical test fixture", "details": {"os_version": "test", "physical_device": True}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_device_auth_and_idempotent_results(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path, target="iphone")
    assert (
        client.post("/api/v1/device/claim", json={"installed_model_ids": ["test-model"]}).status_code == 401
    )
    device = pair(client)
    headers = {"Authorization": "Bearer " + device["token"]}
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    job = client.post(
        "/api/v1/device/claim", headers=headers, json={"installed_model_ids": ["test-model"]}
    ).json()
    assert "reference" not in job
    assert "snapshot" not in job
    assert "hello world" not in str(job)  # Ground truth is never sent to an inference device.
    assert job["model"]["id"] == "test-model"
    result = {
        "attempt_id": job["attempt_id"],
        "text": "hello world",
        "load_seconds": 0.1,
        "inference_seconds": 0.2,
        "runtime_version": "test-fixture",
        "audio_sha256": job["audio_sha256"],
        "model_revision": job["model"]["revision"],
        "device_conditions": {"thermal_state": "nominal"},
        "execution_location": "device",
        "energy_joules": None,
    }
    url = f"/api/v1/device/jobs/{job['id']}/result"
    assert client.post(url, headers=headers, json=result).status_code == 200
    assert client.post(url, headers=headers, json=result).status_code == 200
    changed = {**result, "text": "different"}
    assert client.post(url, headers=headers, json=changed).status_code == 409


def test_wrong_device_and_hash_rejected(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path, target="iphone")
    one, two = pair(client), pair(client)
    h1, h2 = {"Authorization": "Bearer " + one["token"]}, {"Authorization": "Bearer " + two["token"]}
    client.post(f"/api/v1/experiments/{experiment['id']}/start")
    job = client.post("/api/v1/device/claim", headers=h1, json={"installed_model_ids": ["test-model"]}).json()
    assert client.post(f"/api/v1/device/jobs/{job['id']}/heartbeat", headers=h2).status_code == 403
    result = {
        "attempt_id": job["attempt_id"],
        "text": "hello",
        "inference_seconds": 0.1,
        "load_seconds": 0,
        "runtime_version": "test-fixture",
        "audio_sha256": "0" * 64,
        "model_revision": job["model"]["revision"],
        "execution_location": "device",
        "device_conditions": {},
    }
    assert client.post(f"/api/v1/device/jobs/{job['id']}/result", headers=h1, json=result).status_code == 422


def test_backup_and_export_contain_raw_evidence(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path)
    exported = client.get(f"/api/v1/export/{experiment['id']}").json()
    assert exported["jobs"][0]["snapshot"]["reference"]["text"] == "hello world"
    response = client.post("/api/v1/backup")
    assert response.status_code == 201
    assert response.json()["sha256"]
