from ai_test_harness.llm import LLMChainError
from ai_test_harness.plan_cache import PlanCache
from ai_test_harness.runner import run_scenarios
from ai_test_harness.schemas.plan import Goto, TestPlan
from ai_test_harness.schemas.results import Verdict
from ai_test_harness.schemas.scenario import Scenario, Step


def scenario(n: int) -> Scenario:
    return Scenario(
        id=f"demo::s{n}",
        feature="Demo",
        name=f"s{n}",
        uri="demo.feature",
        steps=[Step(text="a")],
    )


class FakeGraph:
    """Raises (like a provider 429) for the first `failures` calls of each scenario in `flaky`."""

    def __init__(self, flaky=(), failures=1, outcome="pass"):
        self.flaky = set(flaky)
        self.failures = failures
        self.outcome = outcome
        self.calls = []

    def invoke(self, state):
        scenario_id = state["scenario"].id
        self.calls.append(scenario_id)
        if scenario_id in self.flaky and self.calls.count(scenario_id) <= self.failures:
            raise RuntimeError("429 tokens per minute")
        verdict = Verdict(scenario_id=scenario_id, outcome=self.outcome, reason="fake")
        return {**state, "attempts": 1, "verdict": verdict}


class ExhaustedGraph:
    """Every model in the chain is out of daily quota."""

    def __init__(self):
        self.calls = 0

    def invoke(self, state):
        self.calls += 1
        raise LLMChainError([("daily_quota", "groq:x: 429 tokens per day")])


class PlanningGraph:
    """Returns a plan and a fixed outcome, like a full graph run."""

    def __init__(self, outcome):
        self.outcome = outcome

    def invoke(self, state):
        scenario_id = state["scenario"].id
        plan = TestPlan(scenario_id=scenario_id, actions=[Goto(path="/", step=0)])
        verdict = Verdict(scenario_id=scenario_id, outcome=self.outcome, reason="fake")
        return {**state, "attempts": 1, "plan": plan, "verdict": verdict}


def test_infra_errors_are_retried_once():
    graph = FakeGraph(flaky={"demo::s1"})
    finals = run_scenarios(graph, [scenario(0), scenario(1)], infra_retry_delay_s=0)
    assert [f["verdict"].outcome for f in finals] == ["pass", "pass"]
    assert graph.calls == ["demo::s0", "demo::s1", "demo::s1"]
    assert finals[1]["infra_retried"] is True
    assert "infra_retried" not in finals[0]


def test_persistent_infra_errors_are_not_retried_forever():
    graph = FakeGraph(flaky={"demo::s0"}, failures=99)
    finals = run_scenarios(graph, [scenario(0)], infra_retry_delay_s=0)
    assert finals[0]["verdict"].outcome == "infra_error"
    assert graph.calls == ["demo::s0", "demo::s0"]  # exactly one retry


def test_product_bugs_are_never_retried():
    graph = FakeGraph(outcome="product_bug")
    finals = run_scenarios(graph, [scenario(0)], infra_retry_delay_s=0)
    assert finals[0]["verdict"].outcome == "product_bug"
    assert graph.calls == ["demo::s0"]


def test_exhausted_daily_quotas_are_not_retried():
    graph = ExhaustedGraph()
    finals = run_scenarios(graph, [scenario(0)], infra_retry_delay_s=0)
    assert graph.calls == 1
    assert finals[0]["verdict"].outcome == "infra_error"
    assert "daily LLM quota exhausted" in finals[0]["verdict"].reason


def test_passing_plans_are_cached(tmp_path):
    cache = PlanCache(tmp_path, fingerprint="v1")
    run_scenarios(
        PlanningGraph("pass"), [scenario(0)], infra_retry_delay_s=0, cache=cache
    )
    assert cache.get(scenario(0)) is not None


def test_product_bug_plans_are_not_cached(tmp_path):
    # A product_bug plan could be a misclassified test defect: caching it would repeat it daily.
    cache = PlanCache(tmp_path, fingerprint="v1")
    run_scenarios(
        PlanningGraph("product_bug"), [scenario(0)], infra_retry_delay_s=0, cache=cache
    )
    assert cache.get(scenario(0)) is None
