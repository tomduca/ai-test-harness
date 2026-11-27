"""Run the full planner -> executor -> evaluator graph over every scenario."""

import os
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
        except Exception as exc:  # noqa: BLE001 - one broken scenario must not stop the whole run
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


OUTCOME_ICONS = {
    "pass": "✅",
    "product_bug": "🐞",
    "test_defect": "🧪",
    "infra_error": "⚠️",
}


def write_github_summary(finals: list[dict]) -> None:
    """Append a results table to the GitHub Actions job summary (no-op outside CI)."""
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        "## ai-test-harness results",
        "",
        "| | Scenario | Outcome | Attempts |",
        "|---|---|---|---|",
    ]
    for final in finals:
        verdict = final["verdict"]
        lines.append(
            f"| {OUTCOME_ICONS[verdict.outcome]} | `{verdict.scenario_id}` "
            f"| {verdict.outcome} | {final['attempts']} |"
        )
    failures = [f for f in finals if f["verdict"].outcome != "pass"]
    if failures:
        lines += ["", "### Failures", ""]
        for final in failures:
            verdict = final["verdict"]
            lines += [
                f"<details><summary><code>{verdict.scenario_id}</code></summary>",
                "",
                "```text",
                verdict.reason[:1500],
                "```",
                "</details>",
                "",
            ]
    with open(path, "a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")
