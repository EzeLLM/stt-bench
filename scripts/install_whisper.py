"""Idempotently prepare a pinned original Turbo checkpoint and local manifest."""

import json
from pathlib import Path

from fetch_checkpoint import download
from stt_lab.db import Database
from stt_lab.registry import register_manifest

root = Path(__file__).resolve().parents[1]
data = root / "data"
revision = "41f01f3fe87f28c78e2fbf8b568835947dd65ed9"
inventory = download(
    "openai/whisper-large-v3-turbo",
    revision,
    data / "models/whisper-turbo-reference",
    ["*.json", "*.txt", "*.safetensors"],
)
languages = json.loads((root / "docs/research/openai--whisper-large-v3-turbo.json").read_text())["cardData"][
    "language"
]
manifest = {
    "id": "whisper-turbo-reference-fp32",
    "family": "Whisper Large-v3 Turbo",
    "variant": "Original reference · FP32 compute",
    "repository": inventory["repository"],
    "revision": revision,
    "license": "MIT",
    "original_publisher": "OpenAI",
    "source_checkpoint": inventory["repository"] + "@" + revision,
    "runtime": "whisper-transformers",
    "runtime_version": "4.57.6",
    "root": "models/whisper-turbo-reference",
    "languages": languages,
    "components": [
        {
            "name": "encoder and decoder",
            "precision": "FP16 checkpoint weights, upcast to FP32 compute",
            "quantization": "none",
        }
    ],
    "files": inventory["files"],
    "executable": str(root / ".venv-reference/bin/python"),
    "parity": "not-validated",
}
register_manifest(Database(data), manifest)
(data / "whisper-reference-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("Registered pinned original Whisper Turbo. No speech benchmark has been run.")
