"""Build data/treaties/<cc>.json from an IRS treaty PDF's text layer.

    curl -sSLO https://www.irs.gov/pub/irs-trty/indo.pdf && pdftotext -layout indo.pdf indo.txt
    python scripts/extract_treaty.py ID indo.txt https://www.irs.gov/pub/irs-trty/indo.pdf

Splits the main convention text on its centred "ARTICLE N" headings (the first occurrence of each number, so the
protocol and exchange of notes that follow are not mixed in), takes the next non-blank line as the title and the
following text as the excerpt the treaty retriever indexes.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

HEAD = re.compile(r"^\s{10,}ARTICLE\s+(\d+)\s*$")


def extract(text: str) -> list[dict]:
    lines = text.splitlines()
    starts: list[tuple[int, int]] = []
    seen: set[int] = set()
    for i, line in enumerate(lines):
        m = HEAD.match(line)
        if m:
            n = int(m.group(1))
            if n in seen or (starts and n != starts[-1][1] + 1):
                if n == 1 and starts:  # a second ARTICLE 1 = the protocol begins
                    break
                continue
            seen.add(n)
            starts.append((i, n))
    articles = []
    for k, (i, n) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else min(len(lines), i + 80)
        body = [ln.strip() for ln in lines[i + 1:end]]
        body = [ln for ln in body if ln and not re.fullmatch(r"-?\s*\d+\s*-?", ln)]
        title = body[0] if body else ""
        excerpt = re.sub(r"\s+", " ", " ".join(body[1:]))[:700]
        articles.append({"article": n, "title": title, "text": excerpt})
    return articles


def main() -> None:
    cc, txt, url = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    arts = extract(txt.read_text(errors="replace"))
    out = Path(__file__).resolve().parent.parent / "data" / "treaties" / f"{cc.lower()}.json"
    out.write_text(json.dumps({"country": cc.upper(), "source_url": url, "accessed_at": date.today().isoformat(),
                               "articles": arts}, indent=1, ensure_ascii=False) + "\n")
    print(out, len(arts), "articles")


if __name__ == "__main__":
    main()
