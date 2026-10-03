"""
Deterministic safety net on top of the classifier. If the complaint clearly mentions a lawyer,
TRAI, a SIM swap etc. the case must go to an admin even if the llm missed it.
Rules can only raise the severity, never lower it.
"""

import re

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

#(rule name, pattern, severity, critical_reason)
RULES = [
    (
        "legal_threat",
        r"legal notice|lawyer|advocate|consumer (court|forum)|court case|legal action|\bsue\b",
        "critical",
        "legal",
    ),
    (
        "regulator",
        r"\btrai\b|ombudsman|appellate authority|grievance portal|cpgrams",
        "critical",
        "regulatory",
    ),
    (
        "fraud",
        r"sim swap|duplicate sim|ported (out )?without|without my (knowledge|consent)"
        r"|otp.{0,40}(never|didn'?t|did not|not).{0,15}(request|make|made|do|did)"
        r"|(asking|asked) for (my )?(otp|upc)|money .{0,25}(gone|missing|lost)|\bhacked\b|\bfraud"
        r"|unknown person|(activated|changed|replaced).{0,60}(i didn'?t|i did not|never requested)",
        "critical",
        "fraud",
    ),
    (
        "privacy",
        r"delete (all )?my (personal )?data|(personal )?data deleted|data (has been |was )?(leak|leaked|sold|breach)"
        r"|(leaked|sold) my (data|details)|call records of|personal data you (store|have|keep)",
        "critical",
        "privacy",
    ),
    (
        "compensation",
        r"compensation|full (month'?s? )?refund|refund the full|waive (my )?(entire|whole|full)"
        r"|money back|refund .{0,30}(to my bank|in cash)|refund of my|deposit .{0,20}cash",
        "critical",
        "compensation",
    ),
    (
        "area_outage",
        r"(whole|entire|complete) (area|building|locality|society|street|colony)"
        r"|all (my )?neighbou?rs|everyone (in|on|around)|tower (seems |is )?down",
        "high",
        None,
    ),
]

COMPILED = [(name, re.compile(pattern, re.I), sev, reason) for name, pattern, sev, reason in RULES]


def apply_rules(text: str, severity: str | None, critical_reason: str | None):
    """returns (severity, critical_reason, names of the rules that fired)"""
    fired = []
    current = severity if severity in SEVERITY_ORDER else "medium"
    reason = critical_reason
    for name, pattern, rule_severity, rule_reason in COMPILED:
        if not pattern.search(text):
            continue
        fired.append(name)
        if SEVERITY_ORDER[rule_severity] > SEVERITY_ORDER[current]:
            current = rule_severity
            reason = rule_reason or reason
        elif rule_severity == "critical" and current == "critical" and not reason:
            reason = rule_reason
    if current != "critical":
        reason = None
    return current, reason, fired
