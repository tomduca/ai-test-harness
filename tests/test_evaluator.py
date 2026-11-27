# Reuses the fake site from the executor tests (same folder, so pytest can import it).
from test_executor import MENU, run

from ai_test_harness.nodes.evaluator import evaluate
from ai_test_harness.schemas.plan import (
    Click,
    ExpectItems,
    ExpectVisible,
    Goto,
    Locator,
)
from ai_test_harness.schemas.results import ActionResult, ExecutionResult

REAL_MAPA_ERROR = (
    "Locator expected to have text '['Proyectos', 'En el aire', 'QSOs', 'Taller', 'Directorio']'\n"
    "Actual value: ['Proyectos', 'En el aire', 'Mapa', 'QSOs', 'Taller', 'Directorio']\n"
    'Call log:\n  - waiting for get_by_role("navigation").get_by_role("link")\n'
    "    13 × locator resolved to 6 elements"
)


def execution(*results, error=None):
    return ExecutionResult(
        scenario_id="s",
        passed=error is None and all(r.status == "passed" for r in results),
        actions=list(results),
        error=error,
    )


def failed(action, error, step=1):
    return ActionResult(
        index=step, step=step, action=action, status="failed", error=error
    )


def passed(action="goto", step=0):
    return ActionResult(index=step, step=step, action=action, status="passed")


def test_all_passed_is_a_pass():
    assert evaluate(execution(passed(), passed("expect_visible", 1))).outcome == "pass"


def test_the_real_mapa_failure_is_a_product_bug():
    verdict = evaluate(execution(passed(), failed("expect_items", REAL_MAPA_ERROR)))
    assert verdict.outcome == "product_bug"
    assert "Mapa" in verdict.reason


def test_browser_failure_is_an_infra_error():
    assert (
        evaluate(execution(error="infrastructure: browser crashed")).outcome
        == "infra_error"
    )


def test_unreachable_site_is_an_infra_error():
    verdict = evaluate(execution(failed("goto", "net::ERR_NAME_NOT_RESOLVED", step=0)))
    assert verdict.outcome == "infra_error"


def test_strict_mode_violation_is_a_test_defect():
    verdict = evaluate(
        execution(
            passed(), failed("click", "strict mode violation: resolved to 2 elements")
        )
    )
    assert verdict.outcome == "test_defect"


def test_test_defect_wins_over_product_bug():
    verdict = evaluate(
        execution(
            passed(),
            failed("expect_items", REAL_MAPA_ERROR, step=1),
            failed("expect_visible", "element(s) not found", step=2),
        )
    )
    assert verdict.outcome == "test_defect"
    assert "step 1" in verdict.reason and "step 2" in verdict.reason  # nothing is lost


def test_unknown_failures_are_unclassified_product_bugs():
    verdict = evaluate(
        execution(passed(), failed("click", "something nobody expected"))
    )
    assert verdict.outcome == "product_bug"
    assert "unclassified" in verdict.reason


# --- Contract with real Playwright error messages (fake site, real browser) ---


def test_real_missing_element_is_a_test_defect(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        ExpectVisible(locator=Locator(role="heading", name="Inexistente"), step=1),
    )
    assert evaluate(result).outcome == "test_defect"


def test_real_missing_click_target_is_a_test_defect(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        Click(locator=Locator(role="link", name="Mapa"), step=1),
    )
    assert evaluate(result).outcome == "test_defect"


def test_real_extra_menu_item_is_a_product_bug(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        ExpectItems(locator=MENU, items=["Proyectos"], step=1),
    )
    assert evaluate(result).outcome == "product_bug"


def test_real_unreachable_site_is_an_infra_error(tmp_path):
    result = run(tmp_path, Goto(path="/", step=0), route=None)
    assert evaluate(result).outcome == "infra_error"
