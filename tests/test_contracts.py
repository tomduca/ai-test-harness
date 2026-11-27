from pathlib import Path

import pytest

from ai_test_harness.contracts import ContractError, ContractSet

LU2MET = ContractSet.load(Path("targets/lu2met/openapi.yaml"))

FOUND = """{"call":"LU1MAW","found":true,"qsos":[
  {"date":"2026-06-24","band":"10m","mode":"SSB","lotw_confirmed":true,"call_logged":"LU1MAW/M"},
  {"date":"2026-01-09","band":"40m","mode":"SSB","lotw_confirmed":true,"call_logged":"LU1MAW"}]}"""
NOT_FOUND = '{"call":"CA3PHX","found":false,"qsos":[]}'
HEALTH = '{"status":"ok","last_sync":"2026-11-26T02:00:32Z","qso_count":4510}'
ERROR = (
    '{"error":"invalid_callsign","message":"That does not look like a valid callsign."}'
)


def test_contract_names_come_from_the_openapi_document():
    assert LU2MET.names == ["ApiError", "Health", "Qso", "QsoLookup"]


@pytest.mark.parametrize(
    "name, body",
    [
        ("QsoLookup", FOUND),
        ("QsoLookup", NOT_FOUND),
        ("Health", HEALTH),
        ("ApiError", ERROR),
    ],
)
def test_real_responses_match_the_contract(name, body):
    LU2MET.validate(name, body)


def test_a_v01_response_without_call_logged_is_rejected():
    v01 = (
        '{"call":"X","found":true,"qsos":[{"date":"2026-01-01","band":"20m",'
        '"mode":"FT8","lotw_confirmed":true}]}'
    )
    with pytest.raises(ContractError, match="call_logged"):
        LU2MET.validate("QsoLookup", v01)


def test_undocumented_fields_are_rejected():
    with pytest.raises(ContractError, match="rst"):
        LU2MET.validate(
            "QsoLookup", NOT_FOUND.replace('"qsos":[]', '"qsos":[],"rst":"59"')
        )


def test_not_found_with_qsos_is_rejected():
    with pytest.raises(ContractError, match="qsos"):
        LU2MET.validate("QsoLookup", FOUND.replace('"found":true', '"found":false'))


def test_types_are_strict():
    with pytest.raises(ContractError, match="boolean"):
        LU2MET.validate("QsoLookup", NOT_FOUND.replace("false", '"false"'))


def test_dates_are_checked():
    with pytest.raises(ContractError, match="date"):
        LU2MET.validate("QsoLookup", FOUND.replace("2026-06-24", "24/06/2026"))


def test_an_unknown_contract_is_reported():
    with pytest.raises(ContractError, match="unknown contract 'Nope'"):
        LU2MET.validate("Nope", NOT_FOUND)


def test_a_missing_document_is_reported(tmp_path):
    with pytest.raises(ContractError, match="no contract document"):
        ContractSet.load(tmp_path / "openapi.yaml")
