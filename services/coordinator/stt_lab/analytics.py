import json
from collections import defaultdict

from .db import Database
from .evaluation import aggregate, bootstrap, distribution, paired_penalty
from .experiments import list_jobs


def comparison(db: Database, experiment_id: str, language="", tag="", evaluation_id: str | None = None):
    jobs = list_jobs(db, experiment_id, evaluation_id)
    groups = defaultdict(list)
    for job in jobs:
        snapshot = job["snapshot"]
        if language and snapshot["recording"]["language"] != language:
            continue
        if tag and tag not in snapshot["tags"]:
            continue
        groups[job["model_id"]].append(job)
    rows = []
    scored_by_model = {}
    for model_id, group in groups.items():
        primary = [j for j in group if j["repetition"] == 0 and j["snapshot"]["supported_language"]]
        successes = [j for j in primary if j["state"] == "succeeded" and j["scores"]]
        scored_by_model[model_id] = {j["recording_id"]: j["scores"] for j in successes}
        measured = [j for j in group if j["output"]]
        times = [j["output"]["measurements"]["inference_seconds"] for j in measured]
        model = group[0]["snapshot"]["model"]
        rows.append(
            {
                "model_id": model_id,
                "family": model["family"],
                "variant": model["variant"],
                "repository": model["repository"],
                "revision": model["revision"],
                "runtime": model["runtime"],
                "parity": model["parity"],
                "metrics": aggregate([j["scores"] for j in successes]),
                "strict_metrics": aggregate([j["scores"] for j in successes], "strict"),
                "wer_ci95": bootstrap([j["scores"] for j in successes]),
                "completed_recordings": len(successes),
                "eligible_recordings": len(primary),
                "excluded_unsupported": sum(
                    j["repetition"] == 0 and not j["snapshot"]["supported_language"] for j in group
                ),
                "failed_jobs": sum(j["state"] == "failed" for j in group),
                "total_jobs": len(group),
                "failure_rate": sum(j["state"] == "failed" for j in group) / len(group),
                "stale_references": sum(j["stale_reference"] for j in primary),
                "latency": distribution(times),
                "load_time": distribution([j["output"]["measurements"]["load_seconds"] for j in measured]),
                "rtf": distribution(
                    [
                        j["output"]["measurements"]["inference_seconds"]
                        / j["snapshot"]["recording"]["duration"]
                        for j in measured
                    ]
                ),
                "recording_ids": [j["recording_id"] for j in successes],
                "job_ids": [j["id"] for j in group],
            }
        )
    penalties = []
    for a in rows:
        for b in rows:
            if (
                a["model_id"] != b["model_id"]
                and a["family"] == b["family"]
                and "reference" in a["variant"].lower()
            ):
                penalties.append(
                    {
                        "reference_model_id": a["model_id"],
                        "deployment_model_id": b["model_id"],
                        "attribution": "Deployment penalty; quantization is not isolated from backend/conversion",
                        **paired_penalty(scored_by_model[a["model_id"]], scored_by_model[b["model_id"]]),
                    }
                )
    with db.connect() as conn:
        reviews = []
        eligible_output_ids = {
            j["output"]["id"]
            for group in groups.values()
            for j in group
            if j["output"] and j["snapshot"]["supported_language"]
        }
        for review in conn.execute(
            "SELECT mapping,ratings FROM reviews WHERE experiment_id=? AND locked=1", (experiment_id,)
        ):
            mapping, ratings = json.loads(review[0]), json.loads(review[1])
            for anonymous_id, rating in ratings.items():
                if mapping[anonymous_id] not in eligible_output_ids:
                    continue
                model_id = conn.execute(
                    "SELECT j.model_id FROM outputs o JOIN jobs j ON j.id=o.job_id WHERE o.id=?",
                    (mapping[anonymous_id],),
                ).fetchone()[0]
                reviews.append({"model_id": model_id, **rating})
    return {
        "experiment_id": experiment_id,
        "evaluation_id": evaluation_id,
        "language": language,
        "tag": tag,
        "rows": rows,
        "penalties": penalties,
        "human_reviews": reviews,
        "methodology": "Corpus edit counts; first repetition per recording for accuracy. All measured repetitions for latency. Recording bootstrap CI (1000 resamples, seed 0); unavailable below two recordings. Partial coverage is not a fair overall ranking.",
    }
