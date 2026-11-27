"""Executor and evaluator outputs."""

from typing import Literal

from pydantic import BaseModel, Field

Outcome = Literal["pass", "product_bug", "test_defect", "infra_error"]
ActionStatus = Literal["passed", "failed", "skipped"]


class ActionResult(BaseModel):
    index: int  # position in the plan
    step: int  # Gherkin step this action implements
    action: str
    status: ActionStatus
    error: str | None = None
    duration_ms: int = 0


class ExecutionResult(BaseModel):
    scenario_id: str
    passed: bool
    actions: list[ActionResult] = Field(default_factory=list)
    error: str | None = (
        None  # infrastructure failure (e.g. the browser could not start)
    )
    console_errors: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)  # screenshot / trace paths


class Verdict(BaseModel):
    scenario_id: str
    outcome: Outcome
    reason: str
