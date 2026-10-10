"""Line + branch coverage for cair/neat.py: /v1/trace write-back, MCP session driving and result decoding. No network."""
import asyncio
import sys
import types
from types import SimpleNamespace

import httpx
import pytest

from cair import config, neat

# ---------- post_trace ----------

class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload, self.error = payload, error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


@pytest.fixture
def post(monkeypatch):
    calls = []

    def install(resp):
        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return resp
        monkeypatch.setattr(neat.httpx, "post", fake_post)
        return calls
    return install


def test_post_trace_sends_bearer_write_key_and_project(post, monkeypatch):
    monkeypatch.setattr(config, "NEATLOGS_ENDPOINT", "https://ingest.example")
    monkeypatch.setattr(config, "NEATLOGS_WRITE_KEY", "nlw_secret")
    monkeypatch.setattr(config, "NEATLOGS_PROJECT", "proj-x")
    calls = post(FakeResponse({"id": "t1"}))
    out = neat.post_trace({"name": "run", "spans": [1]})
    assert out == {"id": "t1"}
    (url, kw), = calls
    assert url == "https://ingest.example/v1/trace"
    assert kw["json"] == {"project": "proj-x", "name": "run", "spans": [1]}
    assert kw["headers"] == {"Authorization": "Bearer nlw_secret"}
    assert kw["timeout"] == 15.0


def test_post_trace_trace_can_override_project_and_timeout(post, monkeypatch):
    monkeypatch.setattr(config, "NEATLOGS_PROJECT", "proj-x")
    calls = post(FakeResponse({}))
    neat.post_trace({"project": "other"}, timeout=3.0)
    assert calls[0][1]["json"]["project"] == "other"
    assert calls[0][1]["timeout"] == 3.0


def test_post_trace_raises_on_http_error(post):
    post(FakeResponse(error=httpx.HTTPStatusError("401", request=None, response=None)))
    with pytest.raises(httpx.HTTPStatusError):
        neat.post_trace({"name": "x"})


# ---------- _content ----------

def test_content_prefers_structured_content():
    res = SimpleNamespace(structured_content={"a": 1}, content=[SimpleNamespace(type="text", text="[2]")])
    assert neat._content(res) == {"a": 1}


def test_content_parses_json_text_blocks_and_skips_non_text():
    res = SimpleNamespace(structured_content=None, content=[
        SimpleNamespace(type="image", text="IGNORED"),
        SimpleNamespace(type="text", text='{"x":'),
        SimpleNamespace(type="text", text="1}"),
    ])
    assert neat._content(res) == {"x": 1}


def test_content_returns_plain_text_when_not_json():
    res = SimpleNamespace(content=[SimpleNamespace(type="text", text="hello"),
                                   SimpleNamespace(type="text", text="world")])
    assert neat._content(res) == "hello\nworld"


def test_content_empty_returns_empty_string():
    assert neat._content(SimpleNamespace(structured_content={}, content=[])) == ""


def test_content_block_without_type_is_ignored():
    res = SimpleNamespace(structured_content=None, content=[SimpleNamespace(text="nope")])
    assert neat._content(res) == ""


# ---------- _mcp_call ----------

@pytest.fixture
def fake_mcp(monkeypatch):
    """Install fake httpx2 / mcp modules and record how the session is driven."""
    rec = SimpleNamespace(client_kwargs=None, url=None, http=None, calls=[], initialized=False, results={})

    class Timeout:
        def __init__(self, *a, **kw):
            self.args, self.kw = a, kw

    class AsyncClient:
        def __init__(self, **kw):
            rec.client_kwargs = kw

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class Stream:
        def __init__(self, url, http_client):
            rec.url, rec.http = url, http_client

        async def __aenter__(self):
            return ("R", "W")

        async def __aexit__(self, *exc):
            return False

    class ClientSession:
        def __init__(self, read, write):
            assert (read, write) == ("R", "W")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            rec.initialized = True

        async def list_tools(self):
            tool = SimpleNamespace(input_schema={"type": "object"})
            tool.name = "get_traces"
            return SimpleNamespace(tools=[tool])

        async def call_tool(self, name, args):
            rec.calls.append((name, args))
            return rec.results[name]

    httpx2 = types.ModuleType("httpx2")
    httpx2.AsyncClient, httpx2.Timeout = AsyncClient, Timeout
    mcp = types.ModuleType("mcp")
    mcp.ClientSession = ClientSession
    client = types.ModuleType("mcp.client")
    sh = types.ModuleType("mcp.client.streamable_http")
    sh.streamable_http_client = Stream
    for name, mod in [("httpx2", httpx2), ("mcp", mcp), ("mcp.client", client), ("mcp.client.streamable_http", sh)]:
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(config, "NEATLOGS_API_KEY", "nl_key")
    monkeypatch.setattr(config, "NEATLOGS_MCP_URL", "https://mcp.example/mcp")
    return rec


def test_mcp_call_lists_tools_and_calls_tools_in_order(fake_mcp):
    fake_mcp.results = {
        "get_traces": SimpleNamespace(structured_content={"traces": [1]}, content=[]),
        "echo": SimpleNamespace(structured_content=None, content=[SimpleNamespace(type="text", text="plain")]),
    }
    out = asyncio.run(neat._mcp_call([("__list_tools__", {}), ("get_traces", {"limit": 2}), ("echo", {})]))
    assert out == [[{"name": "get_traces", "schema": {"type": "object"}}], {"traces": [1]}, "plain"]
    assert fake_mcp.calls == [("get_traces", {"limit": 2}), ("echo", {})]
    assert fake_mcp.initialized
    assert fake_mcp.url == "https://mcp.example/mcp"
    assert fake_mcp.client_kwargs["headers"] == {"Authorization": "Bearer nl_key"}
    assert fake_mcp.http is not None


def test_mcp_call_no_calls_returns_empty_list_but_initializes(fake_mcp):
    assert asyncio.run(neat._mcp_call([])) == []
    assert fake_mcp.initialized and fake_mcp.calls == []


# ---------- mcp (sync wrapper) ----------

def test_mcp_wrapper_runs_calls_synchronously(monkeypatch):
    seen = []

    async def fake_call(calls):
        seen.append(calls)
        return ["ok"]
    monkeypatch.setattr(neat, "_mcp_call", fake_call)
    assert neat.mcp([("t", {"a": 1})]) == ["ok"]
    assert seen == [[("t", {"a": 1})]]


def test_mcp_wrapper_times_out(monkeypatch):
    async def slow(calls):
        await asyncio.sleep(5)
    monkeypatch.setattr(neat, "_mcp_call", slow)
    with pytest.raises(asyncio.TimeoutError):
        neat.mcp([], timeout=0.01)
