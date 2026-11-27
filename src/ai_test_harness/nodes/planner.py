"""Planner node: turns a Gherkin scenario into a validated TestPlan using an LLM."""

import os
from collections.abc import Callable
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from ai_test_harness.llm import get_llm
from ai_test_harness.schemas.plan import TestPlan
from ai_test_harness.schemas.scenario import Scenario
from ai_test_harness.state import ScenarioState

MAX_SELF_CORRECTIONS = 2

# Actions that target ONE element.
SINGLE_TARGET_ACTIONS = {"click", "fill", "expect_visible", "expect_text"}
# Roles that usually appear many times on a page: without a name they are ambiguous.
# Landmarks and regions such as status, main or a single table are fine without one.
REPEATABLE_ROLES = {
    "link",
    "button",
    "heading",
    "listitem",
    "row",
    "cell",
    "columnheader",
    "option",
    "img",
    "textbox",
    "combobox",
}
API_ASSERTIONS = {"expect_status", "expect_contract", "expect_json"}

SYSTEM_PROMPT = """\
You are a senior QA automation engineer. Translate ONE Gherkin scenario into a
test plan, using ONLY the actions defined in the output schema.

General rules:
- Implement every step with at least one action, and set `step` to that step's [index].
- Outcome steps (Then/And after Then) must be implemented with expect_* actions.
- Do not add checks the scenario does not ask for.

Browser (UI) rules:
- "I am on the home page" means: goto "/". For other pages, goto the path quoted in the step.
- Prefer locators by role + accessible name. Use css only as a last resort.
- Menus usually live inside the "navigation" landmark: scope them with within.role="navigation".
- Result and validation messages usually live in a region with role "status".
- To type into a field, use fill and locate the field by its label.
- "No X is shown" means expect_hidden.
- The site UI is in Spanish. Use the literal texts quoted in the scenario, symbols included.
- Labels may be rendered in uppercase by CSS: keep exact=false unless exactness matters.

API rules (steps that say "through the API" or talk about responses):
- Call the endpoint with api_get. expect_status, expect_contract and expect_json always
  check the LAST api_get response, so they must come after it.
- Use the API reference below for paths, query parameters, response fields and contracts.
- Pass quoted values exactly as written, including spaces and letter case.
- expect_json values must use real JSON types: true/false for booleans, numbers for numbers.
- "every X" -> all_items_have; "a X logged as" -> any_item_has; "at least one" -> not_empty;
  "no X" -> empty; "less than N hours ago" -> younger_than_hours.
- Paths are site-relative and start with "/".
"""


class PlannerError(RuntimeError):
    """Raised when the LLM cannot produce a plan consistent with the scenario."""


def render_scenario(scenario: Scenario) -> str:
    lines = [f"Feature: {scenario.feature}", f"Scenario: {scenario.name}", "Steps:"]
    for index, step in enumerate(scenario.steps):
        lines.append(f"[{index}] ({step.type}) {step.text}")
        for row in step.data_table or []:
            lines.append("      | " + " | ".join(row) + " |")
    return "\n".join(lines)


def api_reference() -> str:
    """The API contracts, written for humans, double as context for the LLM."""
    contracts_dir = Path(os.getenv("CONTRACTS_DIR", "docs/contracts"))
    return "\n\n".join(
        path.read_text(encoding="utf-8") for path in sorted(contracts_dir.glob("*.md"))
    )


def find_plan_problems(plan: TestPlan, scenario: Scenario) -> list[str]:
    """Semantic checks the schema cannot express: the plan must fit THIS scenario."""
    problems = []
    step_count = len(scenario.steps)
    covered = {action.step for action in plan.actions}

    if unknown := sorted(step for step in covered if step >= step_count):
        problems.append(f"actions reference steps that do not exist: {unknown}")
    if uncovered := sorted(set(range(step_count)) - covered):
        problems.append(f"steps without any action: {uncovered}")

    asserted = {a.step for a in plan.actions if a.action.startswith("expect_")}
    outcome_steps = [
        i for i, step in enumerate(scenario.steps) if step.type == "Outcome"
    ]
    if unasserted := [i for i in outcome_steps if i in covered and i not in asserted]:
        problems.append(
            f"outcome steps must be verified with expect_* actions: {unasserted}"
        )

    if vague := [
        a.step
        for a in plan.actions
        if a.action in SINGLE_TARGET_ACTIONS
        and a.locator.role in REPEATABLE_ROLES
        and not a.locator.name
    ]:
        problems.append(
            f"locators that target one element need role + name, at steps {vague}"
        )

    first_api_get = next(
        (i for i, a in enumerate(plan.actions) if a.action == "api_get"),
        len(plan.actions),
    )
    if early := [
        a.step
        for i, a in enumerate(plan.actions)
        if a.action in API_ASSERTIONS and i < first_api_get
    ]:
        problems.append(f"API assertions need a previous api_get, at steps {early}")

    if stringly := [
        a.step
        for a in plan.actions
        if a.action == "expect_json"
        and isinstance(a.value, str)
        and a.value.lower() in ("true", "false")
    ]:
        problems.append(
            f"expect_json values must be JSON booleans (true/false), not strings, at steps {stringly}"
        )

    return problems


def build_messages(state: ScenarioState) -> list:
    scenario = state["scenario"]
    content = render_scenario(scenario)
    if "@api" in scenario.tags and (reference := api_reference()):
        content += f"\n\nAPI reference:\n{reference}"
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
        messages = build_messages(state)
        log = []

        for corrections in range(MAX_SELF_CORRECTIONS + 1):
            plan = structured_llm.invoke(messages)
            problems = find_plan_problems(plan, scenario)
            if not problems:
                break
            log.append(f"planner: invalid plan ({'; '.join(problems)})")
            # Show the LLM its own answer and exactly what is wrong with it.
            messages = [
                *messages,
                AIMessage(plan.model_dump_json()),
                HumanMessage(
                    "That plan is invalid:\n- "
                    + "\n- ".join(problems)
                    + "\nReturn a corrected plan for the same scenario."
                ),
            ]
        else:
            raise PlannerError(
                f"{scenario.id}: no valid plan after {MAX_SELF_CORRECTIONS} "
                f"self-corrections: {problems}"
            )

        # Identifiers belong to the harness, never to the LLM.
        plan = plan.model_copy(update={"scenario_id": scenario.id})
        attempt = state["attempts"] + 1
        model = getattr(structured_llm, "last_model", None)
        log.append(
            f"planner: attempt {attempt}, {len(plan.actions)} actions, "
            f"{corrections} self-corrections, model={model}"
        )
        return {"plan": plan, "attempts": attempt, "log": log}

    return planner
