"""
Logs every eval run to MLflow: the settings it ran with (params) and the scores (metrics),
so runs can be compared side by side, e.g. reranker on vs off, a new model, a new threshold.

    docker compose run --rm --no-deps -p 5001:5000 api \
        mlflow ui --host 0.0.0.0 --backend-store-uri sqlite:///evals/mlflow.db

then open http://localhost:5001
"""

import os
import re
from pathlib import Path

from app.config import settings

HERE = Path(__file__).parent
TRACKING_URI = f"sqlite:///{HERE / 'mlflow.db'}"
EXPERIMENT = "resolvr-evals"


def fraction(value) -> float | None:
    """the report keeps scores like "38/44", mlflow wants plain numbers"""
    if isinstance(value, (int, float)):
        return float(value)
    match = re.fullmatch(r"(\d+)/(\d+)", str(value).split(" ")[0])
    if not match or int(match.group(2)) == 0:
        return None
    return int(match.group(1)) / int(match.group(2))


def metric_name(*parts: str) -> str:
    #mlflow only allows letters, digits and a few symbols in names
    return ".".join(re.sub(r"[^\w-]+", "_", p).strip("_") for p in parts)


def collect_metrics(results: dict) -> dict[str, float]:
    metrics = {}
    for mode, m in results.get("retrieval", {}).get("modes", {}).items():
        n = m["n"] or 1
        for k in ("recall@1", "recall@3", "recall@5"):
            metrics[metric_name("retrieval", mode, k.replace("@", "_at_"))] = m[k] / n
        metrics[metric_name("retrieval", mode, "mrr")] = m["mrr"]
        metrics[metric_name("retrieval", mode, "kb_in_top5")] = m["kb_article_in_top5"] / n
        metrics[metric_name("retrieval", mode, "p50_ms")] = m["p50_ms"]
        if "right_ticket_first" in m:
            metrics[metric_name("retrieval", mode, "right_ticket_first")] = m["right_ticket_first"] / n
            metrics[metric_name("retrieval", mode, "ticket_precision")] = m["ticket_precision"]

    for field, m in results.get("classification", {}).items():
        for key, value in m.items():
            if key in ("accuracy", "macro_f1", "critical_recall", "under_triage", "over_triage", "off_by_one"):
                number = fraction(value)
                if number is not None:
                    metrics[metric_name("classify", field, key)] = number

    for key, value in results.get("drafting", {}).items():
        number = fraction(value) if value is not None else None
        if number is not None:
            metrics[metric_name("drafting", key)] = number
    return metrics


def log_run(results: dict, retrieval_only: bool) -> None:
    #mlflow tries to read the git commit, the container has no git binary so keep it quiet
    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
    try:
        import mlflow
    except ImportError:
        print("mlflow not installed, skipping run tracking")
        return

    mlflow.set_tracking_uri(TRACKING_URI)
    #keep the run files next to the db (evals/mlartifacts) instead of wherever the script ran from
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        mlflow.create_experiment(EXPERIMENT, artifact_location=(HERE / "mlartifacts").as_uri())
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=f"{'retrieval' if retrieval_only else 'full'} {results['run_at']}"):
        mlflow.log_params({
            "llm_model": results["model"],
            "llm_fast_model": settings.gemini_fast_model_name,
            "embedding_model": settings.embedding_model,
            "reranker_enabled": settings.reranker_enabled,
            "reranker_model": settings.reranker_model,
            "abstain_threshold": settings.abstain_threshold,
            "retrieval_candidates": settings.retrieval_candidates,
            "retrieval_top_k": settings.retrieval_top_k,
            "heldout_rows": results["rows"],
            "retrieval_only": retrieval_only,
        })
        mlflow.log_metrics(collect_metrics(results))
        #the markdown report + confusion matrix images, viewable from the run page
        for path in (HERE / "results").glob("*"):
            if path.suffix in (".md", ".json", ".png"):
                mlflow.log_artifact(str(path))
    print(f"run logged to mlflow ({TRACKING_URI})")
