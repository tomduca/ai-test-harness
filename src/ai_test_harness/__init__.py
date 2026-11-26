def main() -> None:
    from pathlib import Path

    from ai_test_harness.specs_loader import load_specs

    for scenario in load_specs(Path("specs")):
        print(f"{scenario.id:70} {len(scenario.steps)} steps  {scenario.tags}")