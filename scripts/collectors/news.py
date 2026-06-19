
from __future__ import annotations

import urllib.parse
from typing import Optional

import feedparser

from .. import config
from .base import adverse_media_score, parse_date


_QUERY_TEMPLATES: list[tuple[str, str, str, str]] = [
    # --- English feeds ---
    (
        "general_en",
        '"{name}"',
        "en-US", "US",
    ),
    (
        "adverse_en",
        '"{name}" (fraud OR scandal OR investigation OR sanction OR lawsuit OR "money laundering")',
        "en-US", "US",
    ),
    (
        "regulatory_en",
        '"{name}" (regulator OR "regulatory" OR fine OR penalty OR compliance OR breach)',
        "en-US", "US",
    ),
    (
        "legal_en",
        '"{name}" (indicted OR arrested OR charged OR court OR insolvency OR bankruptcy)',
        "en-US", "US",
    ),
    # --- Spanish feeds (relevant for Amina Bank / EU context) ---
    (
        "general_es",
        '"{name}"',
        "es-ES", "ES",
    ),
    (
        "adverse_es",
        '"{name}" (fraude OR investigación OR sanción OR escándalo OR demanda)',
        "es-ES", "ES",
    ),
]


def _extract_source(entry: dict) -> Optional[str]:
    """Pull a readable source name from a feedparser entry."""
    src = entry.get("source")
    if isinstance(src, dict):
        return src.get("title") or src.get("href")
    if isinstance(src, str) and src:
        return src
    # Google News often embeds "- Source Name" at the end of the title
    title = entry.get("title", "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return None


def _build_url(name: str, query_suffix: str, language: str, country: str) -> str:
    """Build a Google News RSS URL exactly like the test script, using urllib.parse.quote."""
    raw_query = query_suffix.replace("{name}", name)
    encoded_query = urllib.parse.quote(raw_query)
    lang_code = language.split("-")[0]
    return (
        f"{config.GOOGLE_NEWS_RSS}"
        f"?q={encoded_query}"
        f"&hl={language}"
        f"&gl={country}"
        f"&ceid={country}:{lang_code}"
    )


def fetch_news(
    company_name: str,
    limit_per_query: int = 20,
    verbose: bool = False,
) -> list[dict]:
    """Fetch news for *company_name* across all themed query templates.

    Parameters
    ----------
    company_name:
        The entity to search for (used as ``{name}`` in the templates).
    limit_per_query:
        Maximum articles fetched from each individual RSS query.
    verbose:
        Print progress in the same style as the original test script.

    Returns
    -------
    Deduplicated list of article dicts ready to persist to ``NewsArticle``.
    """
    seen_urls: set[str] = set()
    articles: list[dict] = []

    for label, query_suffix, language, country in _QUERY_TEMPLATES:
        url = _build_url(company_name, query_suffix, language, country)
        feed = feedparser.parse(url)
        batch: list[dict] = []

        for entry in feed.entries[:limit_per_query]:
            link = entry.get("link", "")
            if link in seen_urls:
                continue
            seen_urls.add(link)

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            score, matched = adverse_media_score(f"{title} {summary}")
            published = parse_date(entry.get("published"))

            article = {
                "title": title,
                "url": link,
                "source": _extract_source(entry),
                "published_at": published,
                "summary": summary,
                "adverse_score": score,
                "matched_keywords": matched,
                # Extra fields for traceability (not in DB model but useful for debug)
                "_query_label": label,
                "_language": language,
            }
            batch.append(article)

        if verbose and batch:
            print(f"\n  --- [{label}] {len(batch)} noticias para: {company_name} ---")
            for idx, a in enumerate(batch, 1):
                date_str = a["published_at"].strftime("%Y-%m-%d") if a["published_at"] else "n/d"
                print(f"  [{idx}] {a['title']}")
                print(f"       Fecha : {date_str}")
                print(f"       Fuente: {a['source'] or '—'}")
                print(f"       Link  : {a['url']}")
                if a["matched_keywords"]:
                    print(f"       Adverse keywords: {a['matched_keywords']}")

        articles.extend(batch)

    # Strip internal debug keys before returning
    for a in articles:
        a.pop("_query_label", None)
        a.pop("_language", None)

    return articles
