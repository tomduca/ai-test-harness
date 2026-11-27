"""Run the full planner -> executor -> evaluator graph over every scenario."""

from pathlib import Path

from ai_test_harness.graph import build_graph
from ai_test_harness.nodes.evaluator import evaluator
from ai_test_harness.nodes.executor import make_executor
from ai_test_harness.nodes.planner import make_planner
from ai_test_harness.schemas.results import Verdict
from ai_test_harness.specs_loader import load_specs
from ai_test_harness.state import initial_state


def run_specs(specs_dir: Path = Path("specs"), only: str | None = None) -> list[dict]:
    graph = build_graph(make_planner(), make_executor(), evaluator)
    finals = []
    for scenario in load_specs(specs_dir):
        if only and only not in scenario.id:
            continue
        try:
            finals.append(graph.invoke(initial_state(scenario)))
        except Exception as exc:  # one broken scenario must not stop the whole run
            finals.append(
                {
                    "scenario": scenario,
                    "attempts": 0,
                    "log": [],
                    "verdict": Verdict(
                        scenario_id=scenario.id,
                        outcome="infra_error",
                        reason=f"harness error: {type(exc).__name__}: {exc}",
                    ),
                }
            )
    return finals
