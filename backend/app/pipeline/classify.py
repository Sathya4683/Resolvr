import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import call_json
from app.models import Category
from app.models.tickets import CRITICAL_REASONS, PRODUCTS, SENTIMENTS, SEVERITIES
from app.pipeline import prompts


def active_categories(db: Session) -> list[Category]:
    #read at request time, so a category added by an admin is used on the very next complaint
    #sql: SELECT * FROM categories WHERE is_active = true ORDER BY slug
    return list(db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.slug)))


def classification_schema(category_slugs: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": category_slugs + ["other"]},
            "product": {"type": "string", "enum": list(PRODUCTS)},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "critical_reason": {"type": "string", "enum": list(CRITICAL_REASONS) + ["none"]},
            "sentiment": {"type": "string", "enum": list(SENTIMENTS)},
            "language": {"type": "string", "description": "ISO 639-1 code of the complaint language"},
            "in_scope": {"type": "boolean"},
            "summary": {"type": "string", "description": "one short sentence describing the problem"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "category", "product", "severity", "critical_reason", "sentiment",
            "language", "in_scope", "summary", "confidence",
        ],
    }


def examples_block(slugs: list[str]) -> str:
    #skip an example if its category was switched off, the model must never see a label it can't use
    shown = [e for e in prompts.CLASSIFY_EXAMPLES if e["labels"]["category"] in slugs]
    if not shown:
        return ""
    parts = [f'Complaint: {e["complaint"]}\nLabels: {json.dumps(e["labels"])}' for e in shown]
    return "\nExamples of how complaints are labelled:\n" + "\n\n".join(parts) + "\n"


def build_prompt(complaint: str, categories: list[Category], guidance: list[str], product_hint: str | None) -> str:
    lines = []
    for c in categories:
        product = f" (product: {c.product})" if c.product else ""
        lines.append(f"- {c.slug}: {c.description}{product}")
    guidance_block = ""
    if guidance:
        notes = "\n".join(f"- {g}" for g in guidance)
        guidance_block = f"\nNotes from quality reviewers on similar past cases (follow them when relevant):\n{notes}\n"
    hint = f"\nThe agent thinks the product is: {product_hint}\n" if product_hint else ""
    return prompts.CLASSIFY_TEMPLATE.format(
        categories="\n".join(lines),
        severity_guide=prompts.SEVERITY_GUIDE,
        examples=examples_block([c.slug for c in categories]),
        guidance=guidance_block,
        hint=hint,
        complaint=complaint,
    )


def classify(
    db: Session, complaint: str, guidance: list[str] | None = None, product_hint: str | None = None
) -> tuple[dict, object]:
    """returns (labels, llm result). raises LLMError if the model can't be reached"""
    categories = active_categories(db)
    slugs = [c.slug for c in categories]
    prompt = build_prompt(complaint, categories, guidance or [], product_hint)
    result = call_json("classify", prompts.CLASSIFY_SYSTEM, prompt, classification_schema(slugs), fast=True)

    data = result.data or {}
    labels = {
        "category": data.get("category") if data.get("category") in slugs else None,
        "product": data.get("product") if data.get("product") in PRODUCTS else None,
        "severity": data.get("severity") if data.get("severity") in SEVERITIES else "medium",
        "critical_reason": data.get("critical_reason") if data.get("critical_reason") in CRITICAL_REASONS else None,
        "sentiment": data.get("sentiment") if data.get("sentiment") in SENTIMENTS else "neutral",
        "language": (data.get("language") or "en")[:5],
        "in_scope": bool(data.get("in_scope", True)),
        "summary": (data.get("summary") or "")[:300],
        "confidence": float(data.get("confidence") or 0),
    }
    return labels, result
