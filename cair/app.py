"""FastAPI app. neatlogs is initialised once in the lifespan and flushed once at shutdown (long-running host)."""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import markdown
import neatlogs
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from ulid import ULID

from . import config, db, neat, planner, reconcile, rules, tools, view

TEMPLATES = Jinja2Templates(directory=str(config.ROOT / "cair" / "templates"))
TEMPLATES.env.filters["sentence"] = lambda s: (s[:1].upper() + s[1:]) if s else s
TEMPLATES.env.filters["clip"] = lambda s, n: tools.clip(s or "", n)
TEMPLATES.env.filters["grouped"] = lambda x: f"{Decimal(str(x)):,}" if x not in (None, "", "UNCLEAR") else x


@asynccontextmanager
async def lifespan(app: FastAPI):
    owned = True
    try:
        neatlogs.init(api_key=config.NEATLOGS_API_KEY, endpoint=config.NEATLOGS_ENDPOINT, workflow_name="payout-plan",
                      tags=["prod"])
    except neatlogs.NeatlogsConfigurationError:  # already initialised by the host process (tests)
        owned = False
    db.init()
    yield
    if owned:
        neatlogs.flush()
        neatlogs.shutdown()


app = FastAPI(title="Cair", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(config.ROOT / "cair" / "static")), name="static")

# --- per-IP rate limits: /api/plan fronts a paid LLM key -------------------------------------------------------
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
# largest receipt accepted per currency (about USD 10M each): a sanity bound, not a business rule
MAX_RECEIPT = {"USD": Decimal(10_000_000), "IDR": Decimal(200_000_000_000), "INR": Decimal(1_000_000_000),
               "PHP": Decimal(600_000_000)}
LIMITS = {"plan": (20, 600), "write": (60, 600), "plan_global": (600, 86400)}
_hits_lock = threading.Lock()


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers --forwarded-allow-ips 127.0.0.1, and Caddy replaces any X-Forwarded-For sent
    # by an untrusted client, so request.client.host is the real client. Never read X-Forwarded-For ourselves.
    return request.client.host if request.client else "?"


def _over(key: tuple[str, str], n: int, window: int) -> bool:
    q = _hits[key]
    now = time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= n:
        return True
    q.append(now)
    return False


def limited(request: Request, bucket: str) -> bool:
    with _hits_lock:
        if len(_hits) > 50_000:  # evict idle keys so the table cannot grow without bound
            for k in [k for k, q in _hits.items() if not q or time.time() - q[-1] > 86400]:
                del _hits[k]
        if _over((client_ip(request), bucket), *LIMITS[bucket]):
            return True  # rejected per address first, so one address cannot burn the global budget
        # a daily ceiling on paid LLM calls, whatever the source address
        return bucket == "plan" and _over(("*", "plan_global"), *LIMITS["plan_global"])


# --- identity: one browser visit = one neatlogs session; the end-user id is a random cookie, stored hashed -----------
# Cookies are HMAC-signed, so origin (builder / ethjkt / external) cannot be set by hand.
ORIGINS = {"builder", "ethjkt", "external"}


def _sign(v: str) -> str:
    return v + "." + hmac.new(config.COOKIE_SECRET.encode(), v.encode(), hashlib.sha256).hexdigest()[:20]


def _unsign(raw: str | None) -> str | None:
    if not raw or "." not in raw:
        return None
    v, _, mac = raw.rpartition(".")
    return v if hmac.compare_digest(_sign(v), raw) else None


def identity(request: Request) -> tuple[str, str, str, dict]:
    sid = _unsign(request.cookies.get("cair_sid")) or str(ULID())
    uid = _unsign(request.cookies.get("cair_uid")) or str(ULID())
    origin = _unsign(request.cookies.get("cair_origin"))
    origin = origin if origin in ORIGINS else "external"
    return sid, hashlib.sha256(uid.encode()).hexdigest()[:16], origin, {"cair_sid": sid, "cair_uid": uid}


def set_cookies(resp, cookies: dict) -> None:
    for k, v in cookies.items():
        resp.set_cookie(k, _sign(v), max_age=None if k == "cair_sid" else 60 * 60 * 24 * 365, httponly=True, samesite="lax",
                        secure=config.SECURE_COOKIES)


