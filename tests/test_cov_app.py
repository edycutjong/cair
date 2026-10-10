"""Line + branch coverage for cair/app.py: lifespan ownership, rate-limit table, cookies, confirm/receipt edges."""
import time
from collections import deque
from types import SimpleNamespace

import neatlogs
import pytest

from cair import app as appmod
from cair import config, db, neat, view

BODY = {"payer": "devpost", "amount": "100", "country": "ID", "rails": ["payoneer"]}


@pytest.fixture(autouse=True)
def _clean_tables():
    appmod._hits.clear()
    yield
    appmod._hits.clear()


def _req(host="9.9.9.9"):
    return SimpleNamespace(client=SimpleNamespace(host=host))


def _plan(client):
    return client.post("/api/plan", json=BODY).json()["plan_id"]


# --- lifespan -------------------------------------------------------------------------------------------------
def test_lifespan_owner_inits_flushes_and_shuts_down(tmp_path, monkeypatch):
    calls = []
    fake = SimpleNamespace(
        NeatlogsConfigurationError=neatlogs.NeatlogsConfigurationError,
        init=lambda **kw: calls.append(("init", kw["workflow_name"], kw["tags"])),
        flush=lambda: calls.append(("flush",)),
        shutdown=lambda: calls.append(("shutdown",)))
    monkeypatch.setattr(appmod, "neatlogs", fake)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "cair.db")
    from fastapi.testclient import TestClient
    with TestClient(appmod.app) as c:
        assert calls == [("init", "payout-plan", ["prod"])]
        assert c.get("/healthz").status_code == 200
    assert calls[1:] == [("flush",), ("shutdown",)]


def test_lifespan_host_owned_does_not_flush(tmp_path, monkeypatch):
    calls = []

    def init(**kw):
        raise neatlogs.NeatlogsConfigurationError("already initialised")

    fake = SimpleNamespace(NeatlogsConfigurationError=neatlogs.NeatlogsConfigurationError, init=init,
                           flush=lambda: calls.append("flush"), shutdown=lambda: calls.append("shutdown"))
    monkeypatch.setattr(appmod, "neatlogs", fake)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "cair.db")
    from fastapi.testclient import TestClient
    with TestClient(appmod.app):
        pass
    assert calls == []


# --- rate-limit table -----------------------------------------------------------------------------------------
def test_client_ip_without_client_is_placeholder():
    assert appmod.client_ip(SimpleNamespace(client=None)) == "?"
    assert appmod.client_ip(_req("1.2.3.4")) == "1.2.3.4"


def test_over_drops_hits_older_than_window():
    key = ("ip", "plan")
    now = time.time()
    appmod._hits[key] = deque([now - 1000, now - 900, now - 5])
    assert appmod._over(key, 3, 600) is False  # two stale hits expired, so room remains
    assert len(appmod._hits[key]) == 2  # the recent one + the one just recorded
    assert appmod._over(key, 2, 600) is True  # now full: rejected, not recorded
    assert len(appmod._hits[key]) == 2


def test_limited_evicts_idle_keys_when_table_is_huge():
    now = time.time()
    for i in range(50_001):
        appmod._hits[(f"idle{i}", "plan")] = deque()  # empty queue: evictable
    appmod._hits[("stale", "plan")] = deque([now - 90_000])  # last hit over a day ago: evictable
    appmod._hits[("fresh", "plan")] = deque([now - 10])  # recent: kept
    assert appmod.limited(_req(), "write") is False
    keys = set(appmod._hits)
    assert ("fresh", "plan") in keys and ("stale", "plan") not in keys and ("idle0", "plan") not in keys
    assert ("9.9.9.9", "write") in keys
    assert keys == {("fresh", "plan"), ("9.9.9.9", "write")}  # everything idle or stale was evicted


def test_limited_global_plan_ceiling_applies_only_to_plan(monkeypatch):
    monkeypatch.setitem(appmod.LIMITS, "plan_global", (2, 86400))
    assert appmod.limited(_req("a"), "plan") is False
    assert appmod.limited(_req("b"), "plan") is False
    assert appmod.limited(_req("c"), "plan") is True  # global budget spent, whatever the address
    assert appmod.limited(_req("c"), "write") is False  # writes never touch the global plan ceiling


