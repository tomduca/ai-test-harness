from typing import get_args
from urllib.parse import urlparse

from ai_test_harness.nodes.executor import ActionRunner, execute_plan
from ai_test_harness.schemas.plan import (
    Action,
    Click,
    ExpectHidden,
    ExpectImagesLoaded,
    ExpectItems,
    ExpectNoConsoleErrors,
    ExpectText,
    ExpectUrlPath,
    ExpectVisible,
    Fill,
    Goto,
    Locator,
    Scope,
    TestPlan,
)

BASE = "http://harness.test"


def html(body: str) -> str:
    # data: favicon avoids an extra request (and a 404 console error) on every page
    return f'<!doctype html><html><head><link rel="icon" href="data:,"></head><body>{body}</body></html>'


PAGES = {
    "/": html(
        '<nav><a href="#banco">Proyectos</a><a href="#taller">Taller</a></nav>'
        '<section id="banco"><h2>Del banco de trabajo</h2></section>'
        '<section id="taller"><h2>El taller</h2></section>'
        '<a href="/en/">EN</a>'
    ),
    "/en/": html('<nav><a href="/">Projects</a></nav>'),
    "/broken-js/": html("<script>console.error('boom')</script>"),
    "/broken-img/": html('<img src="/missing.png" alt="missing">'),
    "/lang/": html('<nav><a href="#aire">En el aire</a></nav><a href="/en/">EN</a>'),
    "/form/": html(
        '<label for="c">Tu indicativo</label>'
        '<input id="c" oninput="document.getElementById(\'s\').textContent = this.value">'
        '<p id="s" role="status"></p>'
    ),
}


def fake_site(route):
    path = urlparse(route.request.url).path
    if path in PAGES:
        route.fulfill(status=200, content_type="text/html", body=PAGES[path])
    else:
        route.fulfill(status=404, body="not found")


MENU = Locator(role="link", within=Scope(role="navigation"))


def run(tmp_path, *actions, route=fake_site):
    plan = TestPlan(scenario_id="fixture::scenario", actions=list(actions))
    return execute_plan(
        plan, base_url=BASE, evidence_dir=tmp_path, timeout_ms=1500, route=route
    )


def statuses(result):
    return [r.status for r in result.actions]


def test_every_action_in_the_vocabulary_has_a_handler():
    action_types = get_args(get_args(Action)[0])
    names = [cls.model_fields["action"].default for cls in action_types]
    assert [n for n in names if not hasattr(ActionRunner, f"_{n}")] == []


def test_a_passing_plan_produces_evidence(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        ExpectItems(locator=MENU, items=["Proyectos", "Taller"], step=1),
        Click(locator=Locator(role="link", name="Taller"), step=2),
        ExpectVisible(locator=Locator(role="heading", name="El taller"), step=3),
    )
    assert result.passed, result.actions
    assert (tmp_path / "trace.zip").exists()
    assert (tmp_path / "final.png").exists()


def test_extra_menu_item_fails_the_items_assertion(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        ExpectItems(locator=MENU, items=["Proyectos"], step=1),
    )
    assert statuses(result) == ["passed", "failed"]
    assert not result.passed


def test_failed_assertions_are_soft(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        ExpectVisible(locator=Locator(role="heading", name="Inexistente"), step=1),
        ExpectVisible(locator=Locator(role="heading", name="El taller"), step=2),
    )
    assert statuses(result) == ["passed", "failed", "passed"]


def test_failed_interaction_skips_the_rest(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        Click(locator=Locator(role="link", name="Mapa"), step=1),
        ExpectVisible(locator=Locator(role="heading", name="El taller"), step=2),
    )
    assert statuses(result) == ["passed", "failed", "skipped"]


def test_url_path_after_navigation(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        Click(locator=Locator(role="link", name="EN"), step=1),
        ExpectUrlPath(path="/en/", step=2),
    )
    assert result.passed, result.actions


def test_console_errors_are_detected(tmp_path):
    result = run(
        tmp_path, Goto(path="/broken-js/", step=0), ExpectNoConsoleErrors(step=1)
    )
    assert statuses(result) == ["passed", "failed"]
    assert "boom" in result.actions[1].error


def test_broken_images_are_detected(tmp_path):
    result = run(
        tmp_path, Goto(path="/broken-img/", step=0), ExpectImagesLoaded(step=1)
    )
    assert statuses(result) == ["passed", "failed"]
    assert "missing.png" in result.actions[1].error


def test_unreachable_site_is_recorded_as_a_failed_navigation(tmp_path):
    # No route: harness.test is a reserved TLD that never resolves.
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        ExpectItems(locator=MENU, items=["x"], step=1),
        route=None,
    )
    assert statuses(result) == ["failed", "skipped"]
    assert "net::ERR" in result.actions[0].error


def test_short_names_never_match_longer_labels(tmp_path):
    # Regression (real site): substring matching made "EN" click "En el aire".
    result = run(
        tmp_path,
        Goto(path="/lang/", step=0),
        Click(
            locator=Locator(role="link", name="EN", within=Scope(role="navigation")),
            step=1,
        ),
    )
    assert statuses(result) == ["passed", "failed"]  # "EN" is not inside <nav>


def test_names_match_case_insensitively(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/lang/", step=0),
        Click(locator=Locator(role="link", name="en"), step=1),
        ExpectUrlPath(path="/en/", step=2),
    )
    assert result.passed, result.actions


def test_fill_types_into_a_labelled_field(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/form/", step=0),
        Fill(locator=Locator(label="Tu indicativo"), value="LU3MRP", step=1),
        ExpectText(locator=Locator(role="status"), text="LU3MRP", step=2),
    )
    assert result.passed, result.actions


def test_expect_hidden_passes_when_the_element_does_not_exist(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/form/", step=0),
        ExpectHidden(locator=Locator(role="table"), step=1),
    )
    assert result.passed, result.actions


def test_expect_hidden_fails_when_the_element_is_visible(tmp_path):
    result = run(
        tmp_path,
        Goto(path="/", step=0),
        ExpectHidden(locator=Locator(role="heading", name="El taller"), step=1),
    )
    assert statuses(result) == ["passed", "failed"]
