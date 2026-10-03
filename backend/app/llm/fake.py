"""
Deterministic stand-in for the real model, used by the tests (LLM_PROVIDER=fake).
Tests can queue exact responses with FakeProvider.queue("draft", {...}).
"""

import re
from collections import defaultdict
from typing import Iterator

from app.llm.base import LLMError, LLMResult, StreamChunk

_queued: dict[str, list] = defaultdict(list)


class FakeProvider:
    name = "fake"

    @staticmethod
    def queue(purpose: str, response: dict | Exception) -> None:
        _queued[purpose].append(response)

    @staticmethod
    def reset() -> None:
        _queued.clear()

    def _next(self, purpose: str):
        if _queued[purpose]:
            item = _queued[purpose].pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return None

    def generate_json(self, system: str, prompt: str, schema: dict, fast: bool = False) -> LLMResult:
        purpose = "classify" if "category" in schema.get("properties", {}) else "draft"
        data = self._next(purpose)
        if data is None:
            data = self._default_classify(prompt) if purpose == "classify" else self._default_draft(prompt)
        return LLMResult(text=str(data), data=data, prompt_tokens=100, completion_tokens=50, model="fake")

    def generate_text(self, system: str, messages: list[dict]) -> LLMResult:
        queued = self._next("chat")
        text = queued["text"] if queued else "Try restarting the router [KB-001]."
        return LLMResult(text=text, prompt_tokens=80, completion_tokens=20, model="fake")

    def stream_text(self, system: str, messages: list[dict]) -> Iterator[StreamChunk]:
        result = self.generate_text(system, messages)
        for word in result.text.split(" "):
            yield StreamChunk(text=word + " ")
        yield StreamChunk(done=True, usage=result)

    @staticmethod
    def _default_classify(prompt: str) -> dict:
        slugs = re.findall(r"^- ([a-z0-9_]+):", prompt, re.M)
        complaint = prompt.split("<complaint>")[-1].lower()
        category = next((s for s in slugs if s.split("_")[0] in complaint), slugs[0] if slugs else "other")
        return {
            "category": category,
            "product": "broadband",
            "severity": "medium",
            "critical_reason": "none",
            "sentiment": "neutral",
            "language": "en",
            "in_scope": True,
            "summary": "test summary",
            "confidence": 0.8,
        }

    @staticmethod
    def _default_draft(prompt: str) -> dict:
        refs = re.findall(r"^\[((?:TCK|KB)-\d+)\]", prompt, re.M)
        if not refs:
            raise LLMError("no sources in prompt")
        return {
            "steps": [
                {"text": "Restart the router and check the cables.", "citations": [refs[0]]},
                {"text": "Raise a line fault if it keeps dropping.", "citations": refs[:2]},
            ],
            "customer_reply": "We are looking into it.",
            "abstain": False,
            "abstain_reason": "",
        }
