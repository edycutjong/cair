"""FastAPI app. neatlogs is initialised once in the lifespan and flushed once at shutdown (long-running host)."""
from __future__ import annotations

from contextlib import asynccontextmanager

import neatlogs
from fastapi import FastAPI

from . import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    neatlogs.init(api_key=config.NEATLOGS_API_KEY, endpoint=config.NEATLOGS_ENDPOINT, workflow_name="payout-plan",
                  tags=["prod"])
    yield
    neatlogs.flush()
    neatlogs.shutdown()


app = FastAPI(title="Cair", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
