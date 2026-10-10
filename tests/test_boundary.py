"""Permission-boundary tests: what the public surface must never return, and who can claim to be the builder."""
import json
import re

import pytest

from cair import config, db, neat

SECRETS = {"NEATLOGS_API_KEY": "api-SENTINEL-key", "NEATLOGS_WRITE_KEY": "write-SENTINEL-key",
           "LLM_API_KEY": "sk-SENTINEL-llm", "BUILDER_TOKEN": "SENTINEL-builder-token",
           "COOKIE_SECRET": "SENTINEL-cookie-secret"}


@pytest.fixture
def secrets_set(monkeypatch):
    for name, value in SECRETS.items():
        monkeypatch.setattr(config, name, value)


def _plan(client):
    r = client.post("/api/plan", json={"payer": "devpost", "amount": "7123.45", "country": "ID",
                                       "rails": ["payoneer", "wise"]})
    assert r.status_code == 200
    return r.json()["plan_id"]


def test_no_public_route_returns_a_secret(client, secrets_set, monkeypatch):
    monkeypatch.setattr(neat, "mcp", lambda calls, timeout=30.0: [{"span_count": 0, "spans": []}] * len(calls))
    pid = _plan(client)
    client.post(f"/api/plan/{pid}/confirm", json={"line": "line10"})
    bodies = [client.get(p).text for p in ("/", "/rules", "/rules.csv", "/healthz", "/verify", "/judge",
                                           f"/plan/{pid}", f"/api/plan/{pid}", "/static/app.js", "/static/cair.css")]
    blob = "\n".join(bodies)
    for name, value in SECRETS.items():
        assert value not in blob, f"{name} leaked into a public response"


def test_public_plan_api_has_no_raw_tool_errors_or_internals(client):
    pid = _plan(client)
    out = client.get(f"/api/plan/{pid}").json()
    assert "tool_outputs" not in out and "llm_usage" not in out
    assert all("error" not in r for r in out["recovery"])
    assert re.search(r"Traceback|File \"", json.dumps(out)) is None


def test_wrong_or_missing_builder_token_never_grants_builder_origin(client, secrets_set):
    for url in ("/?b=wrong", "/?b=", "/?b=SENTINEL-builder-token-extra"):
        client.cookies.clear()
        assert client.get(url).status_code == 200
        assert "cair_origin" not in client.cookies
    client.cookies.clear()
    client.get("/?b=SENTINEL-builder-token")  # the one right token
    pid = _plan(client)
    assert db.get_plan(pid)["origin"] == "builder"


def test_origin_query_cannot_be_forged_into_builder(client):
    client.get("/?src=builder")
    pid = _plan(client)
    assert db.get_plan(pid)["origin"] == "external"


def test_a_plan_id_that_does_not_exist_is_a_404_not_a_leak(client):
    for path in ("/plan/nope", "/api/plan/nope"):
        r = client.get(path)
        assert r.status_code == 404 and "Traceback" not in r.text


def test_input_errors_are_fixed_messages_not_exception_text(client):
    """CodeQL py/stack-trace-exposure: an exception's text must never be the response body."""
    r = client.post("/api/plan", json={"payer": "devpost", "amount": "abc", "country": "ID", "rails": ["wise"]})
    assert r.status_code == 400 and r.json()["error"] == "Enter the amount in USD, e.g. 7000."
    r = client.post("/api/plan", json={"payer": "nobody", "amount": "5", "country": "ID"})
    assert r.json()["error"] == "Pick who is paying you."


def test_a_validly_signed_but_malformed_cookie_is_never_written_back(client):
    """CodeQL py/cookie-injection: only a well-formed id is echoed into Set-Cookie, even when the HMAC is valid."""
    from cair import app as appmod
    client.cookies.set("cair_sid", appmod._sign("evil; Path=/; Domain=x"))
    r = client.get("/")
    assert "evil" not in r.headers.get("set-cookie", "") and "Domain=x" not in r.headers.get("set-cookie", "")
