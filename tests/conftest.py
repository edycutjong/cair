import neatlogs
import pytest
from fastapi.testclient import TestClient

from cair import app as appmod
from cair import config, db, fx, llm, neat


@pytest.fixture(scope="session", autouse=True)
def _neatlogs_local():
    neatlogs.init(api_key="test", workflow_name="cair-tests", disable_export=True, register_shutdown_handlers=False)
    yield
    neatlogs.shutdown()


@pytest.fixture
def fixed_fx(monkeypatch, tmp_path):
    monkeypatch.setattr(fx, "SNAPSHOT", tmp_path / "fx_snapshot.json")

    def live(quote, timeout=5.0):
        out = {"base": "USD", "quote": quote, "rate": {"IDR": "17881", "INR": "96.73", "PHP": "62.821"}[quote],
               "as_of": "2026-10-09", "source": "ECB reference rate (test)", "stale": False}
        fx._save(out)
        return out

    monkeypatch.setattr(fx, "live", live)
    return live


@pytest.fixture
def llm_says(monkeypatch):
    """Make the explain call return fixed text (or raise) so planner tests never touch the network."""
    def setter(*texts, raises=None):
        seq = list(texts)

        def chat(messages, temperature=0.0, max_tokens=700):
            if raises:
                raise raises
            return seq.pop(0) if len(seq) > 1 else seq[0]

        monkeypatch.setattr(llm, "chat", chat)
    return setter


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
