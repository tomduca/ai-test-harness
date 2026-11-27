"""Run the full planner -> executor -> evaluator graph over every scenario."""

import os
import time
from pathlib import Path

from ai_test_harness.contracts import ContractSet
from ai_test_harness.graph import build_graph
from ai_test_harness.llm import LLMChainError
from ai_test_harness.nodes.evaluator import evaluator
from ai_test_harness.nodes.executor import make_executor
from ai_test_harness.nodes.planner import make_planner, planner_fingerprint
from ai_test_harness.plan_cache import PlanCache
from ai_test_harness.schemas.results import Verdict
from ai_test_harness.schemas.scenario import Scenario
from ai_test_harness.specs_loader import load_specs
from ai_test_harness.state import initial_state
from ai_test_harness.target import Target


def _run_one(graph, scenario: Scenario) -> dict:
    try:
        return graph.invoke(initial_state(scenario))
    except Exception as exc:  # noqa: BLE001 - one broken scenario must not stop the run
        quota = isinstance(exc, LLMChainError) and exc.daily_quota_exhausted
        prefix = (
            "daily LLM quota exhausted for every model" if quota else "harness error"
        )
        return {
            "scenario": scenario,
            "attempts": 0,
            "log": [],
            "quota_exhausted": quota,
            "verdict": Verdict(
                scenario_id=scenario.id,
                outcome="infra_error",
                reason=f"{prefix}: {type(exc).__name__}: {exc}",
            ),
        }


def run_scenarios(
    graph,
    scenarios: list[Scenario],
    infra_retry_delay_s: float,
    cache: PlanCache | None = None,
) -> list[dict]:
    """Run every scenario; retry ONCE, after a delay, only transient infra errors.
    Product bugs and test defects are never retried: retrying a real bug until it
    passes is how intermittent bugs get hidden. Exhausted daily quotas are not
    retried either: waiting a minute cannot fix them.
    """
    finals = [_run_one(graph, scenario) for scenario in scenarios]

    to_retry = [
        i
        for i, final in enumerate(finals)
        if final["verdict"].outcome == "infra_error"
        and not final.get("quota_exhausted")
    ]
    if exhausted := sum(1 for f in finals if f.get("quota_exhausted")):
        print(f"{exhausted} scenario(s) hit exhausted daily LLM quotas: not retried")
    if to_retry:
        print(
            f"Retrying {len(to_retry)} scenario(s) after infra errors in {infra_retry_delay_s:g}s"
        )
        time.sleep(infra_retry_delay_s)
        for i in to_retry:
            finals[i] = {**_run_one(graph, scenarios[i]), "infra_retried": True}
    if cache is not None:
        # Only passing plans are proven: a product_bug plan could be a misclassified
        # test defect, and caching it would repeat that mistake every day.
        for scenario, final in zip(scenarios, finals, strict=True):
            if final["verdict"].outcome == "pass" and final.get("plan") is not None:
                cache.put(scenario, final["plan"])
    return finals


def run_specs(target: Target, only: str | None = None) -> list[dict]:
    cache_root = os.getenv("PLAN_CACHE_DIR", ".plan-cache")  # empty string disables it
    cache = (
        PlanCache(Path(cache_root) / target.name, planner_fingerprint(target))
        if cache_root
        else None
    )
    contracts = (
        ContractSet.load(target.openapi_path) if target.openapi_path.exists() else None
    )
    executor = make_executor(
        base_url=os.getenv("BASE_URL")
        or target.base_url,  # BASE_URL: e.g. a staging site
        reports_dir=Path(os.getenv("REPORTS_DIR", "reports")) / target.name,
        contracts=contracts,
    )
    planner = make_planner(cache=cache, target=target, contracts=contracts)
    graph = build_graph(planner, executor, evaluator)
    scenarios = [s for s in load_specs(target.specs_dir) if not only or only in s.id]
    # Default 60 s: Groq's tokens-per-minute window resets every minute.
    delay = float(os.getenv("INFRA_RETRY_DELAY_S", "60"))
    return run_scenarios(graph, scenarios, infra_retry_delay_s=delay, cache=cache)


OUTCOME_ICONS = {
    "pass": "✅",
    "product_bug": "🐞",
    "test_defect": "🧪",
    "infra_error": "⚠️",
}


def write_github_summary(
    finals: list[dict], title: str = "ai-test-harness results"
) -> None:
    """Append a results table to the GitHub Actions job summary (no-op outside CI)."""
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        f"## {title}",
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
