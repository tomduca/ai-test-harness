from ai_test_harness.plan_cache import PlanCache
from ai_test_harness.schemas.plan import Goto, TestPlan
from ai_test_harness.schemas.scenario import Scenario, Step

SCENARIO = Scenario(
    id="demo::s", feature="Demo", name="s", uri="demo.feature", steps=[Step(text="a")]
)
PLAN = TestPlan(scenario_id="demo::s", actions=[Goto(path="/", step=0)])


def test_a_stored_plan_is_returned(tmp_path):
    cache = PlanCache(tmp_path, fingerprint="v1")
    cache.put(SCENARIO, PLAN)
    assert cache.get(SCENARIO) == PLAN


def test_a_changed_scenario_misses(tmp_path):
    cache = PlanCache(tmp_path, fingerprint="v1")
    cache.put(SCENARIO, PLAN)
    edited = SCENARIO.model_copy(update={"steps": [Step(text="a, edited")]})
    assert cache.get(edited) is None


def test_a_changed_planner_misses(tmp_path):
    PlanCache(tmp_path, fingerprint="v1").put(SCENARIO, PLAN)
    assert PlanCache(tmp_path, fingerprint="v2").get(SCENARIO) is None


def test_a_corrupted_entry_is_ignored(tmp_path):
    cache = PlanCache(tmp_path, fingerprint="v1")
    cache.put(SCENARIO, PLAN)
    next(tmp_path.glob("*.json")).write_text("{not json")
    assert cache.get(SCENARIO) is None
