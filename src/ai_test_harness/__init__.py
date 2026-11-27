def main() -> None:
    import sys

    from ai_test_harness.runner import run_specs, write_github_summary

    only = sys.argv[1] if len(sys.argv) > 1 else None
    finals = run_specs(only=only)

    for final in finals:
        verdict = final["verdict"]
        print(
            f"{verdict.outcome:12} {verdict.scenario_id}  (attempts: {final['attempts']})"
        )
        if verdict.outcome != "pass":
            reason = verdict.reason[:1000].replace("\n", "\n             ")
            print(f"             {reason}")
    outcomes = [f["verdict"].outcome for f in finals]
    print(
        f"\n{len(finals)} scenarios: "
        + ", ".join(
            f"{outcomes.count(o)} {o}"
            for o in ("pass", "product_bug", "test_defect", "infra_error")
        )
    )
    # Non-zero exit code when anything did not pass: CI will rely on this.
    write_github_summary(finals)
    sys.exit(0 if all(o == "pass" for o in outcomes) else 1)
