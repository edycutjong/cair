"""Line + branch coverage for cair/llm.py: client construction, the chat() call contract and token-usage accounting."""
from types import SimpleNamespace

import pytest

from cair import config, llm


class FakeCompletions:
    def __init__(self, resp=None, error=None):
        self.resp, self.error, self.calls = resp, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.resp


def make_resp(content="hello", usage=(11, 7)):
    msg = SimpleNamespace(content=content)
    u = SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]) if usage else None
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=u)


@pytest.fixture
def fake(monkeypatch):
    """Patch llm.client() so chat() talks to a recorder, never the network."""
    def install(resp=None, error=None):
        comps = FakeCompletions(resp, error)
        monkeypatch.setattr(llm, "client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=comps)))
        return comps
    return install


@pytest.fixture
def fresh_client():
    llm.client.cache_clear()
    yield
    llm.client.cache_clear()


def test_client_builds_openai_and_wraps_with_neatlogs(monkeypatch, fresh_client):
    seen = {}

    class FakeOpenAI:
        def __init__(self, **kw):
            seen["openai"] = kw

    def fake_wrap(raw, **kw):
        seen["wrap"] = (raw, kw)
        return "wrapped"

    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(llm.neatlogs, "wrap", fake_wrap)
    monkeypatch.setattr(config, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://qwen.example/v1")

    assert llm.client() == "wrapped"
    assert seen["openai"] == {"api_key": "sk-test", "base_url": "https://qwen.example/v1", "timeout": 90, "max_retries": 0}
    raw, kw = seen["wrap"]
    assert isinstance(raw, FakeOpenAI)
    assert kw == {"surface": "cair", "provider": "qwen-cloud"}


def test_client_falls_back_when_key_and_base_url_unset(monkeypatch, fresh_client):
    seen = {}
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: seen.update(kw) or "raw")
    monkeypatch.setattr(llm.neatlogs, "wrap", lambda raw, **kw: raw)
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "LLM_BASE_URL", "")

    assert llm.client() == "raw"
    assert seen["api_key"] == "missing"
    assert seen["base_url"] is None


def test_client_is_cached(monkeypatch, fresh_client):
    built = []
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: built.append(kw) or "raw")
    monkeypatch.setattr(llm.neatlogs, "wrap", lambda raw, **kw: raw)
    assert llm.client() is llm.client()
    assert len(built) == 1


def test_chat_sends_model_params_and_thinking_off(fake, monkeypatch):
    comps = fake(make_resp("answer"))
    monkeypatch.setattr(config, "LLM_MODEL", "qwen-test")
    msgs = [{"role": "user", "content": "hi"}]

    assert llm.chat(msgs) == "answer"
    (call,) = comps.calls
    assert call == {"model": "qwen-test", "messages": msgs, "temperature": 0.0, "max_tokens": 2000,
                    "extra_body": {"enable_thinking": False}}


def test_chat_passes_custom_temperature_and_max_tokens(fake):
    comps = fake(make_resp("x"))
    llm.chat([{"role": "user", "content": "hi"}], temperature=0.7, max_tokens=50)
    assert comps.calls[0]["temperature"] == 0.7
    assert comps.calls[0]["max_tokens"] == 50


def test_chat_returns_empty_string_for_none_content(fake):
    fake(make_resp(content=None))
    assert llm.chat([]) == ""


def test_chat_without_accumulator_does_not_track_usage(fake):
    fake(make_resp(usage=(5, 3)))
    assert llm.USAGE.get() is None
    assert llm.chat([]) == "hello"
    assert llm.USAGE.get() is None


def test_chat_appends_usage_to_accumulator(fake):
    fake(make_resp(usage=(11, 7)))
    acc: list = []
    token = llm.USAGE.set(acc)
    try:
        llm.chat([])
        llm.chat([])
    finally:
        llm.USAGE.reset(token)
    assert acc == [{"prompt": 11, "completion": 7}, {"prompt": 11, "completion": 7}]


def test_chat_skips_usage_when_response_has_none(fake):
    fake(make_resp(usage=None))
    acc: list = []
    token = llm.USAGE.set(acc)
    try:
        assert llm.chat([]) == "hello"
    finally:
        llm.USAGE.reset(token)
    assert acc == []


def test_chat_propagates_provider_errors(fake):
    fake(error=RuntimeError("qwen down"))
    with pytest.raises(RuntimeError, match="qwen down"):
        llm.chat([])
