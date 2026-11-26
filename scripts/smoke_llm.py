"""Smoke test: one structured-output call to the configured LLM provider."""

from pydantic import BaseModel

from ai_test_harness.llm import get_llm


class Station(BaseModel):
    callsign: str
    grid_locator: str
    city: str


result = get_llm(Station).invoke(
    "Extract the station data: LU2MET operates from Mendoza, Argentina, grid square FF57oc."
)
print(type(result).__name__, result)
