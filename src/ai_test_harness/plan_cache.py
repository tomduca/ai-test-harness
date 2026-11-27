"""Cache of proven plans: a plan that passed against the real site is reused as is."""

import hashlib
from pathlib import Path

from ai_test_harness.schemas.plan import TestPlan
from ai_test_harness.schemas.scenario import Scenario


class PlanCache:
    def __init__(self, directory: Path, fingerprint: str):
        # fingerprint: changes when the planner's prompt, vocabulary or contracts change.
        self.directory = directory
        self.fingerprint = fingerprint

    def _path(self, scenario: Scenario) -> Path:
        material = self.fingerprint + "\n" + scenario.model_dump_json(exclude={"uri"})
        return (
            self.directory
            / f"{hashlib.sha256(material.encode()).hexdigest()[:32]}.json"
        )

    def get(self, scenario: Scenario) -> TestPlan | None:
        path = self._path(scenario)
        if not path.exists():
            return None
        try:
            return TestPlan.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:  # corrupted or written by an older vocabulary: ignore it
            return None

    def put(self, scenario: Scenario, plan: TestPlan) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(scenario).write_text(
            plan.model_dump_json(indent=2), encoding="utf-8"
        )
