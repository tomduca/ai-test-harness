"""Run the full planner -> executor -> evaluator graph over every scenario."""

import os
import time
from pathlib import Path

from ai_test_harness.graph import build_graph
from ai_test_harness.nodes.evaluator import evaluator
from ai_test_harness.nodes.executor import make_executor
from ai_test_harness.nodes.planner import make_planner
from ai_test_harness.schemas.results import Verdict
from ai_test_harness.schemas.scenario import Scenario
from ai_test_harness.specs_loader import load_specs
from ai_test_harness.state import initial_state


def _run_one(graph, scenario: Scenario) -> dict:
    try:
        return graph.invoke(initial_state(scenario))
    except Exception as exc:  # noqa: BLE001 - one broken scenario must not stop the run
        return {
            "scenario": scenario,
            "attempts": 0,
            "log": [],
            "verdict": Verdict(
                scenario_id=scenario.id,
                outcome="infra_error",
                reason=f"harness error: {type(exc).__name__}: {exc}",
            ),
        }


def run_scenarios(
    graph, scenarios: list[Scenario], infra_retry_delay_s: float
) -> list[dict]:
    """Run every scenario; retry ONCE, after a delay, only those that ended in infra_error.

    Product bugs and test defects are never retried: retrying a real bug until it
    passes is how intermittent bugs get hidden.
    """
    finals = [_run_one(graph, scenario) for scenario in scenarios]

    to_retry = [
        i for i, final in enumerate(finals) if final["verdict"].outcome == "infra_error"
    ]
    if to_retry:
        print(
            f"Retrying {len(to_retry)} scenario(s) after infra errors in {infra_retry_delay_s:g}s"
        )
        time.sleep(infra_retry_delay_s)
        for i in to_retry:
            finals[i] = {**_run_one(graph, scenarios[i]), "infra_retried": True}
    return finals


def run_specs(specs_dir: Path = Path("specs"), only: str | None = None) -> list[dict]:
    graph = build_graph(make_planner(), make_executor(), evaluator)
    scenarios = [s for s in load_specs(specs_dir) if not only or only in s.id]
    # Default 60 s: Groq's tokens-per-minute window resets every minute.
    delay = float(os.getenv("INFRA_RETRY_DELAY_S", "60"))
    return run_scenarios(graph, scenarios, infra_retry_delay_s=delay)


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
        retried = " (retried after infra_error)" if final.get("infra_retried") else ""
        lines.append(
            f"| {OUTCOME_ICONS[verdict.outcome]} | `{verdict.scenario_id}` "
            f"| {verdict.outcome}{retried} | {final['attempts']} |"
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
