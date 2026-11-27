from pathlib import Path

import pytest

from ai_test_harness.nodes.planner import make_planner
from ai_test_harness.specs_loader import load_feature
from ai_test_harness.state import initial_state

pytestmark = pytest.mark.live


def test_llm_plans_the_menu_scenario():
    scenarios = load_feature(Path("targets/lu2met/specs/navigation.feature"))
    scenario = next(s for s in scenarios if s.name.startswith("The main menu offers"))

    plan = make_planner()(initial_state(scenario))["plan"]

    # LLM output varies: assert the shape we need, not the exact plan.
    assert plan.actions[0].action == "goto"
    assert any(a.action == "expect_items" for a in plan.actions)
