"""Runtime configuration. Secrets come from the environment only (systemd EnvironmentFile on the host,
`CAIR_ENV_FILES` locally); nothing secret is ever read from or written to this repository."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_env_files() -> None:
    """Load KEY=VALUE lines from the files named in CAIR_ENV_FILES (colon-separated). Existing env wins."""
    for raw in os.environ.get("CAIR_ENV_FILES", "").split(":"):
        path = Path(raw).expanduser()
        if not raw or not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_files()

NEATLOGS_API_KEY = os.environ.get("NEATLOGS_API_KEY", "")
NEATLOGS_WRITE_KEY = os.environ.get("NEATLOGS_WRITE_KEY", "")
NEATLOGS_ENDPOINT = os.environ.get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com").rstrip("/")
NEATLOGS_PROJECT = os.environ.get("NEATLOGS_PROJECT", "cair")
NEATLOGS_MCP_URL = os.environ.get("NEATLOGS_MCP_URL", f"{NEATLOGS_ENDPOINT}/mcp")

LLM_API_KEY = os.environ.get("QWEN_API_KEY", "")
LLM_BASE_URL = os.environ.get("QWEN_BASE_URL", "")
LLM_MODEL = os.environ.get("QWEN_MODEL", "qwen-max")

DB_PATH = Path(os.environ.get("CAIR_DB", str(ROOT / "var" / "cair.db")))
FX_BASE_URL = os.environ.get("CAIR_FX_URL", "https://api.frankfurter.dev/v2/providers/ecb")
BUILDER_TOKEN = os.environ.get("CAIR_BUILDER_TOKEN", "")
