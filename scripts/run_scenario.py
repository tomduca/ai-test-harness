"""Plan and execute one scenario against the real site.

Usage: uv run python scripts/run_scenario.py [scenario-id-substring]
"""

import sys
from pathlib import Path

from ai_test_harness.nodes.executor import make_executor
from ai_test_harness.nodes.planner import make_planner
from ai_test_harness.specs_loader import load_specs
from ai_test_harness.state import initial_state

query = sys.argv[1] if len(sys.argv) > 1 else "main-menu"
scenario = next(s for s in load_specs(Path("specs")) if query in s.id)

state = initial_state(scenario)
planned = make_planner()(state)
executed = make_executor()({**state, **planned})

print(scenario.id)
print(*planned["log"], *executed["log"], sep="\n")
for r in executed["execution"].actions:
    print(f"  [{r.status:7}] step {r.step} {r.action} ({r.duration_ms} ms)")
    if r.error:
        print("            " + r.error.replace("\n", "\n            "))
