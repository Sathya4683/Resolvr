"""
Entry point for llm calls. get_llm() picks the provider from LLM_PROVIDER and the helpers
below record latency / tokens / cost metrics for every call in one place.
"""

import logging
from functools import lru_cache

from app import metrics
from app.config import settings
from app.llm.base import LLMError, LLMProvider, LLMResult, StreamChunk

log = logging.getLogger(__name__)

__all__ = ["LLMError", "LLMResult", "StreamChunk", "get_llm", "call_json", "estimate_cost", "record_usage"]


@lru_cache
def get_llm() -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        from app.llm.gemini import GeminiProvider

        return GeminiProvider()
    if provider == "fake":
        from app.llm.fake import FakeProvider

        return FakeProvider()
    raise LLMError(f"unknown LLM_PROVIDER '{settings.llm_provider}'")


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens * settings.llm_input_cost_per_1m + completion_tokens * settings.llm_output_cost_per_1m
    ) / 1_000_000


def record_usage(purpose: str, result: LLMResult) -> None:
    metrics.LLM_LATENCY.labels(purpose).observe(result.latency_s)
    metrics.LLM_TOKENS.labels(purpose, "input").inc(result.prompt_tokens)
    metrics.LLM_TOKENS.labels(purpose, "output").inc(result.completion_tokens)
    metrics.LLM_COST.labels(purpose).inc(estimate_cost(result.prompt_tokens, result.completion_tokens))


def call_json(purpose: str, system: str, prompt: str, schema: dict, fast: bool = False) -> LLMResult:
    """structured call with metrics, raises LLMError so callers can fall back"""
    llm = get_llm()
    try:
        result = llm.generate_json(system, prompt, schema, fast=fast)
    except LLMError as exc:
        metrics.LLM_CALLS.labels(llm.name, purpose, "error").inc()
        log.warning("llm call failed", extra={"purpose": purpose, "error": str(exc)[:300]})
        raise
    metrics.LLM_CALLS.labels(llm.name, purpose, "ok").inc()
    record_usage(purpose, result)
    return result
