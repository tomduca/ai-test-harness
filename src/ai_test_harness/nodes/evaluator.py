"""Evaluator node: deterministic classification of an execution into a verdict."""

from ai_test_harness.schemas.results import (
    ActionResult,
    ExecutionResult,
    Outcome,
    Verdict,
)
from ai_test_harness.state import ScenarioState

# Lower number wins when several failures disagree (fix the test before reporting the site).
PRIORITY: dict[str, int] = {"infra_error": 0, "test_defect": 1, "product_bug": 2}

LOCATOR_ACTIONS = {"click", "expect_visible", "expect_text", "expect_items"}
NOT_FOUND_MARKERS = (
    "element(s) not found",
    "resolved to 0 elements",
    "Actual value: []",
)
MAX_REASON_ERROR_CHARS = 300


def classify_failure(result: ActionResult) -> tuple[Outcome, str]:
    """Map one failed action to an outcome, based on Playwright's error signature."""
    error = result.error or ""

    if result.action == "goto" and ("net::ERR_" in error or "Timeout" in error):
        return "infra_error", "the site could not be reached"
    if "strict mode violation" in error:
        return "test_defect", "the locator matched several elements"
    if result.action in LOCATOR_ACTIONS and (
        any(marker in error for marker in NOT_FOUND_MARKERS)
        or ("Timeout" in error and "resolved to" not in error)
    ):
        # Known limitation: a removed element looks the same as a wrong locator.
        return "test_defect", "the locator matched no elements"
    if result.action.startswith("expect_"):
        return "product_bug", "the element exists but the assertion failed"
    return "product_bug", "unclassified failure, needs human review"


def evaluate(execution: ExecutionResult) -> Verdict:
    scenario_id = execution.scenario_id
    if execution.error:
        return Verdict(
            scenario_id=scenario_id, outcome="infra_error", reason=execution.error
        )

    failures = [
        (r, *classify_failure(r)) for r in execution.actions if r.status == "failed"
    ]
    if not failures:
        if execution.passed:
            return Verdict(
                scenario_id=scenario_id,
                outcome="pass",
                reason=f"all {len(execution.actions)} actions passed",
            )
        return Verdict(
            scenario_id=scenario_id,
            outcome="product_bug",
            reason="unclassified: the run did not pass but no action failed",
        )

    outcome = min((o for _, o, _ in failures), key=PRIORITY.__getitem__)
    reason = "; ".join(
        f"step {r.step} {r.action}: {why}. {(r.error or '')[:MAX_REASON_ERROR_CHARS]}"
        for r, _, why in failures
    )
    return Verdict(scenario_id=scenario_id, outcome=outcome, reason=reason)


def evaluator(state: ScenarioState) -> dict:
    verdict = evaluate(state["execution"])
    return {"verdict": verdict, "log": [f"evaluator: {verdict.outcome}"]}
