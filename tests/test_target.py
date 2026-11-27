import json

import pytest

from ai_test_harness.target import TargetError, load_target


@pytest.fixture(autouse=True)
def no_default_target(monkeypatch):
    monkeypatch.delenv("HARNESS_TARGET", raising=False)


def make_target(targets_dir, folder, **fields):
    config = {"name": folder, "base_url": "https://example.test/", **fields}
    (targets_dir / folder).mkdir(parents=True)
    (targets_dir / folder / "target.toml").write_text(
        "\n".join(f"{key} = {json.dumps(value)}" for key, value in config.items())
    )


def test_a_target_is_loaded_and_normalized(tmp_path):
    make_target(tmp_path, "demo", planner_hints=["hint"])
    target = load_target("demo", tmp_path)
    assert target.base_url == "https://example.test"  # trailing slash removed
    assert target.specs_dir == tmp_path / "demo" / "specs"
    assert target.planner_hints == ["hint"]


def test_an_unknown_target_lists_the_available_ones(tmp_path):
    make_target(tmp_path, "demo")
    with pytest.raises(
        TargetError, match=r"unknown target 'nope'; available: \['demo'\]"
    ):
        load_target("nope", tmp_path)


def test_the_only_target_is_the_default(tmp_path):
    make_target(tmp_path, "demo")
    assert load_target(None, tmp_path).name == "demo"


def test_the_environment_selects_the_target(tmp_path, monkeypatch):
    make_target(tmp_path, "a")
    make_target(tmp_path, "b")
    monkeypatch.setenv("HARNESS_TARGET", "b")
    assert load_target(None, tmp_path).name == "b"


def test_several_targets_need_a_choice(tmp_path):
    make_target(tmp_path, "a")
    make_target(tmp_path, "b")
    with pytest.raises(TargetError, match="choose a target"):
        load_target(None, tmp_path)


def test_the_name_must_match_the_folder(tmp_path):
    make_target(tmp_path, "demo", name="other")
    with pytest.raises(TargetError, match="must match its folder"):
        load_target("demo", tmp_path)


def test_typos_in_the_config_are_rejected(tmp_path):
    make_target(tmp_path, "demo", planer_hints=["typo"])
    with pytest.raises(TargetError, match="planer_hints"):
        load_target("demo", tmp_path)


def test_a_base_url_without_scheme_is_rejected(tmp_path):
    make_target(tmp_path, "demo", base_url="example.test")
    with pytest.raises(TargetError, match="http"):
        load_target("demo", tmp_path)


def test_the_real_lu2met_target_is_valid():
    target = load_target("lu2met")
    assert target.base_url == "https://www.lu2met.ar"
    assert (target.specs_dir / "navigation.feature").exists()
