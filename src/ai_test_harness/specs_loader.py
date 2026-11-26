"""Load Gherkin .feature files into validated Scenario objects."""

import re
from collections import Counter
from pathlib import Path

from gherkin.parser import Parser
from gherkin.pickles.compiler import Compiler

from ai_test_harness.schemas.scenario import Scenario, Step


class SpecError(ValueError):
    """Raised when a feature file is not valid input for the harness."""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _check_unique_names(document: dict, uri: str) -> None:
    # Checked on the AST (not on pickles): outline rows legitimately share a name.
    children = document["feature"].get("children", [])
    names = [child["scenario"]["name"] for child in children if "scenario" in child]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    if duplicates:
        raise SpecError(f"{uri}: duplicate scenario names: {duplicates}")


def _to_step(pickle_step: dict) -> Step:
    table = pickle_step.get("argument", {}).get("dataTable")
    rows = (
        [[cell["value"] for cell in row["cells"]] for row in table["rows"]]
        if table
        else None
    )
    return Step(
        type=pickle_step.get("type", "Unknown"),
        text=pickle_step["text"],
        data_table=rows,
    )


def load_feature(path: Path) -> list[Scenario]:
    uri = path.as_posix()
    try:
        document = Parser().parse(path.read_text(encoding="utf-8"))
    except Exception as exc:  # gherkin raises its own parser exceptions
        raise SpecError(f"{uri}: invalid Gherkin: {exc}") from exc
    if not document.get("feature"):
        raise SpecError(f"{uri}: no Feature found")

    document["uri"] = uri
    _check_unique_names(document, uri)

    feature_name = document["feature"]["name"]
    seen: Counter[str] = Counter()
    scenarios: list[Scenario] = []
    for pickle in Compiler().compile(document):
        base_id = f"{path.stem}::{_slug(pickle['name'])}"
        # Outline rows reference two AST nodes: the scenario and the example row.
        is_outline_row = len(pickle["astNodeIds"]) > 1
        seen[base_id] += 1
        scenarios.append(
            Scenario(
                id=f"{base_id}[{seen[base_id]}]" if is_outline_row else base_id,
                feature=feature_name,
                name=pickle["name"],
                uri=uri,
                tags=[tag["name"] for tag in pickle["tags"]],
                steps=[_to_step(step) for step in pickle["steps"]],
            )
        )
    return scenarios


def load_specs(directory: Path) -> list[Scenario]:
    return [
        scenario
        for feature_file in sorted(directory.rglob("*.feature"))
        for scenario in load_feature(feature_file)
    ]
