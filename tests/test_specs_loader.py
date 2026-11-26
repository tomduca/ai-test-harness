from pathlib import Path

import pytest

from ai_test_harness.specs_loader import SpecError, load_feature

NAV = Path("specs/features/navigation.feature")


def test_outline_is_expanded_into_one_scenario_per_example():
    outline = [s for s in load_feature(NAV) if s.name.startswith("Each menu item")]
    assert len(outline) == 5
    assert [s.id[-3:] for s in outline] == ["[1]", "[2]", "[3]", "[4]", "[5]"]


def test_placeholders_are_replaced():
    first = next(s for s in load_feature(NAV) if s.name.startswith("Each menu item"))
    assert first.steps[-1].text == 'I see content titled "Del banco de trabajo"'


def test_background_is_prepended_to_every_scenario():
    assert all(s.steps[0].text == "I am on the home page" for s in load_feature(NAV))


def test_feature_tags_are_inherited():
    assert all({"@navigation", "@smoke"} <= set(s.tags) for s in load_feature(NAV))


def test_data_table_is_preserved():
    menu = next(
        s for s in load_feature(NAV) if s.name.startswith("The main menu offers")
    )
    assert menu.steps[-1].data_table == [
        ["Proyectos"],
        ["En el aire"],
        ["QSOs"],
        ["Taller"],
        ["Directorio"],
    ]


def test_duplicate_scenario_names_are_rejected(tmp_path):
    spec = tmp_path / "dup.feature"
    spec.write_text(
        "Feature: Dup\n  Scenario: Same\n    Given a\n  Scenario: Same\n    Given b\n"
    )
    with pytest.raises(SpecError, match="duplicate"):
        load_feature(spec)


def test_invalid_gherkin_is_rejected(tmp_path):
    spec = tmp_path / "bad.feature"
    spec.write_text("This is not Gherkin\n")
    with pytest.raises(SpecError, match="invalid Gherkin"):
        load_feature(spec)
