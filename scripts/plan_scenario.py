"""Print the plan the LLM generates for one scenario.

Usage: uv run python scripts/plan_scenario.py [scenario-id-substring]
"""

import sys
from pathlib import Path

from ai_test_harness.nodes.planner import make_planner
from ai_test_harness.specs_loader import load_specs
from ai_test_harness.state import initial_state

query = sys.argv[1] if len(sys.argv) > 1 else "main-menu"
scenario = next(s for s in load_specs(Path("specs")) if query in s.id)

result = make_planner()(initial_state(scenario))
print(scenario.id)
print(*result["log"], sep="\n")
print(result["plan"].model_dump_json(indent=2, exclude_none=True))
