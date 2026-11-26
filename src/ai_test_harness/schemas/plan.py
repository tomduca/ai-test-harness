"""Planner output: the concrete test plan for one scenario."""

from pydantic import BaseModel


class TestPlan(BaseModel):
    __test__ = False  # not a pytest test class, despite the name
    scenario_id: str
    actions: list[
        str
    ]  # placeholder: becomes typed Playwright actions in the planner step
