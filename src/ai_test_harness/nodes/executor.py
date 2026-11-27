"""Executor node: runs a TestPlan with Playwright, deterministically, and collects evidence."""

import os
import re
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import ConsoleMessage, Page, expect, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator as PlaywrightLocator

from ai_test_harness.schemas.plan import Locator, TestPlan
from ai_test_harness.schemas.results import ActionResult, ExecutionResult
from ai_test_harness.state import ScenarioState

# If one of these fails, the page is in an unknown state: the remaining actions are skipped.
# Failed assertions (expect_*) are soft: they are recorded and execution continues.
INTERACTIONS = {"goto", "click"}

MAX_ERROR_CHARS = 600
ANSI_CODES = re.compile(r"\x1b\[[0-9;]*m")

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


class ActionRunner:
    """One handler per action type: `_<action name>`. No interpretation, no LLM."""

    def __init__(self, page: Page, base_url: str, timeout_ms: int):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_ms
        self.console_errors: list[str] = []
        page.on("console", self._on_console)
        page.on("pageerror", lambda exc: self.console_errors.append(str(exc)))

    def _on_console(self, message: ConsoleMessage) -> None:
        if message.type == "error":
            self.console_errors.append(message.text)

    def run(self, action) -> None:
        getattr(self, f"_{action.action}")(action)

    def _goto(self, a):
        self.page.goto(self.base_url + a.path)

    def _click(self, a):
        resolve(self.page, a.locator).click()

    def _expect_visible(self, a):
        expect(resolve(self.page, a.locator)).to_be_visible(timeout=self.timeout)

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
                browser.close()
    except PlaywrightError as exc:
        return ExecutionResult(
            scenario_id=plan.scenario_id,
            passed=False,
            actions=results,
            error=f"infrastructure: {_clean(exc)}",
            evidence=evidence,
        )

    return ExecutionResult(
        scenario_id=plan.scenario_id,
        passed=bool(results) and all(r.status == "passed" for r in results),
        actions=results,
        console_errors=console_errors,
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
