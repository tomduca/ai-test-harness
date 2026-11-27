"""Executor node: runs a TestPlan with Playwright, deterministically, and collects evidence."""

import json
import os
import re
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import ConsoleMessage, Page, expect, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator as PlaywrightLocator
from pydantic import ValidationError

from ai_test_harness.contracts import CONTRACTS
from ai_test_harness.schemas.plan import Locator, TestPlan
from ai_test_harness.schemas.results import ActionResult, ExecutionResult
from ai_test_harness.state import ScenarioState

# If one of these fails, the state is unknown: the remaining actions are skipped.
# expect_status is a gate: with an unexpected status, the body is not the one the
# following checks were written for (their failures would be cascades, not findings).
# Other failed assertions (expect_*) are soft: they are recorded and execution continues.
INTERACTIONS = {"goto", "click", "fill", "api_get", "expect_status"}

MAX_ERROR_CHARS = 600
ANSI_CODES = re.compile(r"\x1b\[[0-9;]*m")
_MISSING = object()

# Broken = finished loading with no pixels, or still pending without being lazy-loaded.
BROKEN_IMAGES_JS = """
() => Array.from(document.images)
  .filter(img => (img.complete && img.naturalWidth === 0) || (!img.complete && img.loading !== 'lazy'))
  .map(img => img.currentSrc || img.src)
"""


def _match(value: str, exact: bool) -> str | re.Pattern:
    """exact=True: exact, case-sensitive. Otherwise: the WHOLE text, case-insensitive.

    Never substring: with substring matching, "EN" matched "En el aire" on the real site.
    """
    if exact:
        return value
    return re.compile(rf"^\s*{re.escape(value)}\s*$", re.IGNORECASE)


def resolve(page: Page, loc: Locator) -> PlaywrightLocator:
    """Translate our Locator schema into a Playwright locator."""
    root = page
    if loc.within:
        scope_name = _match(loc.within.name, exact=False) if loc.within.name else None
        root = page.get_by_role(loc.within.role, name=scope_name)
    if loc.role:
        name = _match(loc.name, loc.exact) if loc.name else None
        return root.get_by_role(loc.role, name=name, exact=loc.exact or None)
    if loc.text:
        return root.get_by_text(_match(loc.text, loc.exact), exact=loc.exact or None)
    if loc.label:
        return root.get_by_label(_match(loc.label, loc.exact), exact=loc.exact or None)
    return root.locator(loc.css)


def _clean(exc: Exception) -> str:
    return ANSI_CODES.sub("", str(exc)).strip()[:MAX_ERROR_CHARS]


@dataclass
class ApiResponse:
    url: str
    status: int
    text: str

    def json_body(self) -> Any:
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"response is not JSON: {self.text[:200]!r}") from exc


def _get_path(body: Any, path: str) -> Any:
    """Follow a dot path like 'qsos.0.band' through dicts and lists."""
    current = body
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise AssertionError(f"field '{path}' not found in the response")
    return current


def _same(actual: Any, expected: Any) -> bool:
    """Equality that never confuses booleans with numbers (in Python, True == 1)."""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return (
            isinstance(actual, bool)
            and isinstance(expected, bool)
            and actual == expected
        )
    return actual == expected


