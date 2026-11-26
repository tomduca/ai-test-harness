"""Provider-agnostic chat model factory with an ordered fallback chain."""

import os
from functools import cache

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel


class LLMConfigError(RuntimeError):
    """Raised when the LLM chain is not configured correctly."""


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
    return init_chat_model(spec, **kwargs)


@cache
def get_llm(schema: type[BaseModel] | None = None) -> Runnable:
    """Return the configured model chain, optionally bound to a structured-output schema.

    Models are tried in the order given by LLM_MODELS; on error, the next one is used.
    """
    load_dotenv()
    specs = _model_specs()
    if not specs:
        raise LLMConfigError(
            "Set LLM_MODELS in .env, e.g. "
            "google_genai:gemini-3.8-flash,google_genai:gemini-3.5-flash-lite"
        )
    if invalid := [spec for spec in specs if ":" not in spec]:
        raise LLMConfigError(f"Each entry must be 'provider:model', got: {invalid}")

    chain = [_build(spec) for spec in specs]
    if schema is not None:
        # Structured output must be bound per model, before adding fallbacks
        chain = [model.with_structured_output(schema) for model in chain]

    primary, *fallbacks = chain
    return primary.with_fallbacks(fallbacks) if fallbacks else primary
