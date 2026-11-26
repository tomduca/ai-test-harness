"""Validated representation of an executable Gherkin scenario."""

from pydantic import BaseModel, Field


class Step(BaseModel):
    # Gherkin keyword category: Context (Given), Action (When),
    # Outcome (Then) or Unknown. "And"/"But" inherit the previous type.
    type: str = "Unknown"
    text: str
    data_table: list[list[str]] | None = None


class Scenario(BaseModel):
    id: str  # stable id, e.g. "navigation::switching-the-site-language[1]"
    feature: str
    name: str
    uri: str
    tags: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(min_length=1)
