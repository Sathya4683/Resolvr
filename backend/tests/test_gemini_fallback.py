"""the gemini provider retries on the fallback model when the main one is overloaded (no network)"""

from types import SimpleNamespace

import pytest
from google.genai import errors

from app.config import settings
from app.llm.base import LLMError
from app.llm.gemini import GeminiProvider


class FakeModels:
    def __init__(self, busy: set[str]):
        self.busy = busy
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if model in self.busy:
            raise errors.APIError(503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}})
        usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=0)
        return SimpleNamespace(text='{"ok": true}', usage_metadata=usage)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_model_name", "main-model")
    monkeypatch.setattr(settings, "gemini_fast_model_name", "main-model")
    monkeypatch.setattr(settings, "gemini_fallback_model_name", "backup-model, last-resort")
    return GeminiProvider()


def test_busy_model_falls_back(provider):
    provider.client = SimpleNamespace(models=FakeModels(busy={"main-model"}))
    result = provider.generate_json("system", "prompt", {"type": "object"})
    assert result.data == {"ok": True}
    assert result.model == "backup-model"
    assert provider.client.models.calls == ["main-model", "backup-model"]


def test_walks_down_the_fallback_list(provider):
    provider.client = SimpleNamespace(models=FakeModels(busy={"main-model", "backup-model"}))
    result = provider.generate_json("system", "prompt", {"type": "object"})
    assert result.model == "last-resort"
    assert provider.client.models.calls == ["main-model", "backup-model", "last-resort"]


def test_all_busy_raises_llm_error(provider):
    provider.client = SimpleNamespace(models=FakeModels(busy={"main-model", "backup-model", "last-resort"}))
    with pytest.raises(LLMError):
        provider.generate_json("system", "prompt", {"type": "object"})


def test_healthy_model_is_used_directly(provider):
    provider.client = SimpleNamespace(models=FakeModels(busy=set()))
    assert provider.generate_json("system", "prompt", {"type": "object"}).model == "main-model"
