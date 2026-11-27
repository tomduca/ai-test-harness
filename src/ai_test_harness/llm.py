"""Provider-agnostic chat model chain with ordered, observable fallbacks."""

import os
from functools import cache

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable
from pydantic import BaseModel

# Structured-output method per provider (missing = LangChain's default for that provider).
# Groq + gpt-oss: tool calling is fragile (it may "call" its internal 'commentary' channel).
STRUCTURED_OUTPUT_METHOD = {"groq": "json_schema"}


class LLMConfigError(RuntimeError):
    """Raised when the LLM chain is not configured correctly."""


class LLMChainError(RuntimeError):
    """Raised when every model in the chain failed. The message lists each model's error."""

    def __init__(self, failures: list[tuple[str, str]]):
        self.kinds = [kind for kind, _ in failures]
        lines = "\n  ".join(f"[{kind}] {line}" for kind, line in failures)
        super().__init__(f"all models failed:\n  {lines}")

    @property
    def daily_quota_exhausted(self) -> bool:
        """True when waiting minutes will not help: every model is out of daily quota."""
        return bool(self.kinds) and all(kind == "daily_quota" for kind in self.kinds)


def _failure_kind(exc: Exception) -> str:
    """Classify a provider error from its FULL message (the report only keeps 200 chars)."""
    text = str(exc).lower()
    if "per day" in text or "perday" in text:
        return "daily_quota"
    if "429" in text or "rate limit" in text:
        return "rate_limit"
    if "503" in text or "unavailable" in text or "timeout" in text:
        return "unavailable"
    return "error"


def _model_specs() -> list[str]:
    raw = os.getenv("LLM_MODELS", "")
    return [spec.strip() for spec in raw.split(",") if spec.strip()]


def _build(spec: str) -> BaseChatModel:
    kwargs = {
        # Fail fast so the next model in the chain gets its chance
        "timeout": float(os.getenv("LLM_TIMEOUT", "60")),
        "max_retries": int(os.getenv("LLM_MAX_RETRIES", "1")),
    }
    if temperature := os.getenv("LLM_TEMPERATURE"):
        kwargs["temperature"] = float(temperature)
    if rpm := os.getenv("LLM_REQUESTS_PER_MINUTE"):
        # Client-side pacing: stay under the provider's free-tier limits instead of hitting 429s.
        kwargs["rate_limiter"] = InMemoryRateLimiter(
            requests_per_second=float(rpm) / 60,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
    return init_chat_model(spec, **kwargs)


class ModelChain:
    """Try each model in order. Remember which one answered; report every failure."""

    def __init__(self, entries: list[tuple[str, Runnable]]):
        self.entries = entries
        self.last_model: str | None = None

    def invoke(self, messages):
        failures = []
        for spec, runnable in self.entries:
            try:
                result = runnable.invoke(messages)
            except Exception as exc:  # noqa: BLE001 - any failure moves on to the next model
                line = f"{spec}: {type(exc).__name__}: {str(exc)[:200]}"
                failures.append((_failure_kind(exc), line))
                continue
            self.last_model = spec
            return result
        raise LLMChainError(failures)


@cache
def get_llm(schema: type[BaseModel] | None = None) -> ModelChain:
    """Return the configured model chain, optionally bound to a structured-output schema."""
    load_dotenv()
    specs = _model_specs()
    if not specs:
        raise LLMConfigError(
            "Set LLM_MODELS in .env, e.g. "
            "groq:openai/gpt-oss-120b,google_genai:gemini-3.5-flash-lite"
        )
    if invalid := [spec for spec in specs if ":" not in spec]:
        raise LLMConfigError(f"Each entry must be 'provider:model', got: {invalid}")

    entries = []
    for spec in specs:
        model = _build(spec)
        if schema is not None:
            method = STRUCTURED_OUTPUT_METHOD.get(spec.split(":", 1)[0])
            model = model.with_structured_output(
                schema, **({"method": method} if method else {})
            )
        entries.append((spec, model))
    return ModelChain(entries)
