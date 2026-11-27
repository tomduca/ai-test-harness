import pytest
from pydantic import ValidationError

from ai_test_harness.schemas.plan import ExpectItems, Goto, Locator, TestPlan

MENU_PLAN = {
    "scenario_id": "navigation::the-main-menu-offers-exactly-the-expected-items",
    "actions": [
        {"action": "goto", "path": "/", "step": 0},
        {
            "action": "expect_items",
            "locator": {"role": "link", "within": {"role": "navigation"}},
            "items": ["Proyectos", "En el aire", "QSOs", "Taller", "Directorio"],
            "step": 1,
        },
    ],
}


def test_llm_json_is_parsed_into_typed_actions():
    plan = TestPlan.model_validate(MENU_PLAN)
    assert isinstance(plan.actions[0], Goto)
    assert isinstance(plan.actions[1], ExpectItems)
    assert plan.actions[1].locator.within.role == "navigation"


def test_unknown_action_is_rejected():
    with pytest.raises(ValidationError):
        TestPlan.model_validate(
            {"scenario_id": "x", "actions": [{"action": "hover_magically", "step": 0}]}
        )


def test_empty_plan_is_rejected():
    with pytest.raises(ValidationError):
        TestPlan(scenario_id="x", actions=[])


@pytest.mark.parametrize(
    "path", ["https://evil.example", "//evil.example", "en/", "/\n", "/ en/", "/en/\t"]
)
def test_navigation_cannot_leave_the_site(path):
    with pytest.raises(ValidationError):
        Goto(path=path, step=0)


def test_locator_needs_exactly_one_strategy():
    with pytest.raises(ValidationError, match="exactly one"):
        Locator()
    with pytest.raises(ValidationError, match="exactly one"):
        Locator(role="link", css="a")


def test_name_requires_role():
    with pytest.raises(ValidationError, match="only valid together with 'role'"):
        Locator(text="Taller", name="Taller")


def test_invented_roles_are_rejected():
    with pytest.raises(ValidationError):
        Locator(role="menu-thingy")


def test_step_index_cannot_be_negative():
    with pytest.raises(ValidationError):
        Goto(path="/", step=-1)


def test_llm_schema_requires_the_action_discriminator():
    # Regression: with a default, `action` was optional in the JSON schema and
    # gpt-oss (json_schema mode) omitted it, so plans could not be parsed.
    defs = TestPlan.model_json_schema()["$defs"]
    action_models = [d for d in defs.values() if "action" in d.get("properties", {})]
    assert len(action_models) == 8
    assert all("action" in d["required"] for d in action_models)