# --- pages -------------------------------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, src: str | None = None, b: str | None = None):
    resp = TEMPLATES.TemplateResponse(request, "index.html", {"form": view.form_options(), "card": None})
    _, _, _, cookies = identity(request)
    if src == "ethjkt":
        cookies["cair_origin"] = "ethjkt"
    if b and config.BUILDER_TOKEN and b == config.BUILDER_TOKEN:
        cookies["cair_origin"] = "builder"
    set_cookies(resp, cookies)
    return resp


@app.get("/plan/{plan_id}", response_class=HTMLResponse)
def plan_page(request: Request, plan_id: str):
    row = db.get_plan(plan_id)
    if not row:
        raise HTTPException(404, "no such plan")
    card = json.loads(row["card_json"])
    return TEMPLATES.TemplateResponse(request, "index.html", {
        "form": view.form_options(card), "card": view.card_view(card, db.confirms(plan_id), db.receipts(plan_id))})


@app.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request):
    sheet = rules.sheet()
    return TEMPLATES.TemplateResponse(request, "rules.html", {"rows": view.rules_rows(sheet), "version": sheet.version})


@app.get("/rules.csv")
def rules_csv():
    return HTMLResponse((config.DATA / "rules_sheet.csv").read_text(), media_type="text/csv")


@app.get("/judge", response_class=HTMLResponse)
def judge(request: Request):
    """For the judge: claim, 30-second path, receipts, honest limits. Rendered from JUDGE.md; no login, no cookie."""
    body = markdown.markdown((config.ROOT / "JUDGE.md").read_text(), extensions=["tables"])
    return TEMPLATES.TemplateResponse(request, "judge.html", {"body": body})


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "rules_version": rules.sheet().version}


# --- the agent -------------------------------------------------------------------------------------------------------
@app.post("/api/plan")
async def api_plan(request: Request):
    try:
        inp = view.validate(await _json_dict(request))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 400)
    if limited(request, "plan"):  # counted after validation: only requests that reach the LLM use the budget
        return JSONResponse({"error": "Too many plans from this address — try again in a few minutes."}, 429)
    sid, uhash, origin, cookies = identity(request)
    plan_id = str(ULID())
    result = await run_in_threadpool(
        planner.run, plan_id=plan_id, payer=inp["payer"], country=inp["country"], amount_usd=inp["amount"],
        rails_offered=inp["rails"], exchange=inp["exchange"], question=inp["question"], origin=origin,
        session_id=sid, end_user_id=uhash)
    card = result["card"]
    db.save_plan(card, sid, uhash, origin, rules.sheet().version)
    html = TEMPLATES.get_template("_card.html").render(card=view.card_view(card, [], []))
    resp = JSONResponse({"plan_id": plan_id, "html": html, "trace_id": card.get("trace_id")})
    set_cookies(resp, cookies)
    return resp


