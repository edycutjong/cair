"""Browser E2E: boots the real app (uvicorn) on a free port with no keys, then drives it with Playwright.

With no Qwen key the explanation falls back to the template and the product says so; the route, line 10 and every
amount are decided by code, so the card under test is the real one.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    env = {**os.environ, "CAIR_DB": str(Path(tempfile.mkdtemp()) / "e2e.db"), "CAIR_SECURE_COOKIES": "0",
           "NEATLOGS_API_KEY": "", "NEATLOGS_WRITE_KEY": "", "QWEN_API_KEY": "", "CAIR_ENV_FILES": ""}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "cair.app:app", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/healthz", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("the app did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)
