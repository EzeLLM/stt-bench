#!/usr/bin/env python3
"""Stage exact HF files with TLS + Git/LFS integrity checks. No audio is uploaded."""

import argparse
import fnmatch
import hashlib
import http.client
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


def fetch_resumable(url: str, partial: Path, expected_size: int | None, attempts: int = 12) -> None:
    """Download into `partial`, resuming with HTTP Range after dropped or stalled connections.

    urllib returns empty reads on a dropped connection instead of raising, so a truncated body would
    otherwise surface only as a checksum mismatch. The byte count is checked against the upstream size here;
    the SHA-256 or Git blob check in `download` remains the integrity gate.
    """
    for attempt in range(attempts):
        offset = partial.stat().st_size if partial.exists() else 0
        if expected_size is not None and offset == expected_size:
            return
        if expected_size is not None and offset > expected_size:
            partial.unlink()
            offset = 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
                resumed = response.status == 206
                with partial.open("ab" if resumed else "wb") as file:
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        file.write(chunk)
        except (OSError, http.client.HTTPException) as error:
            print(f"Transfer interrupted ({error}); resuming, attempt {attempt + 2}/{attempts}", flush=True)
            time.sleep(min(60, 5 * 2**attempt))
            continue
        if expected_size is None or partial.stat().st_size == expected_size:
            return
    raise ValueError(f"Incomplete transfer after {attempts} attempts: {url}")


def download(repository: str, revision: str, destination: Path, patterns: list[str]) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repository) or not re.fullmatch(
        r"[a-f0-9]{40}", revision
    ):
        raise ValueError("A repository identity and full immutable 40-character revision are required")
    with urllib.request.urlopen(
        f"https://huggingface.co/api/models/{repository}/revision/{revision}?blobs=true", timeout=60
    ) as response:
        metadata = json.load(response)
    if metadata["sha"] != revision:
        raise ValueError("Repository revision mismatch")
    selected = [
        f for f in metadata["siblings"] if any(fnmatch.fnmatchcase(f["rfilename"], p) for p in patterns)
    ]
    if not selected:
        raise ValueError("No files match the requested patterns")
    print(f"Selected {len(selected)} files, {sum(f.get('size', 0) for f in selected):,} bytes", flush=True)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for info in selected:
        relative = info["rfilename"]
        target = (destination / relative).resolve()
        if not target.is_relative_to(destination) or target == destination:
            raise ValueError("Invalid upstream file path")
        target.parent.mkdir(parents=True, exist_ok=True)
        expected_lfs = info.get("lfs", {}).get("sha256")

        def verify(path):
            sha, git = hashlib.sha256(), hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
            with path.open("rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    sha.update(chunk)
                    git.update(chunk)
            if expected_lfs:
                valid = sha.hexdigest() == expected_lfs
            else:
                valid = git.hexdigest() == info["blobId"]
            return valid, sha.hexdigest()

        valid, digest = verify(target) if target.exists() else (False, None)
        if not valid:
            temporary = target.with_name(target.name + ".download")
            url = f"https://huggingface.co/{repository}/resolve/{revision}/" + urllib.parse.quote(
                relative, safe="/"
            )
            fetch_resumable(url, temporary, info.get("size"))
            valid, digest = verify(temporary)
            if not valid:
                temporary.unlink(missing_ok=True)
                raise ValueError(f"Upstream checksum verification failed: {relative}")
            temporary.replace(target)
        manifest.append({"path": relative, "sha256": digest})
        print("Verified", relative, flush=True)
    return {
        "repository": repository,
        "revision": revision,
        "license": metadata.get("cardData", {}).get("license"),
        "files": manifest,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--include", action="append", required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="Inventory output outside the checkpoint directory"
    )
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.destination.resolve()):
        parser.error("Inventory must be outside the checkpoint directory")
    result = download(args.repository, args.revision, args.destination, args.include)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
