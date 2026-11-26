"""LangGraph state for a single-scenario run."""

import operator
from typing import Annotated, TypedDict

from ai_test_harness.schemas.plan import TestPlan
from ai_test_harness.schemas.results import ExecutionResult, Verdict
from ai_test_harness.schemas.scenario import Scenario


class ScenarioState(TypedDict):
    scenario: Scenario
    plan: TestPlan | None
    execution: ExecutionResult | None
    verdict: Verdict | None
    attempts: int
    # Reducer: each node returns new log lines and LangGraph appends them.
    log: Annotated[list[str], operator.add]


def initial_state(scenario: Scenario) -> ScenarioState:
    return {
        "scenario": scenario,
        "plan": None,
        "execution": None,
        "verdict": None,
        "attempts": 0,
        "log": [],
    }