# --- identity / cookies ---------------------------------------------------------------------------------------
def test_index_origin_cookie_from_src_and_builder_token(client, monkeypatch):
    r = client.get("/?src=ethjkt")
    assert r.status_code == 200
    assert appmod._unsign(r.cookies.get("cair_origin")) == "ethjkt"

    monkeypatch.setattr(config, "BUILDER_TOKEN", "s3cret")
    client.cookies.clear()
    r = client.get("/?b=wrong")
    assert "cair_origin" not in r.cookies
    r = client.get("/?b=s3cret")
    assert appmod._unsign(r.cookies.get("cair_origin")) == "builder"
    pid = client.post("/api/plan", json=BODY).json()["plan_id"]
    assert db.get_plan(pid)["origin"] == "builder"

    monkeypatch.setattr(config, "BUILDER_TOKEN", "")
    client.cookies.clear()
    assert "cair_origin" not in client.get("/?b=").cookies  # no configured token: never grants builder


def test_unsign_rejects_missing_dotless_and_tampered():
    assert appmod._unsign(None) is None
    assert appmod._unsign("nodot") is None
    good = appmod._sign("abc")
    assert appmod._unsign(good) == "abc"
    assert appmod._unsign("abd" + good[3:]) is None
    # signed but not a ULID: replaced with a fresh one
    fresh = appmod._ulid_or_new(appmod._sign("not-a-ulid"))
    assert fresh != "not-a-ulid" and appmod._ULID_RE.fullmatch(fresh)


# --- malformed bodies -----------------------------------------------------------------------------------------
def test_non_json_body_is_treated_as_empty(client):
    hdr = {"content-type": "application/json"}
    assert client.post("/api/plan", content="{not json", headers=hdr).status_code == 400
    pid = _plan(client)
    r = client.post(f"/api/plan/{pid}/confirm", content="{not json", headers=hdr)
    assert r.status_code == 400 and r.json()["error"] == "unknown line"
    r = client.post("/api/receipt", content="{not json", headers=hdr)
    assert r.status_code == 404 and r.json()["error"] == "no such plan"


# --- confirm --------------------------------------------------------------------------------------------------
def test_confirm_unknown_plan_is_404(client):
    assert client.post("/api/plan/01NOSUCHPLAN/confirm", json={"line": "line10"}).status_code == 404


def test_confirm_is_rate_limited(client, monkeypatch):
    pid = _plan(client)
    monkeypatch.setitem(appmod.LIMITS, "write", (1, 600))
    assert client.post(f"/api/plan/{pid}/confirm", json={"line": "line10"}).status_code == 200
    r = client.post(f"/api/plan/{pid}/confirm", json={"line": "line10"})
    assert r.status_code == 429 and r.json() == {"error": "rate limited"}


def test_confirm_survives_tracing_failure(client, monkeypatch):
    pid = _plan(client)

    def boom(trace, timeout=15.0):
        raise RuntimeError("neatlogs down")

    monkeypatch.setattr(neat, "post_trace", boom)
    r = client.post(f"/api/plan/{pid}/confirm", json={"line": "line10"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "line": "line10", "trace_id": None}
    assert db.confirms(pid) == ["line10"]  # still recorded locally


def test_confirm_posts_trace_into_plan_session(client, monkeypatch):
    pid = _plan(client)
    seen = []

    def post(trace, timeout=15.0):
        seen.append(trace)
        return {"trace_id": "a" * 32}

    monkeypatch.setattr(neat, "post_trace", post)
    r = client.post(f"/api/plan/{pid}/confirm", json={"line": "line10"})
    assert r.json()["trace_id"] == "a" * 32
    row = db.get_plan(pid)
    assert seen[0]["attributes"] == {"neatlogs.session.id": row["session_id"],
                                     "neatlogs.end_user.id": row["end_user_hash"]}
    assert seen[0]["children"][0]["name"] == "confirm:line10"


# --- receipt --------------------------------------------------------------------------------------------------
def test_receipt_is_rate_limited(client, monkeypatch):
    monkeypatch.setitem(appmod.LIMITS, "write", (1, 600))
    assert client.post("/api/receipt", json={"plan_id": "x"}).status_code == 404
    r = client.post("/api/receipt", json={"plan_id": "x"})
    assert r.status_code == 429 and r.json() == {"error": "rate limited"}


def test_receipt_validation_errors(client):
    pid = _plan(client)
    post = lambda **kw: client.post("/api/receipt", json={"plan_id": pid, **kw})  # noqa: E731
    assert post(currency="EUR", landed_amount="1").json()["error"] == "unsupported currency"
    for bad in ("", "abc", "0", "-3", "NaN", "Infinity", "1e30", "99999999999"):
        r = post(currency="USD", landed_amount=bad)
        assert r.status_code == 400 and r.json()["error"].startswith("Enter the amount"), bad
    r = post(landed_amount="100", landed_on="31-12-2026")
    assert r.status_code == 400 and r.json()["error"] == "date must be YYYY-MM-DD"
    for far in ("2999-01-01", "2019-12-31"):
        r = post(landed_amount="100", landed_on=far)
        assert r.status_code == 400 and "not possible" in r.json()["error"]
    assert db.receipts(pid) == []


def test_receipt_success_and_replay_label(client, monkeypatch):
    pid = _plan(client)
    calls = []

    def fake(card, amount, currency, landed_on, label, session_id, end_user_hash):
        calls.append((amount, currency, landed_on, label))
        return {"mode": "point", "quoted": "4897.00", "error_pct": "0.1", "unexplained_usd": "0", "verdict": "match",
                "evaluator_trace_id": "e" * 32, "evaluator_error": "secret upstream detail"}

    monkeypatch.setattr(appmod.reconcile, "reconcile", fake)
    monkeypatch.setattr(view, "stamp_view", lambda r: {"verdict": r["verdict"]})
    monkeypatch.setattr(appmod.TEMPLATES, "get_template",
                        lambda name: SimpleNamespace(render=lambda r: f"<stamp {name} {r['verdict']}>"))

    ok = client.post("/api/receipt", json={"plan_id": pid, "currency": "usd", "landed_amount": "4,897.00",
                                           "consent_public": True})
    assert ok.status_code == 200
    out = ok.json()
    assert out["html"] == "<stamp _stamp.html match>" and "evaluator_error" not in out["result"]
    assert calls[-1][:2] == ("4897.00", "USD") and calls[-1][3] is None  # landed today: a prediction, no label

    replay = client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "10", "landed_on": "2024-01-01"})
    assert replay.status_code == 200
    assert calls[-1] == ("10", "USD", "2024-01-01", "REPLAY — known outcome")

    rows = db.receipts(pid)
    assert len(rows) == 2
    by_date = {r["landed_on"]: r for r in rows}
    assert by_date["2024-01-01"]["label"] == "REPLAY — known outcome"
    assert by_date[max(by_date)]["consent_public"] == 1 and by_date[max(by_date)]["quoted"] == "4897.00"


