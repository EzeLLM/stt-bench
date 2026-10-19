"""Stage original reference assets; never install converted weights as originals."""

import argparse
import json
from pathlib import Path

from fetch_checkpoint import download
from stt_lab.db import Database
from stt_lab.registry import EUROPEAN, QWEN_LANGUAGES, register_manifest

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    "qwen-0.6b": (
        "Qwen/Qwen3-ASR-0.6B",
        "5eb144179a02acc5e5ba31e748d22b0cf3e303b0",
        "Qwen3-ASR 0.6B",
        "qwen-transformers",
        "0.0.6",
        ".venv-qwen",
        "qwen-0.6b-reference",
        "Qwen",
    ),
    "qwen-1.7b": (
        "Qwen/Qwen3-ASR-1.7B",
        "7278e1e70fe206f11671096ffdd38061171dd6e5",
        "Qwen3-ASR 1.7B",
        "qwen-transformers",
        "0.0.6",
        ".venv-qwen",
        "qwen-1.7b-reference",
        "Qwen",
    ),
    "parakeet-v3": (
        "nvidia/parakeet-tdt-0.6b-v3",
        "541d1f99c6b0c3cd0b11a95167540bb8edefd82b",
        "Parakeet TDT 0.6B v3",
        "parakeet-transformers",
        "5.20.1",
        ".venv-parakeet",
        "parakeet-v3-reference",
        "NVIDIA",
    ),
    "parakeet-ultra": (
        "moondream/parakeet-ultra",
        "73175eb7aeb0d82f1e2a6b53b3aabc10a90bcd0b",
        "Parakeet Ultra",
        "parakeet-transformers",
        "5.20.1",
        ".venv-parakeet",
        "parakeet-ultra-reference",
        "Moondream",
    ),
}


def install(name):
    repo, revision, family, runtime, version, environment, directory, publisher = SPECS[name]
    destination = ROOT / "data/models" / directory
    inventory = download(repo, revision, destination, ["*.json", "*.txt", "*.safetensors"])
    assets = [
        {**f, "source_repository": repo, "source_revision": revision, "source_path": f["path"]}
        for f in inventory["files"]
    ]
    issues = []
    if name == "parakeet-ultra":
        # Ultra publishes the same v3 tokenizer but not the HF processor descriptors. Their provenance is explicit.
        processor = download(
            "nvidia/parakeet-tdt-0.6b-v3",
            SPECS["parakeet-v3"][1],
            destination,
            ["processor_config.json", "tokenizer_config.json", "generation_config.json"],
        )
        assets += [
            {
                **f,
                "source_repository": processor["repository"],
                "source_revision": processor["revision"],
                "source_path": f["path"],
            }
            for f in processor["files"]
        ]
        issues.append(
            "Reference condition: Transformers TDT core, auxiliary VAD head explicitly excluded; published Photon pipeline is not reproduced. V3 processor and generation descriptors staged from the pinned NVIDIA source. Owner-data parity unvalidated."
        )
    manifest = {
        "id": name + ("-tdt-core-no-vad-fp32" if name == "parakeet-ultra" else "-reference-fp32"),
        "family": family,
        "variant": "Original reference · FP32 compute"
        + (" · auxiliary VAD excluded" if name == "parakeet-ultra" else ""),
        "repository": repo,
        "revision": revision,
        "license": inventory["license"],
        "original_publisher": publisher,
        "source_checkpoint": repo + "@" + revision,
        "runtime": runtime,
        "runtime_version": version,
        "root": "models/" + directory,
        "languages": QWEN_LANGUAGES if name.startswith("qwen") else EUROPEAN,
        "components": [
            {
                "name": "ASR encoder and decoder",
                "precision": "Original checkpoint tensors upcast to FP32 compute; integer buffers retained",
                "quantization": "none",
            }
        ],
        "files": sorted(assets, key=lambda x: x["path"]),
        "executable": str(ROOT / environment / "bin/python"),
        "parity": "not-validated",
        "known_issues": issues,
    }
    if name == "parakeet-ultra":
        manifest["reference_options"] = {"exclude_auxiliary_vad_head": True}
        manifest["components"].append(
            {
                "name": "auxiliary vad_head",
                "precision": "Original tensors retained on disk; excluded from the no-VAD TDT execution condition",
                "quantization": "none",
            }
        )
    register_manifest(Database(ROOT / "data"), manifest)
    (ROOT / "data" / (name + "-manifest.json")).write_text(json.dumps(manifest, indent=2) + "\n")
    print("Registered", manifest["id"], "without claiming conversion or publisher-runtime parity")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=[*SPECS, "all"], default="all")
    args = parser.parse_args()
    for name in SPECS if args.model == "all" else [args.model]:
        install(name)
