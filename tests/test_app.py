import json

import pytest
from fastapi.testclient import TestClient

from cair import app as appmod
from cair import config, db, neat, view


@pytest.fixture
def client(tmp_path, monkeypatch, fixed_fx, llm_says):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "cair.db")
    monkeypatch.setattr(config, "SECURE_COOKIES", False)
    monkeypatch.setattr(neat, "post_trace", lambda trace, timeout=15.0: {"success": True, "trace_id": "f" * 32})
    llm_says("Use Payoneer. Wise is refused. Line 10 stays blank.")
    db.init()
    appmod._hits.clear()
    with TestClient(appmod.app) as c:
        yield c


def test_plan_confirm_and_page(client):
    r = client.post("/api/plan", json={"payer": "devpost", "amount": "7000", "country": "ID",
                                       "rails": ["payoneer", "wise"], "planner": "v1"})
    assert r.status_code == 200
    pid = r.json()["plan_id"]
    assert "REFUSED" in r.json()["html"] and "Leave blank" in r.json()["html"]
    row = db.get_plan(pid)
    assert row["planner"] == "v2"  # v1 is not routable from the web: it exists only in scripts/eval.py
    assert client.post(f"/api/plan/{pid}/confirm", json={"line": "line10"}).json()["ok"]
    assert client.post(f"/api/plan/{pid}/confirm", json={"line": "nonsense"}).status_code == 400
    assert client.get(f"/plan/{pid}").status_code == 200


def test_bad_input_is_rejected(client):
    assert client.post("/api/plan", json={"payer": "x", "amount": "1", "country": "ID"}).status_code == 400
    assert client.post("/api/plan", json={"payer": "devpost", "amount": "-5", "country": "ID",
                                          "rails": ["wise"]}).status_code == 400


def test_rate_limit(client):
    body = {"payer": "devpost", "amount": "100", "country": "ID", "rails": ["payoneer"]}
    codes = [client.post("/api/plan", json=body).status_code for _ in range(13)]
    assert codes[-1] == 429


def test_verify_has_no_raw_amounts(client, monkeypatch):
    pid = client.post("/api/plan", json={"payer": "devpost", "amount": "7123.45", "country": "ID",
                                         "rails": ["payoneer", "wise"]}).json()["plan_id"]
    secret_span = {"name": "fee_calc", "type": "tool_call", "status": "SUCCESS", "duration_ms": 1.2,
                   "input_value": '{"gross": "7123.45"}', "output_value": '{"withheld": "2137.04"}'}
    monkeypatch.setattr(neat, "mcp", lambda calls, timeout=30.0: [{"span_count": 1, "spans": [secret_span]}] * len(calls))
    rows, source = view.verify_rows(db.recent_plans(20))
    blob = json.dumps(rows)
    assert "7123" in json.dumps(dict(db.get_plan(pid)))  # the DB has it…
    assert "7123" not in blob and "2137" not in blob and "input_value" not in blob  # …the public projection does not
    assert rows[0]["band"] == "> $5k" and rows[0]["spans"][0]["name"] == "fee_calc"
    html = client.get("/verify").text
    assert "7123" not in html and "2137" not in html


def test_healthz(client):
    assert client.get("/healthz").json()["ok"] is True
