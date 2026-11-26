"""Planner -> executor -> evaluator graph with a bounded retry loop."""

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from ai_test_harness.state import ScenarioState

MAX_ATTEMPTS = 2

Node = Callable[[ScenarioState], dict]


def route_after_evaluation(state: ScenarioState) -> str:
    """Retry planning only when the failure is the test's fault, and only up to MAX_ATTEMPTS."""
    if state["verdict"].outcome == "test_defect" and state["attempts"] < MAX_ATTEMPTS:
        return "planner"
    return END


def build_graph(planner: Node, executor: Node, evaluator: Node):
    builder = StateGraph(ScenarioState)
    builder.add_node("planner", planner)
    builder.add_node("executor", executor)
    builder.add_node("evaluator", evaluator)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "executor")
    builder.add_edge("executor", "evaluator")
    builder.add_conditional_edges("evaluator", route_after_evaluation, ["planner", END])

    return builder.compile()
