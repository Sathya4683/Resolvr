import itertools
import json
import logging
import time
from typing import Iterator

from app.config import settings
from app.llm.base import LLMError, LLMResult, StreamChunk

log = logging.getLogger(__name__)

#errors that mean "busy / try again", worth one shot on the fallback model
BUSY_CODES = {429, 500, 503, 504}


class GeminiProvider:
    name = "gemini"

    def __init__(self):
        from google import genai
        from google.genai import errors, types

        if not settings.google_api_key:
            raise LLMError("GOOGLE_API_KEY is not set")
        self.types = types
        self.errors = errors
        self.client = genai.Client(
            api_key=settings.google_api_key,
            http_options=types.HttpOptions(
                timeout=settings.llm_timeout_seconds * 1000,  #milliseconds
                #the sdk retries 429/5xx with exponential backoff for us
                retry_options=types.HttpRetryOptions(
                    attempts=settings.llm_max_retries + 1, initial_delay=1.0, max_delay=8.0
                ),
            ),
        )
        self.model = settings.gemini_model_name
        self.fast_model = settings.gemini_fast_model_name or self.model
        self.fallback_model = settings.gemini_fallback_model_name

    def _thinking(self, model: str):
        """
        these are short structured tasks, so we keep the model's "thinking" as low as it goes.
        gemini 2.5 used a token budget (0 = off), gemini 3 uses a level and can't be fully turned off
        """
        if model.startswith("gemini-2.5"):
            return self.types.ThinkingConfig(thinking_budget=0) if "flash" in model else None
        return self.types.ThinkingConfig(thinking_level="minimal" if "lite" in model else "low")

    def _config(self, model: str, system: str, schema: dict | None = None):
        kwargs = {"system_instruction": system, "temperature": 0.2, "max_output_tokens": 4096}
        if schema:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_json_schema"] = schema
        thinking = self._thinking(model)
        if thinking:
            kwargs["thinking_config"] = thinking
        return self.types.GenerateContentConfig(**kwargs)

    def _contents(self, messages: list[dict]):
        return [
            self.types.Content(
                role="model" if m["role"] == "assistant" else "user", parts=[self.types.Part(text=m["content"])]
            )
            for m in messages
        ]

    @staticmethod
    def _usage(response) -> tuple[int, int]:
        usage = response.usage_metadata
        if usage is None:
            return 0, 0
        output = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        return usage.prompt_token_count or 0, output

    def _with_fallback(self, model: str, call):
        """
        runs call(model). if google says the model is overloaded (it happens a lot on the free tier
        for the newest models) we try once more on the fallback model instead of failing the request
        """
        try:
            return call(model), model
        except self.errors.APIError as exc:
            if exc.code not in BUSY_CODES or not self.fallback_model or self.fallback_model == model:
                raise
            log.warning("model busy, using fallback", extra={"model": model, "fallback": self.fallback_model,
                                                             "code": exc.code})
            return call(self.fallback_model), self.fallback_model

    def generate_json(self, system: str, prompt: str, schema: dict, fast: bool = False) -> LLMResult:
        start = time.perf_counter()
        try:
            response, used = self._with_fallback(
                self.fast_model if fast else self.model,
                lambda m: self.client.models.generate_content(
                    model=m, contents=prompt, config=self._config(m, system, schema)
                ),
            )
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned invalid json: {exc}") from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        prompt_tokens, completion_tokens = self._usage(response)
        return LLMResult(
            text=response.text,
            data=data,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=used,
            latency_s=time.perf_counter() - start,
        )

    def generate_text(self, system: str, messages: list[dict]) -> LLMResult:
        start = time.perf_counter()
        try:
            response, used = self._with_fallback(
                self.model,
                lambda m: self.client.models.generate_content(
                    model=m, contents=self._contents(messages), config=self._config(m, system)
                ),
            )
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        prompt_tokens, completion_tokens = self._usage(response)
        return LLMResult(
            text=response.text or "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=used,
            latency_s=time.perf_counter() - start,
        )

    def _open_stream(self, model: str, system: str, messages: list[dict]):
        stream = self.client.models.generate_content_stream(
            model=model, contents=self._contents(messages), config=self._config(model, system)
        )
        #a busy model fails on the first chunk, pull it here so the fallback can kick in
        first = next(stream, None)
        return itertools.chain([first] if first else [], stream)

    def stream_text(self, system: str, messages: list[dict]) -> Iterator[StreamChunk]:
        start = time.perf_counter()
        prompt_tokens = completion_tokens = 0
        parts = []
        try:
            stream, used = self._with_fallback(self.model, lambda m: self._open_stream(m, system, messages))
            for chunk in stream:
                if chunk.text:
                    parts.append(chunk.text)
                    yield StreamChunk(text=chunk.text)
                if chunk.usage_metadata:
                    prompt_tokens, completion_tokens = self._usage(chunk)
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        yield StreamChunk(
            done=True,
            usage=LLMResult(
                text="".join(parts),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=used,
                latency_s=time.perf_counter() - start,
            ),
        )
