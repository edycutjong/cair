"""Export neatlogs traces as read back over the MCP server (get_trace_context) into evidence/traces/<name>.json.

    NEATLOGS_API_KEY=... python scripts/export_trace.py v2-hero=6ea01b70588b56884b9f4193c431f5ce ...

Only builder and eval traces are exported (no real user's data). File paths in code locations are trimmed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cair import neat  # noqa: E402


def main() -> None:
    pairs = [a.split("=", 1) for a in sys.argv[1:]]
    results = neat.mcp([("get_trace_context", {"trace_id": tid}) for _, tid in pairs], timeout=90)
    out_dir = ROOT / "evidence" / "traces"
    out_dir.mkdir(parents=True, exist_ok=True)
    for (name, tid), ctx in zip(pairs, results):
        text = re.sub(r"(/[\w.-]+)+/(cair|scripts)/", r"<repo>/\2/", json.dumps(ctx, indent=1, ensure_ascii=False))
        (out_dir / f"{name}.json").write_text(text + "\n")
        spans = ctx.get("spans", []) if isinstance(ctx, dict) else []
        print(f"{name}: {tid} spans={len(spans)} status={ctx.get('status') if isinstance(ctx, dict) else ctx}")


if __name__ == "__main__":
    main()
