"""Line + branch coverage for cair/fx.py: the Frankfurter ECB call, the snapshot write-back and the stale fallback."""
import json
from datetime import date, timedelta

import httpx
import pytest

from cair import config, fx


@pytest.fixture
def snap(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "fx_snapshot.json"
    monkeypatch.setattr(fx, "SNAPSHOT", path)
    return path


class FakeResponse:
    def __init__(self, body=None, status=200):
        self._body, self.status = body, status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("boom", request=httpx.Request("GET", "http://x"),
                                        response=httpx.Response(self.status))

    def json(self):
        return self._body


def patch_get(monkeypatch, response):
    calls = []

    def get(url, timeout):
        calls.append((url, timeout))
        return response

    monkeypatch.setattr(fx.httpx, "get", get)
    return calls


def entry(quote="IDR", as_of=None, **over):
    as_of = as_of or date.today().isoformat()
    return {"base": "USD", "quote": quote, "rate": "17881", "as_of": as_of, "source": "ECB test", "stale": False, **over}


def test_live_rejects_non_ecb_currency_without_http(monkeypatch, snap):
    calls = patch_get(monkeypatch, FakeResponse({"rate": 1, "date": "2026-10-09"}))
    for quote in ("VND", "NGN", "idr"):
        with pytest.raises(fx.FxUnavailable, match=f"USD/{quote}"):
            fx.live(quote)
    assert calls == []
    assert not snap.exists()


def test_live_returns_quote_and_writes_snapshot(monkeypatch, snap):
    calls = patch_get(monkeypatch, FakeResponse({"rate": 96.73, "date": "2026-10-09"}))
    out = fx.live("INR", timeout=2.5)
    assert calls == [(f"{config.FX_BASE_URL}/rate/usd/inr", 2.5)]
    assert (out["base"], out["quote"], out["rate"], out["as_of"], out["stale"]) == ("USD", "INR", "96.73", "2026-10-09", False)
    assert "ECB reference rate" in out["source"]
    assert out["fetched_at"].endswith("+00:00")
    assert json.loads(snap.read_text()) == {"INR": out}


def test_live_default_timeout_is_five_seconds(monkeypatch, snap):
    calls = patch_get(monkeypatch, FakeResponse({"rate": "62.821", "date": "2026-10-09"}))
    assert fx.live("PHP")["rate"] == "62.821"
    assert calls[0][1] == 5.0


def test_live_http_error_propagates_and_leaves_no_snapshot(monkeypatch, snap):
    patch_get(monkeypatch, FakeResponse(status=503))
    with pytest.raises(httpx.HTTPStatusError):
        fx.live("IDR")
    assert not snap.exists()


def test_live_malformed_body_raises_keyerror_and_no_snapshot(monkeypatch, snap):
    patch_get(monkeypatch, FakeResponse({"date": "2026-10-09"}))
    with pytest.raises(KeyError):
        fx.live("IDR")
    assert not snap.exists()


def test_save_merges_quotes_and_overwrites_same_quote(snap):
    fx._save(entry("IDR", rate="1"))
    fx._save(entry("INR", rate="2"))
    fx._save(entry("IDR", rate="3"))
    data = json.loads(snap.read_text())
    assert {k: v["rate"] for k, v in data.items()} == {"IDR": "3", "INR": "2"}
    assert not snap.with_suffix(".tmp").exists()


@pytest.mark.parametrize("junk", ["{not json", ""])
def test_save_recovers_from_corrupt_snapshot(snap, junk):
    snap.parent.mkdir(parents=True)
    snap.write_text(junk)
    fx._save(entry("PHP"))
    assert list(json.loads(snap.read_text())) == ["PHP"]


def test_save_serialises_writers_with_the_module_lock(snap, monkeypatch):
    events = []

    class SpyLock:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, *exc):
            events.append("exit")

    monkeypatch.setattr(fx, "_lock", SpyLock())
    fx._save(entry())
    assert events == ["enter", "exit"]
    assert snap.exists()


def test_cached_missing_file_is_none(snap):
    assert fx.cached("IDR") is None


@pytest.mark.parametrize("junk", ["{broken", ""])
def test_cached_corrupt_file_is_none(snap, junk):
    snap.parent.mkdir(parents=True)
    snap.write_text(junk)
    assert fx.cached("IDR") is None


def test_cached_unknown_quote_is_none(snap):
    fx._save(entry("IDR"))
    assert fx.cached("INR") is None


def test_cached_empty_entry_is_none(snap):
    snap.parent.mkdir(parents=True)
    snap.write_text(json.dumps({"IDR": {}}))
    assert fx.cached("IDR") is None


def test_cached_fresh_snapshot_is_stamped_stale_with_source_suffix(snap):
    e = entry("IDR")
    fx._save(e)
    got = fx.cached("IDR")
    assert got == {**e, "stale": True, "source": "ECB test (last fetched snapshot)"}
    assert json.loads(snap.read_text())["IDR"]["stale"] is False  # the stored entry is not mutated


def test_cached_boundary_exactly_max_stale_days_is_usable(snap):
    fx._save(entry("IDR", as_of=(date.today() - timedelta(days=fx.MAX_STALE_DAYS)).isoformat()))
    assert fx.cached("IDR")["stale"] is True


def test_cached_older_than_max_stale_days_is_none(snap):
    fx._save(entry("IDR", as_of=(date.today() - timedelta(days=fx.MAX_STALE_DAYS + 1)).isoformat()))
    assert fx.cached("IDR") is None


def test_cached_entry_without_as_of_is_none(snap):
    e = entry("IDR")
    del e["as_of"]
    snap.parent.mkdir(parents=True)
    snap.write_text(json.dumps({"IDR": e}))
    assert fx.cached("IDR") is None


def test_cached_unparseable_as_of_is_none(snap):
    snap.parent.mkdir(parents=True)
    snap.write_text(json.dumps({"IDR": entry("IDR", as_of="yesterday")}))
    assert fx.cached("IDR") is None


def test_live_then_cached_roundtrip(monkeypatch, snap):
    patch_get(monkeypatch, FakeResponse({"rate": "17881", "date": date.today().isoformat()}))
    live = fx.live("IDR")
    got = fx.cached("IDR")
    assert got["rate"] == live["rate"] and got["stale"] is True
    assert got["source"] == live["source"] + " (last fetched snapshot)"
