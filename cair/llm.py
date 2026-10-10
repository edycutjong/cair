"""The one LLM client. Built once, wrapped by neatlogs so every call is an LLM span (model, tokens, latency)."""
from __future__ import annotations

from functools import lru_cache

import neatlogs
from openai import OpenAI

from . import config


@lru_cache(maxsize=1)
def client() -> OpenAI:
    raw = OpenAI(api_key=config.LLM_API_KEY or "missing", base_url=config.LLM_BASE_URL or None, timeout=60, max_retries=0)
    # Static values only: wrap() kwargs land on the trace root as neatlogs.workflow.* attributes.
    return neatlogs.wrap(raw, surface="cair", provider="qwen-cloud")


def chat(messages: list[dict], temperature: float = 0.0, max_tokens: int = 900) -> str:
    resp = client().chat.completions.create(
        model=config.LLM_MODEL, messages=messages, temperature=temperature, max_tokens=max_tokens
    )
    return resp.choices[0].message.content or ""
