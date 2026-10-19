from test_experiments import prepare_experiment


def test_profile_upload_backup_and_context(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path)
    response = client.post(
        f"/api/v1/experiments/{experiment['id']}/artifacts",
        data={"measurement_kind": "external-trace"},
        files={"file": ("power.trace.zip", b"opaque test profiling artifact")},
    )
    assert response.status_code == 201
    artifact = response.json()
    assert artifact["experiment_id"] == experiment["id"]
    assert artifact["measurement_kind"] == "external-trace"
    assert client.get(f"/api/v1/artifacts/{artifact['id']}").content == b"opaque test profiling artifact"


def test_finalized_experiment_rejects_new_artifacts(client, tmp_path):
    _, experiment = prepare_experiment(client, tmp_path)
    client.post(f"/api/v1/experiments/{experiment['id']}/cancel")
    client.post(f"/api/v1/experiments/{experiment['id']}/finalize")
    response = client.post(
        f"/api/v1/experiments/{experiment['id']}/artifacts",
        data={"measurement_kind": "external-trace"},
        files={"file": ("profile.zip", b"late change")},
    )
    assert response.status_code == 409
