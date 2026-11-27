import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ai_test_harness.nodes.executor import execute_plan
from ai_test_harness.schemas.plan import (
    ApiGet,
    ExpectContract,
    ExpectJson,
    ExpectStatus,
    QueryParam,
    TestPlan,
)

QSOS = {
    "LU1MAW": [
        {
            "date": "2026-06-24",
            "band": "10m",
            "mode": "SSB",
            "lotw_confirmed": True,
            "call_logged": "LU1MAW/M",
        },
        {
            "date": "2026-01-09",
            "band": "40m",
            "mode": "SSB",
            "lotw_confirmed": True,
            "call_logged": "LU1MAW",
        },
    ],
}


class FakeApi(BaseHTTPRequestHandler):
    """A tiny stand-in for the real API, following contract v0.2 (plus one broken call)."""

    last_query = ""

    def do_GET(self):
        url = urlparse(self.path)
        type(self).last_query = url.query
        query = parse_qs(url.query, keep_blank_values=True)
        call = query.get("call", [""])[0].strip().upper()

        if url.path == "/api/health":
            last_sync = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
            self._json(200, {"status": "ok", "last_sync": last_sync, "qso_count": 2})
        elif url.path != "/api/qso":
            self._json(404, {"error": "not_found", "message": "no such endpoint"})
        elif call.startswith("!"):
            self._json(400, {"error": "invalid_callsign", "message": "bad callsign"})
        elif call == "EXTRA1":
            self._json(200, {"call": call, "found": False, "qsos": [], "rst": "59"})
        else:
            qsos = QSOS.get(call.split("/")[0], [])
            self._json(200, {"call": call, "found": bool(qsos), "qsos": qsos})

    def _json(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture(scope="module")
def api_base():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def lookup(call, band=None):
    params = [QueryParam(name="call", value=call)]
    if band:
        params.append(QueryParam(name="band", value=band))
    return ApiGet(path="/api/qso", params=params, step=0)


def run(api_base, tmp_path, *actions):
    plan = TestPlan(scenario_id="fixture::api", actions=list(actions))
    return execute_plan(plan, base_url=api_base, evidence_dir=tmp_path, timeout_ms=2000)


def statuses(result):
    return [r.status for r in result.actions]


def test_a_found_station_meets_the_contract(api_base, tmp_path):
    result = run(
        api_base,
        tmp_path,
        lookup("LU1MAW"),
        ExpectStatus(status=200, step=1),
        ExpectContract(contract="qso_lookup", step=1),
        ExpectJson(field="found", op="equals", value=True, step=1),
        ExpectJson(field="qsos", op="not_empty", step=1),
        ExpectJson(
            field="qsos",
            op="any_item_has",
            item_field="call_logged",
            value="LU1MAW/M",
            step=1,
        ),
    )
    assert result.passed, result.actions
    assert result.api_calls[0].endswith("-> 200")


def test_a_wrong_status_fails(api_base, tmp_path):
    result = run(api_base, tmp_path, lookup("!!bad"), ExpectStatus(status=200, step=1))
    assert statuses(result) == ["passed", "failed"]
    assert "got 400" in result.actions[1].error


def test_undocumented_fields_break_the_contract(api_base, tmp_path):
    result = run(
        api_base,
        tmp_path,
        lookup("EXTRA1"),
        ExpectContract(contract="qso_lookup", step=1),
    )
    assert statuses(result) == ["passed", "failed"]
    assert "rst" in result.actions[1].error


def test_the_error_body_meets_its_contract(api_base, tmp_path):
    result = run(
        api_base,
        tmp_path,
        lookup("!!bad"),
        ExpectContract(contract="api_error", step=1),
        ExpectJson(field="error", op="equals", value="invalid_callsign", step=1),
    )
    assert result.passed, result.actions


def test_booleans_are_not_numbers(api_base, tmp_path):
    result = run(
        api_base,
        tmp_path,
        lookup("LU1MAW"),
        ExpectJson(field="found", op="equals", value=1, step=1),
    )
    assert statuses(result) == ["passed", "failed"]


def test_all_items_have_fails_on_an_empty_list(api_base, tmp_path):
    # Vacuous truth would make "every QSO is on 2m" pass with zero QSOs.
    result = run(
        api_base,
        tmp_path,
        lookup("CA3PHX"),
        ExpectJson(
            field="qsos", op="all_items_have", item_field="band", value="2m", step=1
        ),
    )
    assert statuses(result) == ["passed", "failed"]
    assert "empty" in result.actions[1].error


def test_all_items_have_reports_what_it_saw(api_base, tmp_path):
    result = run(
        api_base,
        tmp_path,
        lookup("LU1MAW"),
        ExpectJson(
            field="qsos", op="all_items_have", item_field="band", value="10m", step=1
        ),
    )
    assert statuses(result) == ["passed", "failed"]
    assert "'40m'" in result.actions[1].error


def test_unknown_fields_are_reported(api_base, tmp_path):
    result = run(
        api_base,
        tmp_path,
        lookup("LU1MAW"),
        ExpectJson(field="station", op="equals", value=True, step=1),
    )
    assert "not found in the response" in result.actions[1].error


def test_health_freshness(api_base, tmp_path):
    result = run(
        api_base,
        tmp_path,
        ApiGet(path="/api/health", step=0),
        ExpectContract(contract="health", step=1),
        ExpectJson(field="last_sync", op="younger_than_hours", value=48, step=1),
    )
    assert result.passed, result.actions


@pytest.mark.parametrize("call", ["LU1MAW/M", " LU3MRP ", "lu3mrp"])
def test_query_values_reach_the_server_unchanged(api_base, tmp_path, call):
    # The slash must be URL-encoded and the spaces kept: the spec tests both.
    run(api_base, tmp_path, lookup(call))
    assert parse_qs(FakeApi.last_query, keep_blank_values=True)["call"] == [call]


def test_assertions_need_a_previous_api_call(api_base, tmp_path):
    result = run(api_base, tmp_path, ExpectStatus(status=200, step=0))
    assert "api_get must come first" in result.actions[0].error


def test_a_wrong_status_skips_the_body_checks(api_base, tmp_path):
    # Regression (real site): 333aaazzz returned 200 instead of 400; the follow-up
    # check for the 'error' field failed as a cascade and was misread as a test defect.
    result = run(
        api_base,
        tmp_path,
        lookup("LU1MAW"),
        ExpectStatus(status=400, step=1),
        ExpectJson(field="error", op="equals", value="invalid_callsign", step=1),
    )
    assert statuses(result) == ["passed", "failed", "skipped"]
