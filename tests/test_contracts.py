from typing import get_args

import pytest
from pydantic import ValidationError

from ai_test_harness.contracts import CONTRACTS, ContractName, Health, QsoLookup

FOUND = """{"call":"LU1MAW","found":true,"qsos":[
  {"date":"2026-06-24","band":"10m","mode":"SSB","lotw_confirmed":true,"call_logged":"LU1MAW/M"},
  {"date":"2026-01-09","band":"40m","mode":"SSB","lotw_confirmed":true,"call_logged":"LU1MAW"}]}"""
NOT_FOUND = '{"call":"CA3PHX","found":false,"qsos":[]}'
HEALTH = '{"status":"ok","last_sync":"2026-11-26T02:00:32Z","qso_count":4510}'


def test_real_found_response_matches():
    assert QsoLookup.model_validate_json(FOUND).qsos[0].call_logged == "LU1MAW/M"


def test_real_not_found_response_matches():
    assert QsoLookup.model_validate_json(NOT_FOUND).found is False


def test_real_health_response_matches():
    assert Health.model_validate_json(HEALTH).qso_count == 4510


def test_a_v01_response_without_call_logged_is_rejected():
    v01 = '{"call":"X","found":true,"qsos":[{"date":"2026-01-01","band":"20m","mode":"FT8","lotw_confirmed":true}]}'
    with pytest.raises(ValidationError, match="call_logged"):
        QsoLookup.model_validate_json(v01)


def test_undocumented_fields_are_rejected():
    extra = NOT_FOUND.replace('"qsos":[]', '"qsos":[],"rst":"59"')
    with pytest.raises(ValidationError, match="rst"):
        QsoLookup.model_validate_json(extra)


def test_not_found_with_qsos_is_rejected():
    inconsistent = FOUND.replace('"found":true', '"found":false')
    with pytest.raises(ValidationError, match="found is false"):
        QsoLookup.model_validate_json(inconsistent)


def test_types_are_strict():
    with pytest.raises(ValidationError):
        QsoLookup.model_validate_json(NOT_FOUND.replace("false", '"false"'))


def test_every_contract_name_has_a_model():
    assert set(get_args(ContractName)) == set(CONTRACTS)
