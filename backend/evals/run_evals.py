"""
Offline evaluation on the held-out set (data/eval/heldout.csv). These complaints were never
loaded into the database, so retrieval can't cheat by finding the exact text.

    docker compose exec api python -m evals.run_evals                  # everything
    docker compose exec api python -m evals.run_evals --retrieval-only # no llm calls needed

Writes evals/results/report.md, metrics.json and confusion matrix images.

A. retrieval    recall@k and MRR for keyword vs vector vs hybrid vs hybrid + reranker
B. classify     confusion matrices + per class precision/recall/F1 for category, product,
                severity, sentiment. severity also gets critical recall, under-triage and
                off-by-one, with and without the escalate-only rules
C. drafting     citation validity and coverage, abstention correctness, groundedness judged by the llm
D. operations   latency, tokens and estimated cost per complaint
"""

import argparse
import csv
import json
import os
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from app import embeddings
from app.config import settings
from app.db import SessionLocal
from app.llm import LLMError, call_json, estimate_cost
from app.models.tickets import SENTIMENTS
from app.pipeline.classify import active_categories, classify
from app.pipeline.draft import draft_resolution
from app.pipeline.pii import redact
from app.pipeline.retrieve import hybrid_search
from app.pipeline.rules import SEVERITY_ORDER, apply_rules
from app.pipeline.validate import citation_problems

DATA = Path(os.getenv("DATA_DIR", "/data"))
OUT = Path(__file__).parent / "results"

JUDGE_SYSTEM = """You check whether a support resolution step is supported by the source it cites.
Answer supported=true only if the source text clearly contains or directly implies the step.
Reply with JSON only."""
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"supported": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["supported", "reason"],
}