# --- verify cache ---------------------------------------------------------------------------------------------
def test_refresh_verify_reuses_fresh_cache(monkeypatch):
    def nope(plans):
        raise AssertionError("verify_rows must not run while the cache is fresh")

    monkeypatch.setattr(view, "verify_rows", nope)
    monkeypatch.setitem(appmod._verify_cache, "at", time.time())
    monkeypatch.setitem(appmod._verify_cache, "rows", [])
    monkeypatch.setitem(appmod._verify_cache, "source", "cached")
    appmod._refresh_verify()
    assert appmod._verify_cache["source"] == "cached"


def test_refresh_verify_rebuilds_when_stale_or_empty(client, monkeypatch):
    seen = []
    monkeypatch.setattr(view, "verify_rows", lambda plans: (seen.append(plans) or [], "mcp"))
    monkeypatch.setitem(appmod._verify_cache, "at", 0.0)
    monkeypatch.setitem(appmod._verify_cache, "rows", None)
    r = client.get("/verify")
    assert r.status_code == 200 and len(seen) == 1
    assert appmod._verify_cache["source"] == "mcp"
    client.get("/verify")
    assert len(seen) == 1  # fresh now: second read served from cache
    monkeypatch.setitem(appmod._verify_cache, "at", time.time() - 120)
    client.get("/verify")
    assert len(seen) == 2


# --- small pages ----------------------------------------------------------------------------------------------
def test_missing_plan_pages_and_static_pages(client):
    assert client.get("/plan/01NOSUCHPLAN").status_code == 404
    assert client.get("/api/plan/01NOSUCHPLAN").status_code == 404
    assert client.get("/rules").status_code == 200
    assert client.get("/rules.csv").headers["content-type"].startswith("text/csv")
    assert client.get("/judge").status_code == 200
    r = client.get("/healthz")
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"


def test_api_plan_get_hides_raw_recovery_errors(client):
    pid = _plan(client)
    out = client.get(f"/api/plan/{pid}").json()
    assert out["plan_id"] == pid and all("error" not in r for r in out["recovery"])


def test_grouped_filter_formats_numbers_and_passes_sentinels():
    f = appmod.TEMPLATES.env.filters["grouped"]
    assert f("1234567.5") == "1,234,567.5"
    assert f("UNCLEAR") == "UNCLEAR" and f(None) is None and f("") == ""
    assert appmod.TEMPLATES.env.filters["sentence"]("abc") == "Abc"
    assert appmod.TEMPLATES.env.filters["sentence"]("") == ""
    assert appmod.TEMPLATES.env.filters["clip"](None, 5) == ""
