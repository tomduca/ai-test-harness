import pytest

from ai_test_harness.nodes.planner import (
    MAX_SELF_CORRECTIONS,
    PlannerError,
    find_plan_problems,
    make_planner,
    render_scenario,
)
from ai_test_harness.schemas.plan import Click, ExpectItems, Goto, Locator, TestPlan
from ai_test_harness.schemas.results import Verdict
from ai_test_harness.schemas.scenario import Scenario, Step
from ai_test_harness.state import initial_state

SCENARIO = Scenario(
    id="navigation::menu",
    feature="Main navigation",
    name="Menu",
    uri="navigation.feature",
    steps=[
        Step(type="Context", text="I am on the home page"),
        Step(
            type="Outcome",
            text="the main menu contains exactly these items, in this order:",
            data_table=[["Proyectos"], ["Taller"]],
        ),
    ],
)

GOOD_PLAN = TestPlan(
    scenario_id="an-id-the-llm-made-up",
    actions=[
        Goto(path="/", step=0),
        ExpectItems(
            locator=Locator(role="link"), items=["Proyectos", "Taller"], step=1
        ),
    ],
)
PARTIAL_PLAN = TestPlan(scenario_id="x", actions=[Goto(path="/", step=0)])
UNKNOWN_STEP_PLAN = TestPlan(scenario_id="x", actions=[Goto(path="/", step=5)])
CLICK_ONLY_PLAN = TestPlan(
    scenario_id="x",
    actions=[
        Goto(path="/", step=0),
        Click(locator=Locator(role="link", name="Taller"), step=1),
    ],
)


class FakeLLM:
    """Stands in for get_llm(TestPlan): returns the given plans in order (the last one repeats)."""

    def __init__(self, *plans):
        self.plans = plans
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.plans[min(len(self.calls), len(self.plans)) - 1]


def test_scenario_is_rendered_with_step_indexes_and_tables():
    text = render_scenario(SCENARIO)
    assert "[0] (Context) I am on the home page" in text
    assert "| Proyectos |" in text


def test_the_harness_owns_the_scenario_id():
    result = make_planner(FakeLLM(GOOD_PLAN))(initial_state(SCENARIO))
    assert result["plan"].scenario_id == "navigation::menu"
    assert result["attempts"] == 1


def test_first_attempt_has_no_retry_feedback():
    llm = FakeLLM(GOOD_PLAN)
    make_planner(llm)(initial_state(SCENARIO))
    assert "Previous plan" not in llm.calls[0][-1].content


def test_retry_prompt_includes_the_evaluator_feedback():
    llm = FakeLLM(GOOD_PLAN)
    state = {
        **initial_state(SCENARIO),
        "plan": GOOD_PLAN,
        "attempts": 1,
        "verdict": Verdict(
            scenario_id="navigation::menu",
            outcome="test_defect",
            reason="locator role=link name='Mapa' matched no elements",
        ),
    }
    result = make_planner(llm)(state)
    prompt = llm.calls[0][-1].content
    assert "matched no elements" in prompt
    assert "Previous plan" in prompt
    assert result["attempts"] == 2


def test_click_only_outcome_is_a_problem():
    problems = find_plan_problems(CLICK_ONLY_PLAN, SCENARIO)
    assert problems == ["outcome steps must be verified with expect_* actions: [1]"]


def test_uncovered_steps_trigger_a_self_correction():
    llm = FakeLLM(PARTIAL_PLAN, GOOD_PLAN)
    result = make_planner(llm)(initial_state(SCENARIO))
    assert len(llm.calls) == 2
    assert "steps without any action: [1]" in llm.calls[1][-1].content
    assert result["plan"].actions == GOOD_PLAN.actions
    assert "1 self-corrections" in result["log"][-1]


def test_unknown_steps_trigger_a_self_correction():
    llm = FakeLLM(UNKNOWN_STEP_PLAN, GOOD_PLAN)
    make_planner(llm)(initial_state(SCENARIO))
    assert "steps that do not exist: [5]" in llm.calls[1][-1].content


def test_self_corrections_are_bounded():
    llm = FakeLLM(PARTIAL_PLAN)  # never gets better
    with pytest.raises(PlannerError, match="no valid plan"):
        make_planner(llm)(initial_state(SCENARIO))
    assert len(llm.calls) == MAX_SELF_CORRECTIONS + 1
