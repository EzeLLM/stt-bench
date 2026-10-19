"""Candidates are research leads; only hash-verified manifests can run."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .audio import sha256
from .common import now
from .db import Database, encode

RUNTIMES = Literal[
    "whisper-transformers",
    "qwen-transformers",
    "nemo-parakeet",
    "parakeet-transformers",
    "mlx-audio-qwen",
    "whisperkit",
    "fluidaudio",
]
EUROPEAN = "bg hr cs da nl en et fi fr de el hu it lv lt mt pl pt ro ru sk sl es sv uk".split()
QWEN_LANGUAGES = (
    "zh en yue ar de fr es pt id it ko ru th vi ja tr hi ms nl sv da fi pl cs fil fa el hu mk ro".split()
)


def candidates() -> list[dict]:
    from importlib.resources import files

    return json.loads(files("stt_lab").joinpath("data/catalog.json").read_text())


class Asset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_repository: str | None = None
    source_revision: str | None = None
    source_path: str | None = None


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    precision: str
    quantization: str


class NativeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    compute_units: Literal["cpuOnly", "cpuAndGPU", "cpuAndNeuralEngine", "all"] = "cpuAndNeuralEngine"
    encoder_precision: Literal["int8", "int8-v2", "int4"] = "int8-v2"


class ReferenceOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exclude_auxiliary_vad_head: bool = False


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9._-]{1,100}$")
    family: str
    variant: str
    repository: str = Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    license: str = Field(min_length=1)
    original_publisher: str
    conversion_publisher: str | None = None
    source_checkpoint: str
    parameter_count: int | None = Field(default=None, gt=0)
    runtime: RUNTIMES
    runtime_version: str = Field(min_length=1)
    root: str
    languages: list[str] = Field(min_length=1)
    components: list[Component] = Field(min_length=1)
    files: list[Asset] = Field(min_length=1)
    parity: Literal["not-validated", "published-only", "paired-owner-data"] = "not-validated"
    conversion_procedure: str | None = None
    published_comparisons: list[dict] = Field(default_factory=list)
    known_issues: list[str] = Field(default_factory=list)
    runtime_memory_bytes: int | None = None
    executable: str | None = None
    native_options: NativeOptions | None = None
    reference_options: ReferenceOptions | None = None


def safe_path(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Asset paths must be relative and cannot traverse parent directories")
    value = (root / relative).resolve()
    if not value.is_relative_to(root.resolve()):
        raise ValueError("Asset path escapes its storage root")
    return value


def verify_manifest(db: Database, value: dict) -> dict:
    manifest = Manifest.model_validate(value).model_dump()
    root = safe_path(db.root, manifest["root"])
    if not root.is_dir():
        raise ValueError("Checkpoint directory is missing")
    paths = set()
    total = 0
    for asset in manifest["files"]:
        if asset["path"] in paths:
            raise ValueError("Duplicate checkpoint asset path")
        paths.add(asset["path"])
        path = safe_path(root, asset["path"])
        if not path.is_file():
            raise ValueError(f"Checkpoint asset missing: {asset['path']}")
        if sha256(path) != asset["sha256"]:
            raise ValueError(f"Checkpoint checksum mismatch: {asset['path']}")
        total += path.stat().st_size
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    if actual != paths:
        raise ValueError("Manifest must hash every file in the checkpoint directory")
    return manifest


def register_manifest(db: Database, value: dict) -> dict:
    manifest = verify_manifest(db, value)
    with db.transaction() as conn:
        existing = conn.execute("SELECT manifest FROM models WHERE id=?", (manifest["id"],)).fetchone()
        if existing and Manifest.model_validate(json.loads(existing[0])).model_dump() != manifest:
            raise ValueError("Registered model IDs are immutable; use a new variant ID")
        conn.execute("INSERT OR IGNORE INTO models VALUES(?,?,?)", (manifest["id"], encode(manifest), now()))
    return manifest


def installed(db: Database) -> list[dict]:
    with db.connect() as conn:
        rows = [json.loads(row[0]) for row in conn.execute("SELECT manifest FROM models ORDER BY id")]
    for row in rows:
        row["size_bytes"] = sum(
            (safe_path(db.root, row["root"]) / f["path"]).stat().st_size
            for f in row["files"]
            if (safe_path(db.root, row["root"]) / f["path"]).is_file()
        )
        row["status"] = "registered"
    return rows