class ActionRunner:
    """One handler per action type: `_<action name>`. No interpretation, no LLM."""

    def __init__(self, page: Page, base_url: str, timeout_ms: int):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_ms
        self.console_errors: list[str] = []
        self.api_calls: list[str] = []
        self.last_response: ApiResponse | None = None
        page.on("console", self._on_console)
        page.on("pageerror", lambda exc: self.console_errors.append(str(exc)))

    def _on_console(self, message: ConsoleMessage) -> None:
        if message.type == "error":
            self.console_errors.append(message.text)

    def run(self, action) -> None:
        getattr(self, f"_{action.action}")(action)

    # --- Browser -------------------------------------------------------------

    def _goto(self, a):
        self.page.goto(self.base_url + a.path)

    def _click(self, a):
        resolve(self.page, a.locator).click()

    def _fill(self, a):
        resolve(self.page, a.locator).fill(a.value)

    def _expect_visible(self, a):
        expect(resolve(self.page, a.locator)).to_be_visible(timeout=self.timeout)

    def _expect_hidden(self, a):
        expect(resolve(self.page, a.locator)).to_be_hidden(timeout=self.timeout)

    def _expect_text(self, a):
        expect(resolve(self.page, a.locator)).to_contain_text(
            a.text, ignore_case=not a.locator.exact, timeout=self.timeout
        )

    def _expect_url_path(self, a):
        pattern = re.compile("^" + re.escape(self.base_url + a.path) + r"([?#].*)?$")
        expect(self.page).to_have_url(pattern, timeout=self.timeout)

    def _expect_items(self, a):
        # A list asserts count AND order: an extra or missing item fails.
        expect(resolve(self.page, a.locator)).to_have_text(
            a.items, ignore_case=not a.locator.exact, timeout=self.timeout
        )

    def _expect_no_console_errors(self, a):
        if self.console_errors:
            raise AssertionError(
                f"{len(self.console_errors)} console error(s): {self.console_errors[:5]}"
            )

    def _expect_images_loaded(self, a):
        self.page.wait_for_load_state("load")
        if broken := self.page.evaluate(BROKEN_IMAGES_JS):
            raise AssertionError(f"{len(broken)} image(s) failed to load: {broken[:5]}")

    # --- API (assertions act on the last api_get response) -------------------

    def _api_get(self, a):
        params = {p.name: p.value for p in a.params}
        response = self.page.context.request.get(
            self.base_url + a.path, params=params or None, timeout=self.timeout * 3
        )
        self.last_response = ApiResponse(
            url=response.url, status=response.status, text=response.text()
        )
        self.api_calls.append(f"GET {response.url} -> {response.status}")

    def _response(self) -> ApiResponse:
        if self.last_response is None:
            raise AssertionError("no API response to check: api_get must come first")
        return self.last_response

    def _expect_status(self, a):
        response = self._response()
        if response.status != a.status:
            raise AssertionError(
                f"expected HTTP {a.status}, got {response.status}: {response.text[:200]}"
            )

    def _expect_contract(self, a):
        try:
            CONTRACTS[a.contract].model_validate_json(self._response().text)
        except ValidationError as exc:
            raise AssertionError(
                f"response does not match contract '{a.contract}': {exc}"
            ) from exc

    def _expect_json(self, a):
        actual = _get_path(self._response().json_body(), a.field)

        if a.op == "equals":
            if not _same(actual, a.value):
                raise AssertionError(
                    f"'{a.field}' expected {a.value!r}, got {actual!r}"
                )

        elif a.op in ("empty", "not_empty"):
            if not isinstance(actual, (list, str, dict)):
                raise AssertionError(f"'{a.field}' has no length: {actual!r}")
            if (len(actual) == 0) != (a.op == "empty"):
                raise AssertionError(
                    f"'{a.field}' expected to be {a.op.replace('_', ' ')}, has {len(actual)} item(s)"
                )

        elif a.op in ("any_item_has", "all_items_have"):
            if not isinstance(actual, list):
                raise AssertionError(f"'{a.field}' is not a list: {actual!r}")
            if not actual:
                # An empty list would make all_items_have pass vacuously: a false positive.
                raise AssertionError(f"'{a.field}' is empty: there is nothing to check")
            values = [
                item.get(a.item_field, _MISSING) if isinstance(item, dict) else _MISSING
                for item in actual
            ]
            matches = [_same(value, a.value) for value in values]
            if not (any(matches) if a.op == "any_item_has" else all(matches)):
                seen = sorted({repr(v) for v in values if v is not _MISSING})
                raise AssertionError(
                    f"{a.op} failed: '{a.field}[].{a.item_field}' == {a.value!r}; "
                    f"values seen: {seen[:10]}"
                )

        elif a.op == "younger_than_hours":
            try:
                timestamp = datetime.fromisoformat(str(actual))
            except ValueError as exc:
                raise AssertionError(
                    f"'{a.field}' is not an ISO timestamp: {actual!r}"
                ) from exc
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            age_hours = (datetime.now(UTC) - timestamp).total_seconds() / 3600
            if age_hours >= float(a.value):
                raise AssertionError(
                    f"'{a.field}' is {age_hours:.1f} h old, expected less than {a.value} h"
                )