def load_rows(limit: int | None) -> list[dict]:
    with (DATA / "eval" / "heldout.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[:limit] if limit else rows


def relevant(row: dict) -> set[str]:
    return {r for r in (row["relevant_kb"].split("|") + row["relevant_tickets"].split("|")) if r}


def pace():
    time.sleep(settings.llm_min_interval_ms / 1000)


#---------------- A. retrieval ----------------

def eval_retrieval(db, rows: list[dict]) -> dict:
    modes = {
        "keyword only": ("keyword", False),
        "vector only": ("vector", False),
        "hybrid (rrf)": ("hybrid", False),
        "hybrid + reranker": ("hybrid", True),
    }
    in_scope = [r for r in rows if r["expect_abstain"] != "true"]
    results = {}
    for name, (mode, rerank) in modes.items():
        stats = {"r@1": 0, "r@3": 0, "r@5": 0, "rr": 0.0, "kb@5": 0, "n": 0, "ms": []}
        per_kind = Counter()
        for row in in_scope:
            text, _ = redact(row["complaint"])
            qvec = embeddings.embed_query(text)
            t0 = time.perf_counter()
            hits = hybrid_search(db, text, qvec, mode=mode, top_k=5, rerank=rerank)
            stats["ms"].append((time.perf_counter() - t0) * 1000)
            refs = [h.ref for h in hits]
            rel = relevant(row)
            ranks = [i for i, r in enumerate(refs, start=1) if r in rel]
            first = ranks[0] if ranks else None
            stats["n"] += 1
            stats["r@1"] += bool(first and first <= 1)
            stats["r@3"] += bool(first and first <= 3)
            stats["r@5"] += bool(first)
            stats["rr"] += 1 / first if first else 0
            stats["kb@5"] += any(r in rel for r in refs if r.startswith("KB-"))
            if first == 1:
                per_kind[row["kind"]] += 1
        n = stats["n"]
        results[name] = {
            "n": n,
            "recall@1": stats["r@1"],
            "recall@3": stats["r@3"],
            "recall@5": stats["r@5"],
            "mrr": round(stats["rr"] / n, 3),
            "kb_article_in_top5": stats["kb@5"],
            "p50_ms": round(statistics.median(stats["ms"]), 1),
            "top1_by_kind": dict(per_kind),
        }
        print(f"  {name:18s} r@1 {stats['r@1']}/{n}  r@5 {stats['r@5']}/{n}  mrr {results[name]['mrr']}")
    kinds = Counter(r["kind"] for r in in_scope)
    return {"modes": results, "kinds": dict(kinds)}


#---------------- B. classification ----------------

def eval_classification(db, rows: list[dict]) -> tuple[dict, list[dict]]:
    in_scope = [r for r in rows if r["expect_abstain"] != "true"]
    preds = []
    for i, row in enumerate(in_scope, start=1):
        text, _ = redact(row["complaint"])
        try:
            labels, result = classify(db, text)
        except LLMError as exc:
            print(f"  [{i}] classify failed: {exc}")
            continue
        with_rules, _, fired = apply_rules(row["complaint"], labels["severity"], labels["critical_reason"])
        preds.append({
            "row": row,
            "labels": labels,
            "severity_rules": with_rules,
            "rules_fired": fired,
            "latency_s": result.latency_s,
            "tokens": result.prompt_tokens + result.completion_tokens,
            "cost": estimate_cost(result.prompt_tokens, result.completion_tokens),
        })
        print(f"  [{i}/{len(in_scope)}] {row['eval_id']} -> {labels['category']} / {with_rules}")
        pace()

    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    report = {}
    fields = {
        "category": ("expected_category", lambda p: p["labels"]["category"] or "none"),
        "product": ("expected_product", lambda p: p["labels"]["product"] or "none"),
        "severity (with rules)": ("expected_severity", lambda p: p["severity_rules"]),
        "severity (model only)": ("expected_severity", lambda p: p["labels"]["severity"]),
        "sentiment": ("expected_sentiment", lambda p: p["labels"]["sentiment"]),
    }
    for field, (gold_key, get) in fields.items():
        y_true = [p["row"][gold_key] for p in preds]
        y_pred = [get(p) for p in preds]
        labels = sorted(set(y_true) | set(y_pred), key=lambda x: (SEVERITY_ORDER.get(x, 9), x))
        if field.startswith("sentiment"):
            labels = [s for s in SENTIMENTS if s in set(y_true) | set(y_pred)]
        report[field] = {
            "accuracy": f"{sum(a == b for a, b in zip(y_true, y_pred))}/{len(y_true)}",
            "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 3),
            "per_class": classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0),
            "labels": labels,
            "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        }
        save_confusion(field, labels, report[field]["matrix"])

    for key, get in (("with rules", lambda p: p["severity_rules"]), ("model only", lambda p: p["labels"]["severity"])):
        gold = [SEVERITY_ORDER[p["row"]["expected_severity"]] for p in preds]
        pred = [SEVERITY_ORDER[get(p)] for p in preds]
        critical = [(g, q) for g, q in zip(gold, pred) if g == 3]
        report[f"severity metrics ({key})"] = {
            "critical_recall": f"{sum(q == 3 for _, q in critical)}/{len(critical)}",
            "under_triage": f"{sum(q < g for g, q in zip(gold, pred))}/{len(gold)}",
            "over_triage": f"{sum(q > g for g, q in zip(gold, pred))}/{len(gold)}",
            "off_by_one": f"{sum(abs(q - g) == 1 for g, q in zip(gold, pred))}/{len(gold)}",
        }
    return report, preds


def save_confusion(field: str, labels: list[str], matrix: list[list[int]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    size = max(4, 0.55 * len(labels) + 2)
    fig, ax = plt.subplots(figsize=(size, size))
    ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.set_xlabel("predicted")
    ax.set_ylabel("expected")
    ax.set_title(field)
    top = max((max(r) for r in matrix), default=1) or 1
    for i, r in enumerate(matrix):
        for j, v in enumerate(r):
            if v:
                ax.text(j, i, v, ha="center", va="center", fontsize=8, color="white" if v > top / 2 else "black")
    fig.tight_layout()
    name = field.replace(" ", "_").replace("(", "").replace(")", "")
    fig.savefig(OUT / f"confusion_{name}.png", dpi=120)
    plt.close(fig)


#---------------- C. drafting ----------------

def judge_step(step: str, source_text: str) -> bool | None:
    prompt = f"Step:\n{step}\n\nSource:\n{source_text[:3000]}"
    try:
        result = call_json("judge", JUDGE_SYSTEM, prompt, JUDGE_SCHEMA, fast=True)
    except LLMError:
        return None
    return bool((result.data or {}).get("supported"))


def eval_drafting(db, rows: list[dict], preds: list[dict], judge_limit: int) -> dict:
    by_id = {p["row"]["eval_id"]: p for p in preds}
    stats = Counter()
    latencies, tokens, costs = [], [], []
    judged = supported = 0
    for i, row in enumerate(rows, start=1):
        text, _ = redact(row["complaint"])
        t0 = time.perf_counter()
        qvec = embeddings.embed_query(text)
        sources = hybrid_search(db, text, qvec)
        pred = by_id.get(row["eval_id"])
        labels = pred["labels"] if pred else {"category": None, "product": None, "severity": "medium", "in_scope": True}
        expect_abstain = row["expect_abstain"] == "true"
        best = max((s.similarity for s in sources), default=0)

        abstained = not labels.get("in_scope", True) or best < settings.abstain_threshold
        draft = None
        call_tokens = pred["tokens"] if pred else 0
        call_cost = pred["cost"] if pred else 0.0
        if not abstained:
            try:
                draft, result = draft_resolution(text, labels, sources)
                call_tokens += result.prompt_tokens + result.completion_tokens
                call_cost += estimate_cost(result.prompt_tokens, result.completion_tokens)
                abstained = draft["abstain"] or not draft["steps"]
            except LLMError as exc:
                print(f"  [{i}] draft failed: {exc}")
                continue
            pace()

        elapsed = time.perf_counter() - t0 + (pred["latency_s"] if pred else 0)
        latencies.append(elapsed)
        tokens.append(call_tokens)
        costs.append(call_cost)
        stats["n"] += 1
        stats["abstain_correct"] += abstained == expect_abstain
        stats["expected_abstain"] += expect_abstain
        stats["abstained_when_expected"] += abstained and expect_abstain
        stats["wrongly_abstained"] += abstained and not expect_abstain

        if draft and not abstained:
            allowed = {s.ref for s in sources}
            problems = citation_problems(draft, allowed)
            stats["drafts"] += 1
            stats["drafts_all_citations_valid"] += not any("unknown" in p for p in problems)
            stats["drafts_every_step_cited"] += not any("no citation" in p for p in problems)
            stats["steps"] += len(draft["steps"])
            if judged < judge_limit:
                content = {s.ref: s.content for s in sources}
                for step in draft["steps"]:
                    cited = " ".join(content.get(c, "") for c in step["citations"])
                    verdict = judge_step(step["text"], cited)
                    if verdict is not None:
                        judged += 1
                        supported += verdict
                    pace()
        print(f"  [{i}/{len(rows)}] {row['eval_id']} abstained={abstained} expected={expect_abstain}")

    return {
        "complaints": stats["n"],
        "abstention_correct": f"{stats['abstain_correct']}/{stats['n']}",
        "out_of_scope_abstained": f"{stats['abstained_when_expected']}/{stats['expected_abstain']}",
        "in_scope_wrongly_abstained": stats["wrongly_abstained"],
        "drafts": stats["drafts"],
        "drafts_with_all_citations_valid": f"{stats['drafts_all_citations_valid']}/{stats['drafts']}",
        "drafts_with_every_step_cited": f"{stats['drafts_every_step_cited']}/{stats['drafts']}",
        "avg_steps": round(stats["steps"] / stats["drafts"], 1) if stats["drafts"] else 0,
        "groundedness": f"{supported}/{judged} steps supported by their cited source" if judged else "not run",
        "latency_p50_s": round(statistics.median(latencies), 2) if latencies else None,
        "latency_p95_s": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 2) if latencies else None,
        "tokens_per_complaint": round(statistics.mean(tokens)) if tokens else None,
        "cost_per_complaint_usd": round(statistics.mean(costs), 6) if costs else None,
    }


#---------------- report ----------------

def write_report(results: dict) -> None:
    lines = [
        "# Evaluation results",
        "",
        f"Run {results['run_at']} · {results['rows']} held-out complaints · model `{results['model']}` · "
        f"embeddings `{results['embedding_model']}` · reranker `{results['reranker_model']}`",
        "",
        "The held-out complaints are never loaded into the database. The set is small and synthetic, so the raw "
        "counts matter more than the percentages and real tickets would score lower.",
        "",
        "## A. Retrieval (is a relevant ticket or KB article found?)",
        "",
        "| Mode | recall@1 | recall@3 | recall@5 | MRR | relevant KB article in top 5 | median latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, m in results["retrieval"]["modes"].items():
        n = m["n"]
        lines.append(
            f"| {name} | {m['recall@1']}/{n} | {m['recall@3']}/{n} | {m['recall@5']}/{n} | {m['mrr']} | "
            f"{m['kb_article_in_top5']}/{n} | {m['p50_ms']} ms |"
        )
    lines.append("")
    lines.append(f"Complaint kinds: {results['retrieval']['kinds']}")

    if "classification" in results:
        lines += ["", "## B. Classification", "", "| Field | Accuracy | Macro F1 |", "|---|---|---|"]
        for field, m in results["classification"].items():
            if "accuracy" in m:
                lines.append(f"| {field} | {m['accuracy']} | {m['macro_f1']} |")
        lines += ["", "| Severity metric | Model only | With escalate-only rules |", "|---|---|---|"]
        a = results["classification"]["severity metrics (model only)"]
        b = results["classification"]["severity metrics (with rules)"]
        for key in ("critical_recall", "under_triage", "over_triage", "off_by_one"):
            lines.append(f"| {key.replace('_', ' ')} | {a[key]} | {b[key]} |")
        lines += ["", "Per-class precision / recall / F1:", ""]
        for field, m in results["classification"].items():
            if "per_class" not in m:
                continue
            lines += [f"**{field}**", "", "| Class | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
            for label in m["labels"]:
                c = m["per_class"].get(label)
                if c:
                    scores = f"{c['precision']:.2f} | {c['recall']:.2f} | {c['f1-score']:.2f}"
                    lines.append(f"| {label} | {scores} | {int(c['support'])} |")
            name = field.replace(" ", "_").replace("(", "").replace(")", "")
            lines += ["", f"![{field}](confusion_{name}.png)", ""]

    if "drafting" in results:
        lines += ["## C. Drafting and D. Operations", "", "| Metric | Value |", "|---|---|"]
        for key, value in results["drafting"].items():
            lines.append(f"| {key.replace('_', ' ')} | {value} |")

    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    (OUT / "metrics.json").write_text(json.dumps(results, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true", help="skip everything that needs the llm")
    parser.add_argument("--limit", type=int, help="only use the first N held-out rows")
    parser.add_argument("--judge-limit", type=int, default=40, help="max steps judged by the llm")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_rows(args.limit)
    results = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "rows": len(rows),
        "model": settings.gemini_model_name if settings.llm_provider == "gemini" else settings.llm_provider,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
    }
    with SessionLocal() as db:
        print(f"categories in db: {len(active_categories(db))}")
        print("A. retrieval")
        results["retrieval"] = eval_retrieval(db, rows)
        if not args.retrieval_only:
            print("B. classification")
            results["classification"], preds = eval_classification(db, rows)
            print("C. drafting")
            results["drafting"] = eval_drafting(db, rows, preds, args.judge_limit)
    write_report(results)
    print(f"report written to {OUT / 'report.md'}")


if __name__ == "__main__":
    main()
