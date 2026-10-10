"""ECB daily reference rates via Frankfurter's ECB-only provider route (the default route blends 100+ sources).

Every successful quote is written to a snapshot file, so when the live call fails the planner can fall back to the
last ECB rate it actually fetched, shown with its own as_of date and a "stale" stamp. No snapshot means UNCLEAR.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import httpx

from . import config

ECB_CURRENCIES = {"IDR", "INR", "PHP"}  # ECB publishes these; not VND or NGN
_lock = threading.Lock()
SNAPSHOT = config.DB_PATH.parent / "fx_snapshot.json"


class FxUnavailable(RuntimeError):
    pass


def live(quote: str, timeout: float = 5.0) -> dict:
    if quote not in ECB_CURRENCIES:
        raise FxUnavailable(f"ECB does not publish a USD/{quote} reference rate")
    r = httpx.get(f"{config.FX_BASE_URL}/rate/usd/{quote.lower()}", timeout=timeout)
    r.raise_for_status()
    body = r.json()
    out = {"base": "USD", "quote": quote, "rate": str(body["rate"]), "as_of": body["date"],
           "source": "ECB reference rate via api.frankfurter.dev/v2/providers/ecb", "stale": False,
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _save(out)
    return out


def cached(quote: str) -> dict | None:
    try:
        snap = json.loads(SNAPSHOT.read_text())
    except (OSError, ValueError):
        return None
    hit = snap.get(quote)
    if not hit:
        return None
    return {**hit, "stale": True, "source": hit["source"] + " (last fetched snapshot)"}


def _save(entry: dict) -> None:
    with _lock:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        try:
            snap = json.loads(SNAPSHOT.read_text())
        except (OSError, ValueError):
            snap = {}
        snap[entry["quote"]] = entry
        SNAPSHOT.write_text(json.dumps(snap, indent=1))
