import pytest

from ai_test_harness.nodes.planner import PlannerError, make_planner, render_scenario
from ai_test_harness.schemas.plan import ExpectItems, Goto, Locator, TestPlan
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


class FakeLLM:
    """Stands in for get_llm(TestPlan): records the prompts and returns a fixed plan."""

    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.plan


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


def test_actions_pointing_to_unknown_steps_are_rejected():
    bad = TestPlan(scenario_id="x", actions=[Goto(path="/", step=5)])
    with pytest.raises(PlannerError, match="unknown steps"):
        make_planner(FakeLLM(bad))(initial_state(SCENARIO))


def test_uncovered_steps_are_reported_in_the_log():
    partial = TestPlan(scenario_id="x", actions=[Goto(path="/", step=0)])
    result = make_planner(FakeLLM(partial))(initial_state(SCENARIO))
    assert "planner: WARNING steps without actions [1]" in result["log"]
