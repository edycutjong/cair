"""SQLite store: plans, per-line confirms, receipts. No names, emails or tax ids are ever stored."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, end_user_hash TEXT NOT NULL,
  payer TEXT NOT NULL, country TEXT NOT NULL, amount_usd TEXT NOT NULL, rails_offered TEXT NOT NULL,
  exchange TEXT, origin TEXT NOT NULL CHECK (origin IN ('builder','eval','external','ethjkt')),
  planner TEXT NOT NULL, card_json TEXT NOT NULL, guardrail_ok INTEGER, trace_id TEXT,
  rules_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
CREATE TABLE IF NOT EXISTS confirms (
  plan_id TEXT NOT NULL REFERENCES plans(id), line_key TEXT NOT NULL, trace_id TEXT,
  confirmed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')), PRIMARY KEY (plan_id, line_key));
CREATE TABLE IF NOT EXISTS receipts (
  id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id), rail TEXT NOT NULL,
  landed_amount TEXT NOT NULL, landed_currency TEXT NOT NULL, landed_on TEXT NOT NULL, mode TEXT NOT NULL,
  quoted TEXT, error_pct TEXT, unexplained TEXT, verdict TEXT, label TEXT, evaluator_trace_id TEXT,
  consent_public INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
"""
_lock = threading.Lock()


@contextmanager
def conn():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with _lock, conn() as c:
        c.executescript(SCHEMA)


def save_plan(card: dict, session_id: str, end_user_hash: str, origin: str, rules_version: str) -> None:
    public = {k: v for k, v in card.items() if k != "tool_outputs"}
    guard = card.get("guardrail") or []
    with _lock, conn() as c:
        c.execute("INSERT INTO plans (id, session_id, end_user_hash, payer, country, amount_usd, rails_offered, exchange,"
                  " origin, planner, card_json, guardrail_ok, trace_id, rules_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (card["plan_id"], session_id, end_user_hash, card["payer"], card["country"], card["amount"],
                   json.dumps([r["rail"] for r in card["rails"]]), card.get("exchange"), origin, "v2",
                   json.dumps(public, ensure_ascii=False), int(bool(guard and guard[-1]["passed"])) if guard else None,
                   card.get("trace_id"), rules_version))


def get_plan(plan_id: str) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()


def recent_plans(limit: int = 20) -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM plans ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def save_confirm(plan_id: str, line_key: str, trace_id: str | None) -> None:
    with _lock, conn() as c:
        c.execute("INSERT OR REPLACE INTO confirms (plan_id, line_key, trace_id) VALUES (?,?,?)", (plan_id, line_key, trace_id))


def confirms(plan_id: str) -> list[str]:
    with conn() as c:
        return [r["line_key"] for r in c.execute("SELECT line_key FROM confirms WHERE plan_id = ?", (plan_id,))]


def save_receipt(row: dict) -> None:
    cols = ",".join(row)
    with _lock, conn() as c:
        c.execute(f"INSERT INTO receipts ({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))


def receipts(plan_id: str) -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM receipts WHERE plan_id = ? ORDER BY created_at", (plan_id,)).fetchall()


def counts() -> dict:
    with conn() as c:
        q = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
        return {"plans_external": q("SELECT COUNT(*) FROM plans WHERE origin IN ('external','ethjkt')"),
                "users_external": q("SELECT COUNT(DISTINCT end_user_hash) FROM plans WHERE origin IN ('external','ethjkt')"),
                "plans_all": q("SELECT COUNT(*) FROM plans"), "receipts": q("SELECT COUNT(*) FROM receipts")}
