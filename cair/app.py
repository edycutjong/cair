"""FastAPI app. neatlogs is initialised once in the lifespan and flushed once at shutdown (long-running host)."""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, InvalidOperation

import neatlogs
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from ulid import ULID

from . import config, db, neat, planner, reconcile, rules, view

TEMPLATES = Jinja2Templates(directory=str(config.ROOT / "cair" / "templates"))
TEMPLATES.env.filters["sentence"] = lambda s: (s[:1].upper() + s[1:]) if s else s


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
LIMITS = {"plan": (12, 600), "write": (60, 600)}


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def limited(request: Request, bucket: str) -> bool:
    n, window = LIMITS[bucket]
    q = _hits[(client_ip(request), bucket)]
    now = time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= n:
        return True
    q.append(now)
    return False


# --- identity: one browser visit = one neatlogs session; the end-user id is a random cookie, stored hashed -----------
def identity(request: Request) -> tuple[str, str, str, dict]:
    cookies = {}
    sid = request.cookies.get("cair_sid") or str(ULID())
    uid = request.cookies.get("cair_uid") or str(ULID())
    origin = request.cookies.get("cair_origin") or "external"
    cookies.update({"cair_sid": sid, "cair_uid": uid})
    return sid, hashlib.sha256(uid.encode()).hexdigest()[:16], origin, cookies


def set_cookies(resp, cookies: dict) -> None:
    for k, v in cookies.items():
        resp.set_cookie(k, v, max_age=None if k == "cair_sid" else 60 * 60 * 24 * 365, httponly=True, samesite="lax",
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


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "rules_version": rules.sheet().version}


# --- the agent -------------------------------------------------------------------------------------------------------
@app.post("/api/plan")
async def api_plan(request: Request):
    if limited(request, "plan"):
        return JSONResponse({"error": "Too many plans from this address — try again in a few minutes."}, 429)
    body = await request.json()
    try:
        inp = view.validate(body)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 400)
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


@app.get("/api/plan/{plan_id}")
def api_plan_get(plan_id: str):
    row = db.get_plan(plan_id)
    if not row:
        raise HTTPException(404, "no such plan")
    card = json.loads(row["card_json"])
    return {k: card.get(k) for k in ("plan_id", "payer", "country", "amount", "unit", "rails", "recommended", "w8ben",
                                     "withholding", "fx", "landed", "unclear", "explanation", "guardrail", "recovery",
                                     "trace_id")}


@app.post("/api/plan/{plan_id}/confirm")
async def api_confirm(request: Request, plan_id: str):
    """Human-in-the-loop: the user confirms one line before copying it. The server (never the browser) writes the
    confirm span into the plan's neatlogs session over HTTP /v1/trace."""
    if limited(request, "write"):
        return JSONResponse({"error": "rate limited"}, 429)
    row = db.get_plan(plan_id)
    if not row:
        raise HTTPException(404, "no such plan")
    body = await request.json()
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
    body = await request.json()
    row = db.get_plan(str(body.get("plan_id", "")))
    if not row:
        return JSONResponse({"error": "no such plan"}, 404)
    try:
        amount = Decimal(str(body.get("landed_amount", "")).replace(",", ""))
        if amount <= 0 or amount > Decimal(10_000_000):
            raise InvalidOperation
    except InvalidOperation:
        return JSONResponse({"error": "Enter the amount that landed, e.g. 4897.00"}, 400)
    currency = str(body.get("currency", "USD")).upper()
    if currency not in {"USD", "IDR", "INR", "PHP"}:
        return JSONResponse({"error": "unsupported currency"}, 400)
    landed_on = str(body.get("landed_on") or date.today().isoformat())
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", landed_on):
        return JSONResponse({"error": "date must be YYYY-MM-DD"}, 400)
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
    return {"result": result, "html": html}


# --- judges: read-back from neatlogs, redacted -------------------------------------------------------------------
_verify_cache: dict = {"at": 0.0, "rows": None, "source": ""}


@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request):
    if time.time() - _verify_cache["at"] > 60 or _verify_cache["rows"] is None:
        rows, source = await run_in_threadpool(view.verify_rows, db.recent_plans(20))
        _verify_cache.update(at=time.time(), rows=rows, source=source)
    return TEMPLATES.TemplateResponse(request, "verify.html", {
        "rows": _verify_cache["rows"], "source": _verify_cache["source"], "counts": db.counts(),
        "read_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(_verify_cache["at"]))})

