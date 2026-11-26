"""Planner output: the concrete test plan for one scenario."""

from pydantic import BaseModel


class TestPlan(BaseModel):
    scenario_id: str
    actions: list[str]  # placeholder: becomes typed Playwright actions in the planner step