async def _json_dict(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


@app.get("/api/plan/{plan_id}")
def api_plan_get(plan_id: str):
    row = db.get_plan(plan_id)
    if not row:
        raise HTTPException(404, "no such plan")
    card = json.loads(row["card_json"])
    out = {k: card.get(k) for k in ("plan_id", "payer", "country", "amount", "unit", "rails", "recommended", "w8ben",
                                    "withholding", "fx", "landed", "unclear", "explanation", "guardrail", "trace_id")}
    out["recovery"] = [{k: v for k, v in r.items() if k != "error"} for r in card.get("recovery", [])]  # no raw errors
    return out


@app.post("/api/plan/{plan_id}/confirm")
async def api_confirm(request: Request, plan_id: str):
    """Human-in-the-loop: the user confirms one line before copying it. The server (never the browser) writes the
    confirm span into the plan's neatlogs session over HTTP /v1/trace."""
    if limited(request, "write"):
        return JSONResponse({"error": "rate limited"}, 429)
    row = db.get_plan(plan_id)
    if not row:
        raise HTTPException(404, "no such plan")
    body = await _json_dict(request)
    line = str(body.get("line", ""))
    card = json.loads(row["card_json"])
    value = view.confirmable(card).get(line)
    if value is None:
        return JSONResponse({"error": "unknown line"}, 400)
    trace = {"name": "human-confirm", "input": json.dumps({"plan_id": plan_id, "line": line}),
             "output": json.dumps({"confirmed": line, "value": value}),
             "attributes": {"neatlogs.session.id": row["session_id"], "neatlogs.end_user.id": row["end_user_hash"]},
             "children": [{"name": f"confirm:{line}", "kind": "TASK", "input": value,
                           "output": "confirmed by the user before copying it into the form"}]}
    try:
        posted = await run_in_threadpool(neat.post_trace, trace)
        tid = posted.get("trace_id")
    except Exception:
        tid = None  # the confirm is still recorded locally; tracing is best-effort here
    db.save_confirm(plan_id, line, tid)
    return {"ok": True, "line": line, "trace_id": tid}


@app.post("/api/receipt")
async def api_receipt(request: Request):
    if limited(request, "write"):
        return JSONResponse({"error": "rate limited"}, 429)
    body = await _json_dict(request)
    row = db.get_plan(str(body.get("plan_id", "")))
    if not row:
        return JSONResponse({"error": "no such plan"}, 404)
    currency = str(body.get("currency", "USD")).upper()
    if currency not in MAX_RECEIPT:
        return JSONResponse({"error": "unsupported currency"}, 400)
    try:
        amount = Decimal(str(body.get("landed_amount", "")).replace(",", ""))
        if not amount.is_finite() or amount <= 0 or amount > MAX_RECEIPT[currency]:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return JSONResponse({"error": "Enter the amount that landed, e.g. 4897.00"}, 400)
    try:
        landed = date.fromisoformat(str(body.get("landed_on") or date.today().isoformat()))
    except ValueError:
        return JSONResponse({"error": "date must be YYYY-MM-DD"}, 400)
    if landed > date.today() + timedelta(days=1) or landed.year < 2020:
        return JSONResponse({"error": "that date is not possible for a received payment"}, 400)
    landed_on = landed.isoformat()
    card = json.loads(row["card_json"])
    replay = landed_on < row["created_at"][:10]  # money landed before the plan existed: a replay, not a prediction
    label = "REPLAY — known outcome" if replay else None
    result = await run_in_threadpool(reconcile.reconcile, card, str(amount), currency, landed_on, label,
                                     row["session_id"], row["end_user_hash"])
    db.save_receipt({"id": str(ULID()), "plan_id": row["id"], "rail": card.get("recommended") or "?",
                     "landed_amount": str(amount), "landed_currency": currency, "landed_on": landed_on,
                     "mode": result["mode"], "quoted": result.get("quoted") or result.get("quoted_upper"),
                     "error_pct": result.get("error_pct"), "unexplained": result.get("unexplained_usd"),
                     "verdict": result["verdict"], "label": label, "evaluator_trace_id": result.get("evaluator_trace_id"),
                     "consent_public": int(bool(body.get("consent_public")))})
    html = TEMPLATES.get_template("_stamp.html").render(r=view.stamp_view(result))
    result.pop("evaluator_error", None)  # logged in the trace attempt, not returned to the browser
    return {"result": result, "html": html}


# --- judges: read-back from neatlogs, redacted -------------------------------------------------------------------
_verify_cache: dict = {"at": 0.0, "rows": None, "source": ""}
_verify_lock = threading.Lock()


def _refresh_verify() -> None:
    with _verify_lock:  # one MCP read-back at a time; concurrent requests reuse its result
        if time.time() - _verify_cache["at"] > 60 or _verify_cache["rows"] is None:
            rows, source = view.verify_rows(db.recent_plans(20))
            _verify_cache.update(at=time.time(), rows=rows, source=source)


@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request):
    if time.time() - _verify_cache["at"] > 60 or _verify_cache["rows"] is None:
        await run_in_threadpool(_refresh_verify)
    return TEMPLATES.TemplateResponse(request, "verify.html", {
        "rows": _verify_cache["rows"], "source": _verify_cache["source"], "counts": db.counts(),
        "read_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(_verify_cache["at"]))})

