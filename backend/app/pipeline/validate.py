"""Guardrail: a draft is only trusted if every step cites something we actually retrieved."""


def citation_problems(draft: dict, allowed: set[str]) -> list[str]:
    problems = []
    for i, step in enumerate(draft.get("steps", []), start=1):
        cites = step.get("citations", [])
        if not cites:
            problems.append(f"step {i} has no citation")
        bad = [c for c in cites if c not in allowed]
        if bad:
            problems.append(f"step {i} cites unknown source(s) {', '.join(bad)}")
    if not draft.get("abstain") and not draft.get("steps"):
        problems.append("no steps were written")
    return problems


def strip_invalid(draft: dict, allowed: set[str]) -> dict:
    """last resort: drop citations we can't verify and any step left without one"""
    steps = []
    for step in draft.get("steps", []):
        cites = [c for c in step.get("citations", []) if c in allowed]
        if cites:
            steps.append({"text": step["text"], "citations": cites})
    return {**draft, "steps": steps}
