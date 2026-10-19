"""Versioned, script-preserving metrics. Rates are fractions, not percentages."""

import math
import random
import statistics
import unicodedata

import regex
from rapidfuzz.distance import Levenshtein

VERSION = "unicode-v2"


def normalize(text: str, language: str, strict: bool = False) -> str:
    text = unicodedata.normalize("NFC", text)
    if not strict:
        # Explicit tr-containing labels use Turkish casing for the Latin text. Generic mixed labels retain
        # Unicode lowercasing; strict scores are provided because per-word language attribution is ambiguous.
        if "tr" in language.split("+"):
            text = text.replace("I", "ı").replace("İ", "i")
        text = text.lower()
        text = "".join(" " if unicodedata.category(c).startswith("P") else c for c in text)
    return " ".join(text.split())


def _alignment(reference: list[str], hypothesis: list[str]) -> tuple[dict, list[dict]]:
    counts = {"substitutions": 0, "deletions": 0, "insertions": 0, "reference_length": len(reference)}
    alignment = []
    names = {"equal": "equal", "replace": "substitute", "delete": "delete", "insert": "insert"}
    for opcode in Levenshtein.opcodes(reference, hypothesis):
        a = reference[opcode.src_start : opcode.src_end]
        b = hypothesis[opcode.dest_start : opcode.dest_end]
        if opcode.tag == "replace":
            counts["substitutions"] += len(a)
        elif opcode.tag == "delete":
            counts["deletions"] += len(a)
        elif opcode.tag == "insert":
            counts["insertions"] += len(b)
        alignment.append({"kind": names[opcode.tag], "reference": a, "hypothesis": b})
    counts["rate"] = _rate(counts)
    return counts, alignment


def _rate(counts: dict) -> float | None:
    n = counts["reference_length"]
    return sum(counts[k] for k in ("substitutions", "deletions", "insertions")) / n if n else None


def score(reference: str, hypothesis: str, language: str) -> dict:
    result = {
        "version": VERSION,
        "language": language,
        "normalized_reference": normalize(reference, language),
        "normalized_hypothesis": normalize(hypothesis, language),
    }
    for label, strict in (("strict", True), ("normalized", False)):
        a, b = normalize(reference, language, strict), normalize(hypothesis, language, strict)
        word, alignment = _alignment(a.split(), b.split())
        char, char_alignment = _alignment(regex.findall(r"\X", a), regex.findall(r"\X", b))
        result[label] = {"word": word, "character": char}
        if not strict:
            result["alignment"] = alignment
            result["character_alignment"] = char_alignment
    return result


def aggregate(scores: list[dict], mode: str = "normalized") -> dict:
    result = {}
    for unit in ("word", "character"):
        counts = {
            key: sum(s[mode][unit][key] for s in scores)
            for key in ("substitutions", "deletions", "insertions", "reference_length")
        }
        counts["rate"] = _rate(counts)
        result[unit] = counts
    return result


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * fraction
    lo = int(pos)
    return ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (pos - lo)


def distribution(values: list[float]) -> dict:
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("Measurements must be finite and nonnegative")
    return {
        "count": len(values),
        "mean": statistics.mean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p90": _quantile(values, 0.9) if values else None,
        "p95": _quantile(values, 0.95) if values else None,
        "stddev": statistics.stdev(values) if len(values) > 1 else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def bootstrap(scores: list[dict], seed: int = 0, samples: int = 1000) -> list[float] | None:
    if len(scores) < 2 or aggregate(scores)["word"]["rate"] is None:
        return None
    rng = random.Random(seed)
    rates = [aggregate(rng.choices(scores, k=len(scores)))["word"]["rate"] for _ in range(samples)]
    rates = [x for x in rates if x is not None]
    return [_quantile(rates, 0.025), _quantile(rates, 0.975)] if rates else None


def paired_penalty(reference: dict[str, dict], deployment: dict[str, dict], seed: int = 0) -> dict:
    keys = sorted(reference.keys() & deployment.keys())
    a, b = [reference[k] for k in keys], [deployment[k] for k in keys]
    ar, br = aggregate(a)["word"]["rate"], aggregate(b)["word"]["rate"]
    result = {
        "paired_recordings": len(keys),
        "recording_ids": keys,
        "penalty": br - ar if ar is not None and br is not None else None,
        "ci95": None,
    }
    if len(keys) > 1:
        rng, deltas = random.Random(seed), []
        for _ in range(1000):
            selected = rng.choices(keys, k=len(keys))
            x = aggregate([reference[k] for k in selected])["word"]["rate"]
            y = aggregate([deployment[k] for k in selected])["word"]["rate"]
            if x is not None and y is not None:
                deltas.append(y - x)
        if deltas:
            result["ci95"] = [_quantile(deltas, 0.025), _quantile(deltas, 0.975)]
    return result
