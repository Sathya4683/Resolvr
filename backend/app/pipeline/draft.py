from app.llm import LLMResult, call_json
from app.pipeline import prompts
from app.pipeline.retrieve import Source


def draft_schema(allowed_refs: list[str]) -> dict:
    #citations are limited to the ids we actually retrieved, validate.py double checks anyway
    return {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "citations": {"type": "array", "items": {"type": "string", "enum": allowed_refs}},
                    },
                    "required": ["text", "citations"],
                },
            },
            "customer_reply": {"type": "string"},
            "abstain": {"type": "boolean"},
            "abstain_reason": {"type": "string"},
        },
        "required": ["steps", "customer_reply", "abstain", "abstain_reason"],
    }


def format_sources(sources: list[Source]) -> str:
    return "\n\n".join(f"[{s.ref}] {s.content}" for s in sources)


def draft_resolution(
    complaint: str,
    labels: dict,
    sources: list[Source],
    problems: list[str] | None = None,
    guidance: list[str] | None = None,
) -> tuple[dict, LLMResult]:
    allowed = [s.ref for s in sources]
    prompt = prompts.DRAFT_TEMPLATE.format(
        category=labels.get("category") or "unknown",
        product=labels.get("product") or "unknown",
        severity=labels.get("severity") or "unknown",
        sources=format_sources(sources),
        complaint=complaint,
    )
    if guidance:
        prompt += "\n\nNotes from quality reviewers on similar past cases:\n" + "\n".join(f"- {g}" for g in guidance)
    if problems:
        prompt += prompts.DRAFT_RETRY_NOTE.format(problems="; ".join(problems), allowed=", ".join(allowed))
    result = call_json("draft", prompts.DRAFT_SYSTEM, prompt, draft_schema(allowed))
    data = result.data or {}
    draft = {
        "steps": [
            {"text": str(s.get("text", "")).strip(), "citations": [str(c) for c in s.get("citations", [])]}
            for s in data.get("steps", [])
            if str(s.get("text", "")).strip()
        ],
        "customer_reply": str(data.get("customer_reply", "")).strip(),
        "abstain": bool(data.get("abstain", False)),
        "abstain_reason": str(data.get("abstain_reason", "")).strip(),
    }
    return draft, result