def execute_plan(
    plan: TestPlan,
    *,
    base_url: str,
    evidence_dir: Path,
    timeout_ms: int = 5000,
    headless: bool = True,
    route: Callable | None = None,
) -> ExecutionResult:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results: list[ActionResult] = []
    evidence: list[str] = []
    console_errors: list[str] = []
    api_calls: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            context.set_default_timeout(timeout_ms)
            context.set_default_navigation_timeout(max(timeout_ms * 3, 15_000))
            if route:
                context.route("**/*", route)
            context.tracing.start(screenshots=True, snapshots=True)
            page = context.new_page()
            runner = ActionRunner(page, base_url, timeout_ms)

            try:
                blocked = False
                for index, action in enumerate(plan.actions):
                    if blocked:
                        results.append(
                            ActionResult(
                                index=index,
                                step=action.step,
                                action=action.action,
                                status="skipped",
                            )
                        )
                        continue
                    started = time.monotonic()
                    try:
                        runner.run(action)
                        status, error = "passed", None
                    except (AssertionError, PlaywrightError) as exc:
                        status, error = "failed", _clean(exc)
                        blocked = action.action in INTERACTIONS
                    results.append(
                        ActionResult(
                            index=index,
                            step=action.step,
                            action=action.action,
                            status=status,
                            error=error,
                            duration_ms=int((time.monotonic() - started) * 1000),
                        )
                    )
            finally:
                # Evidence is collected whatever happened above.
                screenshot = evidence_dir / "final.png"
                with suppress(PlaywrightError):
                    page.screenshot(path=screenshot, full_page=True)
                    evidence.append(str(screenshot))
                trace = evidence_dir / "trace.zip"
                context.tracing.stop(path=trace)
                evidence.append(str(trace))
                console_errors = runner.console_errors
                api_calls = runner.api_calls
                browser.close()
    except PlaywrightError as exc:
        return ExecutionResult(
            scenario_id=plan.scenario_id,
            passed=False,
            actions=results,
            error=f"infrastructure: {_clean(exc)}",
            api_calls=api_calls,
            evidence=evidence,
        )

    return ExecutionResult(
        scenario_id=plan.scenario_id,
        passed=bool(results) and all(r.status == "passed" for r in results),
        actions=results,
        console_errors=console_errors,
        api_calls=api_calls,
        evidence=evidence,
    )


def make_executor(
    base_url: str | None = None,
    reports_dir: str | Path | None = None,
    run_id: str | None = None,
    timeout_ms: int | None = None,
) -> Callable[[ScenarioState], dict]:
    load_dotenv()
    base_url = base_url or os.getenv("BASE_URL", "https://www.lu2met.ar")
    reports_dir = Path(reports_dir or os.getenv("REPORTS_DIR", "reports"))
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    timeout_ms = timeout_ms or int(os.getenv("ACTION_TIMEOUT_MS", "5000"))

    def executor(state: ScenarioState) -> dict:
        plan = state["plan"]
        slug = re.sub(r"[^a-z0-9]+", "-", plan.scenario_id.lower()).strip("-")
        # One folder per attempt: evidence from a retry never overwrites the previous one.
        evidence_dir = reports_dir / run_id / slug / f"attempt-{state['attempts']}"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        plan_file = evidence_dir / "plan.json"
        plan_file.write_text(plan.model_dump_json(indent=2))

        result = execute_plan(
            plan, base_url=base_url, evidence_dir=evidence_dir, timeout_ms=timeout_ms
        )
        result.evidence.insert(0, str(plan_file))
        result_file = evidence_dir / "execution.json"
        result.evidence.append(str(result_file))
        result_file.write_text(result.model_dump_json(indent=2))

        counts = {
            s: sum(r.status == s for r in result.actions)
            for s in ("passed", "failed", "skipped")
        }
        return {
            "execution": result,
            "log": [
                (
                    f"executor: {counts['passed']} passed, {counts['failed']} failed, "
                    f"{counts['skipped']} skipped -> {evidence_dir}"
                )
            ],
        }

    return executor
