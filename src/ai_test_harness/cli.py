"""Command-line interface: ai-test-harness <command> [options]."""

import argparse
import sys

from ai_test_harness.runner import run_specs, write_github_summary
from ai_test_harness.specs_loader import SpecError, load_specs
from ai_test_harness.target import TargetError, available_targets, load_target

OUTCOMES = ("pass", "product_bug", "test_defect", "infra_error")
TARGET_HELP = "target name (default: $HARNESS_TARGET, or the only target available)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-test-harness",
        description="AI-powered test harness: LLM planning, Playwright execution, "
        "deterministic evaluation.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run", help="plan, execute and evaluate a target's scenarios"
    )
    run.add_argument("--target", help=TARGET_HELP)
    run.add_argument(
        "--only", default="", help="run only scenarios whose id contains this"
    )

    scenarios = commands.add_parser(
        "scenarios", help="list a target's scenarios (no LLM)"
    )
    scenarios.add_argument("--target", help=TARGET_HELP)

    commands.add_parser("targets", help="list the available targets")
    return parser


def _print_results(finals: list[dict]) -> None:
    for final in finals:
        verdict = final["verdict"]
        retried = ", retried after infra_error" if final.get("infra_retried") else ""
        print(
            f"{verdict.outcome:12} {verdict.scenario_id}  (attempts: {final['attempts']}{retried})"
        )
        if verdict.outcome != "pass":
            reason = verdict.reason[:1000].replace("\n", "\n             ")
            print(f"             {reason}")
    outcomes = [f["verdict"].outcome for f in finals]
    print(
        f"\n{len(finals)} scenarios: "
        + ", ".join(f"{outcomes.count(o)} {o}" for o in OUTCOMES)
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "targets":
            for name in available_targets():
                target = load_target(name)
                print(f"{target.name:16} {target.base_url}")
            return 0

        target = load_target(args.target)
        if args.command == "scenarios":
            for scenario in load_specs(target.specs_dir):
                print(scenario.id)
            return 0

        finals = run_specs(target, only=args.only or None)
    except (TargetError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2  # usage/configuration error, like argparse itself

    _print_results(finals)
    write_github_summary(finals, title=f"ai-test-harness · {target.name}")
    # Non-zero exit code when anything did not pass: CI relies on this.
    return 0 if all(f["verdict"].outcome == "pass" for f in finals) else 1
