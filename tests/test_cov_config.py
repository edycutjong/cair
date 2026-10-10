"""Line + branch coverage for cair/config.py: env-file loading and the environment-derived settings."""
import importlib.util
import os
from pathlib import Path
from unittest import mock

import pytest

from cair import config

CONFIG_PY = Path(config.__file__)

SETTINGS = ["NEATLOGS_API_KEY", "NEATLOGS_WRITE_KEY", "NEATLOGS_ENDPOINT", "NEATLOGS_PROJECT", "NEATLOGS_MCP_URL",
            "QWEN_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL", "CAIR_DB", "CAIR_FX_URL", "CAIR_BUILDER_TOKEN",
            "CAIR_SECURE_COOKIES", "CAIR_COOKIE_SECRET", "CAIR_ENV_FILES"]


@pytest.fixture
def clean_env():
    """A scrubbed environment, fully restored afterwards (load_env_files writes os.environ directly)."""
    with mock.patch.dict(os.environ):
        for k in SETTINGS:
            os.environ.pop(k, None)
        yield os.environ


def fresh_config(**env):
    """Execute cair/config.py as a throwaway module so the real `cair.config` (patched by other tests) is untouched."""
    os.environ.update(env)
    spec = importlib.util.spec_from_file_location("cair_config_fresh", CONFIG_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- load_env_files -------------------------------------------------------------------------------------------
def test_load_env_files_without_the_variable_loads_nothing(clean_env):
    before = dict(os.environ)
    config.load_env_files()
    assert dict(os.environ) == before


def test_load_env_files_parses_key_value_lines(clean_env, tmp_path):
    f = tmp_path / "a.env"
    f.write_text('\n# a comment\nnot a pair\n  FOO_CAIR = bar  \nQUOTED="double q"\nSINGLE=\'single q\'\n'
                 'EMPTY=\nURL=https://x.test/?a=b\n')
    clean_env["CAIR_ENV_FILES"] = str(f)
    config.load_env_files()
    assert os.environ["FOO_CAIR"] == "bar"                    # key and value stripped
    assert os.environ["QUOTED"] == "double q"                 # surrounding quotes removed
    assert os.environ["SINGLE"] == "single q"
    assert os.environ["EMPTY"] == ""
    assert os.environ["URL"] == "https://x.test/?a=b"         # only the first "=" splits
    assert "not a pair" not in os.environ and "# a comment" not in os.environ


def test_load_env_files_never_overrides_the_existing_environment(clean_env, tmp_path):
    f = tmp_path / "a.env"
    f.write_text("QWEN_MODEL=from-file\nQWEN_API_KEY=file-key\n")
    clean_env["QWEN_MODEL"] = "from-env"
    clean_env["CAIR_ENV_FILES"] = str(f)
    config.load_env_files()
    assert os.environ["QWEN_MODEL"] == "from-env"
    assert os.environ["QWEN_API_KEY"] == "file-key"


def test_load_env_files_skips_blank_and_missing_entries_and_reads_every_file(clean_env, tmp_path):
    a, b = tmp_path / "a.env", tmp_path / "b.env"
    a.write_text("FROM_A=1\nSHARED=first\n")
    b.write_text("FROM_B=2\nSHARED=second\n")
    clean_env["CAIR_ENV_FILES"] = f"{a}::{tmp_path / 'missing.env'}:{tmp_path}:{b}"   # blank, missing, a directory
    config.load_env_files()
    assert (os.environ["FROM_A"], os.environ["FROM_B"]) == ("1", "2")
    assert os.environ["SHARED"] == "first"                    # earlier file wins (setdefault)


def test_load_env_files_expands_the_home_directory(clean_env, tmp_path):
    (tmp_path / "home.env").write_text("HOME_EXPANDED=yes\n")
    clean_env["HOME"] = str(tmp_path)
    clean_env["CAIR_ENV_FILES"] = "~/home.env"
    config.load_env_files()
    assert os.environ["HOME_EXPANDED"] == "yes"


# --- module-level settings ------------------------------------------------------------------------------------
def test_defaults_when_nothing_is_set(clean_env):
    c = fresh_config()
    assert c.ROOT == CONFIG_PY.parent.parent and c.DATA == c.ROOT / "data"
    assert c.NEATLOGS_API_KEY == "" and c.NEATLOGS_WRITE_KEY == ""
    assert c.NEATLOGS_ENDPOINT == "https://ingest.neatlogs.com"
    assert c.NEATLOGS_PROJECT == "cair"
    assert c.NEATLOGS_MCP_URL == "https://ingest.neatlogs.com/mcp"
    assert c.LLM_API_KEY == "" and c.LLM_BASE_URL == "" and c.LLM_MODEL == "qwen-max"
    assert c.DB_PATH == c.ROOT / "var" / "cair.db"
    assert c.FX_BASE_URL == "https://api.frankfurter.dev/v2/providers/ecb"
    assert c.BUILDER_TOKEN == ""
    assert c.SECURE_COOKIES is True


def test_environment_overrides_every_setting(clean_env, tmp_path):
    c = fresh_config(NEATLOGS_API_KEY="nk", NEATLOGS_WRITE_KEY="wk", NEATLOGS_ENDPOINT="https://n.test///",
                     NEATLOGS_PROJECT="proj", QWEN_API_KEY="qk", QWEN_BASE_URL="https://q.test/v1",
                     QWEN_MODEL="qwen-plus", CAIR_DB=str(tmp_path / "x.db"), CAIR_FX_URL="https://fx.test",
                     CAIR_BUILDER_TOKEN="tok", CAIR_SECURE_COOKIES="0")
    assert (c.NEATLOGS_API_KEY, c.NEATLOGS_WRITE_KEY, c.NEATLOGS_PROJECT) == ("nk", "wk", "proj")
    assert c.NEATLOGS_ENDPOINT == "https://n.test"            # trailing slashes stripped
    assert c.NEATLOGS_MCP_URL == "https://n.test/mcp"         # derived from the normalised endpoint
    assert (c.LLM_API_KEY, c.LLM_BASE_URL, c.LLM_MODEL) == ("qk", "https://q.test/v1", "qwen-plus")
    assert c.DB_PATH == tmp_path / "x.db"
    assert c.FX_BASE_URL == "https://fx.test" and c.BUILDER_TOKEN == "tok"
    assert c.SECURE_COOKIES is False


def test_explicit_mcp_url_wins_over_the_endpoint_derived_one(clean_env):
    c = fresh_config(NEATLOGS_ENDPOINT="https://n.test", NEATLOGS_MCP_URL="https://mcp.test/x")
    assert c.NEATLOGS_MCP_URL == "https://mcp.test/x"


@pytest.mark.parametrize("value,expected", [("1", True), ("0", False), ("true", False), ("", False)])
def test_secure_cookies_is_only_on_for_exactly_1(clean_env, value, expected):
    assert fresh_config(CAIR_SECURE_COOKIES=value).SECURE_COOKIES is expected


def test_cookie_secret_uses_the_env_value_when_set(clean_env):
    assert fresh_config(CAIR_COOKIE_SECRET="s3cret").COOKIE_SECRET == "s3cret"


def test_cookie_secret_is_random_per_process_when_unset_or_empty(clean_env):
    a, b = fresh_config().COOKIE_SECRET, fresh_config().COOKIE_SECRET
    assert a != b and len(a) == len(b) == 64                  # 32 random bytes, hex encoded
    assert fresh_config(CAIR_COOKIE_SECRET="").COOKIE_SECRET not in ("", a)   # empty counts as unset


def test_importing_loads_env_files_before_reading_settings(clean_env, tmp_path):
    f = tmp_path / "boot.env"
    f.write_text("QWEN_MODEL=file-model\nCAIR_BUILDER_TOKEN='file-token'\n")
    c = fresh_config(CAIR_ENV_FILES=str(f))
    assert c.LLM_MODEL == "file-model" and c.BUILDER_TOKEN == "file-token"
