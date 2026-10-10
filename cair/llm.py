"""The one LLM client. Built once, wrapped by neatlogs so every call is an LLM span (model, tokens, latency)."""
from __future__ import annotations

import contextvars
from functools import lru_cache

import neatlogs
from openai import OpenAI

from . import config


@lru_cache(maxsize=1)
def client() -> OpenAI:
    raw = OpenAI(api_key=config.LLM_API_KEY or "missing", base_url=config.LLM_BASE_URL or None, timeout=90, max_retries=0)
    # Static values only: wrap() kwargs land on the trace root as neatlogs.workflow.* attributes.
    return neatlogs.wrap(raw, surface="cair", provider="qwen-cloud")


# Token usage of every call made inside one plan (the planner resets it per plan; bench.py reads it).
USAGE: contextvars.ContextVar[list | None] = contextvars.ContextVar("cair_llm_usage", default=None)

# Qwen's reasoning mode is off for every planner (v1, v2, ablation): same model, same parameters.
EXTRA_BODY = {"enable_thinking": False}


def chat(messages: list[dict], temperature: float = 0.0, max_tokens: int = 2000) -> str:
    resp = client().chat.completions.create(
        model=config.LLM_MODEL, messages=messages, temperature=temperature, max_tokens=max_tokens,  # type: ignore[arg-type]  # plain role/content dicts
        extra_body=EXTRA_BODY,
    )
    acc = USAGE.get()
    if acc is not None and resp.usage:
        acc.append({"prompt": resp.usage.prompt_tokens, "completion": resp.usage.completion_tokens})
    return resp.choices[0].message.content or ""
