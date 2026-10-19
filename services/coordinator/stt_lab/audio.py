"""Deterministic audio preparation directly from retained originals."""

import array
import hashlib
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

PIPELINE = "pcm16-mono-16k-v1"
MAX_DURATION = 4 * 3600


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(args: list[str], timeout: int = 120) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Audio processing failed: {exc.stderr[-1500:]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Audio processing exceeded its time limit") from exc
    return result.stdout


def prepare(source: Path, target: Path) -> dict:
    info = json.loads(
        command(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)])
    )
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise ValueError("No decodable audio stream found")
    stream = streams[0]
    duration = float(info.get("format", {}).get("duration", stream.get("duration", 0)))
    if not math.isfinite(duration) or duration <= 0 or duration > MAX_DURATION:
        raise ValueError("Recording must contain between 0 and 4 hours of audio")
    args = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-xerror",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-y",
        str(target),
    ]
    command(args, timeout=max(120, int(duration * 2)))
    peaks, silent, clipped, frames = [], 0, 0, 0
    with wave.open(str(target), "rb") as wav:
        total = wav.getnframes()
        if total == 0:
            raise ValueError("Decoded audio is empty")
        bucket = max(1, math.ceil(total / 800))
        while chunk := wav.readframes(bucket):
            samples = array.array("h", chunk)
            if sys.byteorder != "little":
                samples.byteswap()
            frames += len(samples)
            silent += sum(abs(x) < 33 for x in samples)  # approximately -60 dBFS
            clipped += sum(abs(x) >= 32760 for x in samples)
            peaks.append(round(max(abs(x) for x in samples) / 32768, 5))
    return {
        "pipeline": PIPELINE,
        "source": info,
        "source_format": info.get("format", {}).get("format_name", "unknown"),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": stream.get("channels"),
        "duration": frames / 16000,
        "canonical": {
            "codec": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
            "sha256": sha256(target),
            "size_bytes": target.stat().st_size,
        },
        "waveform": peaks,
        "diagnostics": {
            "silence_fraction": silent / frames,
            "clipping_fraction": clipped / frames,
            "silence_threshold_dbfs": -60,
            "note": "Sample-level diagnostics; no VAD or audio enhancement applied",
        },
        "preprocessing": {
            "version": PIPELINE,
            "ffmpeg": command(["ffmpeg", "-version"]).splitlines()[0],
            "arguments": [
                "<original>" if x == str(source) else "<canonical>" if x == str(target) else x for x in args
            ],
        },
    }
