"""
Masks personal data before a complaint is sent to an external llm.
Order matters: longer number patterns (cards, aadhaar) run before phone / account numbers.
"""

import re

PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    #upi ids look like emails without a dot in the domain, e.g. name@okaxis
    ("UPI", re.compile(r"\b[\w.-]{2,}@[a-z]{3,}\b", re.I)),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b")),
    #indian mobile numbers, with or without +91 / 0 in front
    ("PHONE", re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
    ("ACCOUNT", re.compile(r"(?<!\d)\d{9,18}(?!\d)")),
]


def redact(text: str) -> tuple[str, list[str]]:
    """returns the masked text and the kinds of data that were found"""
    found = []
    for label, pattern in PATTERNS:
        text, count = pattern.subn(f"[{label}]", text)
        if count:
            found.append(label.lower())
    return text, found
