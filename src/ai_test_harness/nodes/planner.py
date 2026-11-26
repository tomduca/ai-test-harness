"""Planner node: turns a Gherkin scenario into a validated TestPlan using an LLM."""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ai_test_harness.llm import get_llm
from ai_test_harness.schemas.plan import TestPlan
from ai_test_harness.schemas.scenario import Scenario
from ai_test_harness.state import ScenarioState

SYSTEM_PROMPT = """\
You are a senior QA automation engineer. Translate ONE Gherkin scenario into a
Playwright test plan, using ONLY the actions defined in the output schema.

Rules:
- Implement every step with at least one action, and set `step` to that step's [index].
- "I am on the home page" means: goto "/".
- Outcome steps (Then/And after Then) must be implemented with expect_* actions.
- Prefer locators by role + accessible name. Use css only as a last resort.
- Menus usually live inside the "navigation" landmark: scope them with within.role="navigation".
- The site UI is in Spanish. Use the literal texts quoted in the scenario.
- Labels may be rendered in uppercase by CSS: keep exact=false unless exactness matters.
- Paths are site-relative and start with "/".
- Do not add checks the scenario does not ask for.
"""


class PlannerError(RuntimeError):
    """Raised when the LLM plan is valid JSON but inconsistent with the scenario."""


def render_scenario(scenario: Scenario) -> str:
    lines = [f"Feature: {scenario.feature}", f"Scenario: {scenario.name}", "Steps:"]
    for index, step in enumerate(scenario.steps):
        lines.append(f"[{index}] ({step.type}) {step.text}")
        for row in step.data_table or []:
            lines.append("      | " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_messages(state: ScenarioState) -> list:
    content = render_scenario(state["scenario"])
    verdict = state.get("verdict")
    if verdict is not None and verdict.outcome == "test_defect" and state.get("plan"):
        content += (
            "\n\nYour previous plan failed because the TEST was wrong, not the site:\n"
            f"{verdict.reason}\n\n"
            f"Previous plan:\n{state['plan'].model_dump_json(indent=2)}\n\n"
            "Return a corrected plan."
        )
    return [SystemMessage(SYSTEM_PROMPT), HumanMessage(content)]


def make_planner(llm: Runnable | None = None) -> Callable[[ScenarioState], dict]:
    def planner(state: ScenarioState) -> dict:
        structured_llm = llm or get_llm(TestPlan)
        scenario = state["scenario"]
        plan = structured_llm.invoke(build_messages(state))

        # Identifiers belong to the harness, never to the LLM.
        plan = plan.model_copy(update={"scenario_id": scenario.id})

        step_count = len(scenario.steps)
        if unknown := sorted({a.step for a in plan.actions if a.step >= step_count}):
            raise PlannerError(
                f"{scenario.id}: actions reference unknown steps {unknown}"
            )

        attempt = state["attempts"] + 1
        log = [f"planner: attempt {attempt}, {len(plan.actions)} actions"]
        if uncovered := sorted(set(range(step_count)) - {a.step for a in plan.actions}):
            log.append(f"planner: WARNING steps without actions {uncovered}")
        return {"plan": plan, "attempts": attempt, "log": log}

    return planner
