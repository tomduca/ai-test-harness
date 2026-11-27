from ai_test_harness.graph import MAX_ATTEMPTS, build_graph
from ai_test_harness.schemas.plan import Goto, TestPlan
from ai_test_harness.schemas.results import ExecutionResult, Verdict
from ai_test_harness.schemas.scenario import Scenario, Step
from ai_test_harness.state import initial_state

SCENARIO = Scenario(
    id="demo::s", feature="Demo", name="s", uri="demo.feature", steps=[Step(text="a")]
)


def fake_planner(state):
    attempt = state["attempts"] + 1
    return {
        "plan": TestPlan(
            scenario_id=state["scenario"].id, actions=[Goto(path="/", step=0)]
        ),
        "attempts": attempt,
        "log": [f"planner:{attempt}"],
    }


def fake_executor(state):
    return {
        "execution": ExecutionResult(scenario_id=state["scenario"].id, passed=True),
        "log": ["executor"],
    }


def scripted_evaluator(*outcomes):
    """Returns a fake evaluator that yields the given outcomes in order."""
    queue = iter(outcomes)

    def evaluator(state):
        outcome = next(queue)
        return {
            "verdict": Verdict(
                scenario_id=state["scenario"].id, outcome=outcome, reason="scripted"
            ),
            "log": [f"evaluator:{outcome}"],
        }

    return evaluator


def run(*outcomes):
    graph = build_graph(fake_planner, fake_executor, scripted_evaluator(*outcomes))
    return graph.invoke(initial_state(SCENARIO))


def test_pass_on_first_attempt_ends_the_run():
    result = run("pass")
    assert result["attempts"] == 1
    assert result["log"] == ["planner:1", "executor", "evaluator:pass"]


def test_test_defect_triggers_a_new_plan():
    result = run("test_defect", "pass")
    assert result["attempts"] == 2
    assert result["verdict"].outcome == "pass"
    assert result["log"] == [
        "planner:1",
        "executor",
        "evaluator:test_defect",
        "planner:2",
        "executor",
        "evaluator:pass",
    ]


def test_retries_are_bounded():
    result = run(*["test_defect"] * 10)
    assert result["attempts"] == MAX_ATTEMPTS
    assert result["verdict"].outcome == "test_defect"


def test_product_bug_is_not_retried():
    result = run("product_bug")
    assert result["attempts"] == 1
    assert result["verdict"].outcome == "product_bug"


def test_infra_error_is_not_retried():
    result = run("infra_error")
    assert result["attempts"] == 1
    assert result["verdict"].outcome == "infra_error"
