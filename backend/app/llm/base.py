from dataclasses import dataclass, field
from typing import Iterator, Protocol


class LLMError(Exception):
    """anything that went wrong talking to the model (timeout, quota, bad output...)"""


@dataclass
class LLMResult:
    text: str
    data: dict | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    latency_s: float = 0.0


@dataclass
class StreamChunk:
    """streaming yields text deltas, the last chunk carries the token usage"""

    text: str = ""
    done: bool = False
    usage: LLMResult | None = field(default=None)


class LLMProvider(Protocol):
    """
    The only thing the rest of the app knows about the llm. Adding claude/openai later means
    writing one more class with these three methods.
    messages are plain dicts: {"role": "user" | "assistant", "content": "..."}
    """

    name: str

    def generate_json(self, system: str, prompt: str, schema: dict, fast: bool = False) -> LLMResult: ...

    def generate_text(self, system: str, messages: list[dict]) -> LLMResult: ...

    def stream_text(self, system: str, messages: list[dict]) -> Iterator[StreamChunk]: ...
