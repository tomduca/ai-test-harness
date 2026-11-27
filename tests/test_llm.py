import pytest
from langchain_core.runnables import RunnableLambda

import ai_test_harness.llm as llm_module
from ai_test_harness.llm import LLMChainError, LLMConfigError, get_llm


def unavailable(_):
    raise RuntimeError("503 UNAVAILABLE")


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


def test_falls_back_and_remembers_which_model_answered(monkeypatch):
    def fake_build(spec):
        if spec == "fake:down":
            return RunnableLambda(unavailable)
        return RunnableLambda(lambda _: f"answered by {spec}")

    monkeypatch.setattr(llm_module, "_build", fake_build)
    monkeypatch.setenv("LLM_MODELS", "fake:down,fake:up")

    chain = get_llm()
    assert chain.invoke("hi") == "answered by fake:up"
    assert chain.last_model == "fake:up"


def test_reports_every_failure_when_all_models_fail(monkeypatch):
    monkeypatch.setattr(llm_module, "_build", lambda spec: RunnableLambda(unavailable))
    monkeypatch.setenv("LLM_MODELS", "fake:a,fake:b")

    with pytest.raises(LLMChainError) as info:
        get_llm().invoke("hi")
    assert "fake:a" in str(info.value)
    assert "fake:b" in str(info.value)
