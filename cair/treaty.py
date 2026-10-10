"""Treaty retrieval: BM25 over the articles of each US income-tax treaty in data/treaties/.

The decision "is there an article for this income?" is set membership on the sheet; BM25 only finds the nearest
articles to show next to it. A lexical index cannot invent an article that is not in the text.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

from .config import DATA

QUERY = "prize award contest other income independent personal services"


def _tok(s: str) -> list[str]:
    return re.findall(r"[a-z]+", s.lower())


@lru_cache(maxsize=None)
def index(country: str):
    path = DATA / "treaties" / f"{country.lower()}.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text())
    arts = doc["articles"]
    bm = BM25Okapi([_tok(a["title"] + " " + a["title"] + " " + a["text"]) for a in arts])
    return doc, bm


def nearest(country: str, query: str = QUERY, k: int = 3) -> dict:
    hit = index(country)
    if hit is None:
        return {"country": country, "treaty_text_indexed": False, "nearest": []}
    doc, bm = hit
    scores = bm.get_scores(_tok(query))
    top = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
    arts = doc["articles"]
    return {"country": country, "treaty_text_indexed": True, "source_url": doc["source_url"],
            "article_count": len(arts),
            "has_article_titled_other_income": any(a["title"].lower().startswith("other income") for a in arts),
            "nearest": [{"article": arts[i]["article"], "title": arts[i]["title"],
                         "score": round(float(scores[i]), 3)} for i in top]}
