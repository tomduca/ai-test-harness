"""Executor and evaluator outputs."""

from typing import Literal

from pydantic import BaseModel, Field

Outcome = Literal["pass", "product_bug", "test_defect"]


class ExecutionResult(BaseModel):
    scenario_id: str
    passed: bool
    error: str | None = None
    evidence: list[str] = Field(default_factory=list)  # screenshot / trace paths


class Verdict(BaseModel):
    scenario_id: str
    outcome: Outcome
    reason: str