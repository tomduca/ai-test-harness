import pytest
from langchain_core.runnables import RunnableLambda

import ai_test_harness.llm as llm_module
from ai_test_harness.llm import LLMConfigError, get_llm


@pytest.fixture(autouse=True)
def fresh_cache():
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()


def test_missing_config_raises_a_clear_error(monkeypatch):
    monkeypatch.setenv("LLM_MODELS", "")  # empty counts as set: .env won't override it
    with pytest.raises(LLMConfigError, match="LLM_MODELS"):
        get_llm()


def test_entries_must_include_a_provider(monkeypatch):
    monkeypatch.setenv("LLM_MODELS", "gemini-3.8-flash")
    with pytest.raises(LLMConfigError, match="provider:model"):
        get_llm()


def test_falls_back_to_the_next_model_when_one_is_unavailable(monkeypatch):
    def unavailable(_):
        raise RuntimeError("503 UNAVAILABLE")

    def fake_build(spec):
        if spec == "fake:down":
            return RunnableLambda(unavailable)
        return RunnableLambda(lambda _: f"answered by {spec}")

    monkeypatch.setattr(llm_module, "_build", fake_build)
    monkeypatch.setenv("LLM_MODELS", "fake:down,fake:up")

    assert get_llm().invoke("hi") == "answered by fake:up"