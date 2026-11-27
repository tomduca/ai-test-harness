import pytest

from ai_test_harness.cli import main


@pytest.fixture(autouse=True)
def no_default_target(monkeypatch):
    monkeypatch.delenv("HARNESS_TARGET", raising=False)


def test_targets_are_listed(capsys):
    assert main(["targets"]) == 0
    assert "lu2met" in capsys.readouterr().out


def test_scenarios_are_listed_without_any_llm(capsys):
    assert main(["scenarios", "--target", "lu2met"]) == 0
    out = capsys.readouterr().out
    assert "navigation::the-main-menu-offers-exactly-the-expected-items" in out
    assert "qso_lookup::the-log-data-is-kept-up-to-date" in out


def test_an_unknown_target_is_a_usage_error(capsys):
    assert main(["run", "--target", "nope"]) == 2
    assert "unknown target 'nope'" in capsys.readouterr().err
