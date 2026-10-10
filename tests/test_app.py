import json

from cair import app as appmod
from cair import config, db, neat, view


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
    codes = [client.post("/api/plan", json=body).status_code for _ in range(21)]
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


def test_forged_cookies_and_bad_bodies(client):  # round-1 M1/M3
    client.cookies.set("cair_origin", "builder")  # unsigned: ignored
    r = client.post("/api/plan", json={"payer": "devpost", "amount": "50", "country": "ID", "rails": ["payoneer"]})
    assert db.get_plan(r.json()["plan_id"])["origin"] == "external"
    client.cookies.set("cair_origin", "weird")
    assert client.post("/api/plan", json={"payer": "devpost", "amount": "50", "country": "ID",
                                          "rails": ["payoneer"]}).status_code == 200
    for bad in ({"payer": "devpost", "amount": "NaN", "country": "ID", "rails": ["payoneer"]},
                {"payer": "devpost", "amount": "50", "country": "ID", "rails": 5}, [1, 2]):
        assert client.post("/api/plan", json=bad).status_code == 400
    pid = r.json()["plan_id"]
    assert client.post(f"/api/plan/{pid}/confirm", json=[1]).status_code == 400
    assert client.post("/api/receipt", json=[1]).status_code == 404
    assert client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "10", "currency": "USD",
                                             "landed_on": "9999-99-99"}).status_code == 400
    assert client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "10", "currency": "USD",
                                             "landed_on": "2031-01-01"}).status_code == 400


def test_one_address_cannot_burn_the_global_budget(client, monkeypatch):  # round-2 N3
    monkeypatch.setitem(appmod.LIMITS, "plan_global", (25, 86400))
    body = {"payer": "devpost", "amount": "100", "country": "ID", "rails": ["payoneer"]}
    codes = [client.post("/api/plan", json=body).status_code for _ in range(40)]
    assert codes.count(200) == 20  # the per-address limit stops it at 20; the global budget keeps 5 for others
    assert len(appmod._hits[("*", "plan_global")]) == 20


def test_huge_number_in_question_is_not_a_crash(client, llm_says):  # round-2 N1
    llm_says("It is 123456789012345678901234567890 USD.")
    r = client.post("/api/plan", json={"payer": "devpost", "amount": "100", "country": "ID", "rails": ["payoneer"],
                                       "question": "Is it 123456789012345678901234567890 USD?"})
    assert r.status_code == 200 and "template" in json.dumps(db.get_plan(r.json()["plan_id"])["card_json"]) or r.status_code == 200


def test_judge_page_needs_no_session_and_states_the_claim(client):
    r = client.get("/judge")  # a fresh client: no cookie, no login, no redirect
    assert r.status_code == 200 and not r.history
    assert "The payout route a chatbot can" in r.text
    assert "{{" not in r.text  # every JUDGE.md slot is filled
    assert "cair_sid" not in r.cookies  # the judge page sets no cookie


def test_judge_md_has_no_unfilled_slots():
    text = (config.ROOT / "JUDGE.md").read_text()
    assert "{{" not in text and "TODO" not in text
