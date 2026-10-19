import hashlib
import io
import subprocess
import wave

import pytest


def audio_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 8000)
    return buffer.getvalue()


def import_audio(client):
    response = client.post("/api/v1/recordings", files={"file": ("my memo.wav", audio_bytes(), "audio/wav")})
    assert response.status_code == 201, response.text
    return response.json()


def test_lossless_import_and_duplicate_detection(client):
    recording = import_audio(client)
    assert recording["source_sha256"] == hashlib.sha256(audio_bytes()).hexdigest()
    assert recording["duration"] == 0.5
    assert recording["sample_rate"] == 16000
    assert recording["diagnostics"]["silence_fraction"] == 1
    assert len(recording["waveform"]) > 0
    assert client.get(f"/api/v1/recordings/{recording['id']}/audio").status_code == 200
    duplicate = client.post("/api/v1/recordings", files={"file": ("another.wav", audio_bytes())})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["recording_id"] == recording["id"]
    assert len(client.get("/api/v1/recordings").json()) == 1


def test_corrupt_audio_rejected(client):
    response = client.post("/api/v1/recordings", files={"file": ("bad.m4a", b"invalid audio")})
    assert response.status_code == 422
    assert client.get("/api/v1/recordings").json() == []


@pytest.mark.parametrize("extension", ["m4a", "flac", "mp3", "aiff", "caf"])
def test_real_codec_conversion(client, tmp_path, extension):
    source = tmp_path / "in.wav"
    target = tmp_path / f"memo.{extension}"
    source.write_bytes(audio_bytes())
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), str(target)], check=True)
    response = client.post("/api/v1/recordings", files={"file": (target.name, target.read_bytes())})
    assert response.status_code == 201, response.text
    assert response.json()["canonical"]["sample_rate"] == 16000
    assert response.json()["canonical"]["channels"] == 1


def test_references_are_versioned_and_conflict_safe(client):
    recording = import_audio(client)
    url = f"/api/v1/recordings/{recording['id']}/reference"
    first = client.put(url, json={"text": "مرحبا İzmir", "status": "draft", "expected_revision": 0})
    assert first.status_code == 200
    second = client.put(url, json={"text": "مرحبا İzmir!", "status": "verified", "expected_revision": 1})
    assert second.status_code == 200
    conflict = client.put(url, json={"text": "old editor", "status": "draft", "expected_revision": 1})
    assert conflict.status_code == 409
    history = client.get(url + "/history").json()
    assert [x["revision"] for x in history] == [2, 1]
    assert history[1]["text"] == "مرحبا İzmir"


def test_labels_and_search(client):
    recording = import_audio(client)
    response = client.patch(
        f"/api/v1/recordings/{recording['id']}", json={"language": "tr", "tags": ["Fast speech", "Technical"]}
    )
    assert response.status_code == 200
    assert len(client.get("/api/v1/recordings?language=tr&tag=Technical").json()) == 1
    assert len(client.get("/api/v1/recordings?language=ar").json()) == 0
