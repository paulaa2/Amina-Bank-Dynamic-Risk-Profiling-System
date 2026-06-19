
from __future__ import annotations

import csv
import datetime as dt
import re
import sys
import time

from .. import config
from .base import http

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "llc", "plc", "corp", "corporation",
    "gmbh", "ag", "sa", "se", "srl", "spa", "bv", "nv", "co", "company", "group",
    "holdings", "holding", "trading", "ltda", "oy", "ab", "as", "pte", "sas",
}


def _normalize(name: str) -> str:
    name = _PUNCT.sub(" ", (name or "").lower())
    return _WS.sub(" ", name).strip()


def _tokens(name: str) -> set[str]:
    return {t for t in _normalize(name).split() if t and t not in _SUFFIXES}


def _ensure_bulk_file() -> bool:
    """Download the OpenSanctions bulk CSV if missing or stale. Returns success."""
    cache = config.SANCTIONS_CACHE
    if cache.exists():
        age_h = (time.time() - cache.stat().st_mtime) / 3600
        if age_h < config.SANCTIONS_CACHE_TTL_HOURS and cache.stat().st_size > 0:
            return True
    try:
        with http().get(config.OPENSANCTIONS_BULK_CSV, stream=True,
                        timeout=config.REQUEST_TIMEOUT * 4) as resp:
            resp.raise_for_status()
            tmp = cache.with_suffix(".tmp")
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
            tmp.replace(cache)
        return True
    except Exception as exc:  
        print(f"  [sanctions] bulk download failed: {exc}")
        return cache.exists() and cache.stat().st_size > 0


_INDEX: list[dict] | None = None


def _load_index() -> list[dict]:
    """Load (and memoise) the bulk file into a list of {tokens, row} entries."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    entries: list[dict] = []
    if not _ensure_bulk_file():
        _INDEX = entries
        return entries
    with open(config.SANCTIONS_CACHE, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            names = [row.get("name", "")]
            names += [a for a in (row.get("aliases", "") or "").split(";") if a]
            token_variants = [(_tokens(n), n) for n in names if n.strip()]
            entries.append({"row": row, "names": token_variants})
    _INDEX = entries
    return entries


def _match_bulk(query: str) -> list[dict]:
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    results: list[dict] = []
    for entry in _load_index():
        best_score = 0.0
        best_name = None
        for cand_tokens, raw_name in entry["names"]:
            if not cand_tokens:
                continue
            if cand_tokens == q_tokens:
                score = 1.0
            elif q_tokens <= cand_tokens or cand_tokens <= q_tokens:
                # one is a subset of the other (e.g. "acme" in "acme trading")
                overlap = len(q_tokens & cand_tokens)
                score = overlap / max(len(q_tokens | cand_tokens), 1)
            else:
                continue
            if score > best_score:
                best_score, best_name = score, raw_name
        # Require a strong overlap to avoid noise.
        if best_score >= 0.85:
            row = entry["row"]
            results.append(
                {
                    "matched_name": best_name,
                    "entity_id": row.get("id"),
                    "schema": row.get("schema"),
                    "datasets": [d for d in (row.get("dataset", "") or "").split(";") if d],
                    "countries": [c for c in (row.get("countries", "") or "").split(";") if c],
                    "match_score": round(best_score, 3),
                    "source_url": f"https://www.opensanctions.org/entities/{row.get('id')}/"
                    if row.get("id") else None,
                }
            )
    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results


def _match_hosted(query: str) -> list[dict]:
    """Use the hosted /match endpoint (requires a paid/free-tier key)."""
    url = f"{config.OPENSANCTIONS_API}/match/default"
    headers = {"Authorization": f"ApiKey {config.OPENSANCTIONS_API_KEY}"}
    payload = {"queries": {"q": {"schema": "Company", "properties": {"name": [query]}}}}
    resp = http().post(url, json=payload, headers=headers, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("responses", {}).get("q", {}).get("results", [])
    out: list[dict] = []
    for r in results:
        out.append(
            {
                "matched_name": r.get("caption"),
                "entity_id": r.get("id"),
                "schema": r.get("schema"),
                "datasets": r.get("datasets", []),
                "countries": (r.get("properties", {}) or {}).get("country", []),
                "match_score": round(float(r.get("score", 0.0)), 3),
                "source_url": f"https://www.opensanctions.org/entities/{r.get('id')}/",
            }
        )
    return out


def fetch_sanctions(query: str, limit: int = 5) -> list[dict]:
    """Screen a name against sanctions/watchlists. Returns up to ``limit`` hits."""
    if config.OPENSANCTIONS_API_KEY:
        try:
            return _match_hosted(query)[:limit]
        except Exception as exc:
            print(f"  [sanctions] hosted match failed ({exc}); using bulk dataset")
    return _match_bulk(query)[:limit]
