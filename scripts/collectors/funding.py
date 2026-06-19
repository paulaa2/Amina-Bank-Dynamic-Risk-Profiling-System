    
from __future__ import annotations

import re
from typing import Optional

from .. import config
from .base import parse_date

# Lazy Firecrawl SDK client — created once on first use.
_firecrawl_client = None


def _get_firecrawl():
    global _firecrawl_client
    if _firecrawl_client is None and config.FIRECRAWL_API_KEY:
        from firecrawl import Firecrawl
        _firecrawl_client = Firecrawl(api_key=config.FIRECRAWL_API_KEY)
    return _firecrawl_client


# ---------------------------------------------------------------------------
# Regex helpers shared between Firecrawl + RSS fallback
# ---------------------------------------------------------------------------
_AMOUNT_RE = re.compile(
    r"(?P<cur>[$€£])\s?(?P<num>[\d,]+(?:\.\d+)?)\s?(?P<mult>billion|million|bn|m|b)?",
    re.IGNORECASE,
)
_ROUND_RE = re.compile(
    r"\b(pre-seed|seed|series\s+[a-h]|angel|ipo|spac|grant|debt|convertible|bridge|"
    r"growth equity|growth|venture|funding round|round [a-h])\b",
    re.IGNORECASE,
)
_INVESTORS_RE = re.compile(
    r"(?:led by|investors?[:\s]+|backed by|from)\s+([A-Z][^.!?\n]{5,80})",
    re.IGNORECASE,
)
_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}
_MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "m": 1e6}


def _parse_amount(text: str) -> tuple[Optional[float], Optional[str]]:
    m = _AMOUNT_RE.search(text or "")
    if not m:
        return None, None
    num = float(m.group("num").replace(",", ""))
    mult = (m.group("mult") or "").lower().strip()
    num *= _MULT.get(mult, 1.0)
    return num, _CURRENCY.get(m.group("cur"))


def _parse_round(text: str) -> Optional[str]:
    m = _ROUND_RE.search(text or "")
    return m.group(0).title() if m else None


def _parse_investors(text: str) -> Optional[str]:
    m = _INVESTORS_RE.search(text or "")
    return m.group(1).strip()[:200] if m else None


# ---------------------------------------------------------------------------
# Firecrawl scraper (official SDK: firecrawl-py)
# ---------------------------------------------------------------------------
def _firecrawl_scrape(url: str) -> Optional[str]:
    """Scrape *url* via the Firecrawl SDK and return Markdown, or None on error."""
    client = _get_firecrawl()
    if not client:
        return None
    try:
        result = client.scrape(
            url,
            formats=["markdown"],
            only_main_content=True,
            wait_for=2000,
        )
        if isinstance(result, dict):
            return result.get("markdown") or None
        return getattr(result, "markdown", None)
    except Exception as exc:
        print(f"    [firecrawl] scrape failed ({url}): {exc}")
        return None


def _crunchbase_slug(company_name: str) -> str:
    """Best-effort Crunchbase slug from a company name (lowercase, hyphens)."""
    slug = company_name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    # Strip common legal suffixes from the slug
    for suffix in ("-ag", "-ltd", "-llc", "-inc", "-plc", "-gmbh", "-sa", "-trading"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
    return slug


def _parse_markdown_events(markdown: str, source_url: str, source_label: str) -> list[dict]:
    """Extract structured funding events from a block of Markdown text."""
    events: list[dict] = []

    # Split on H2/H3 headings or horizontal rules to get per-round blocks
    blocks = re.split(r"\n#{1,3} |\n---+\n", markdown)
    for block in blocks:
        amount, currency = _parse_amount(block)
        round_type = _parse_round(block)
        if amount is None and round_type is None:
            continue

        # Try to find a date in the block
        date_match = re.search(
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}",
            block,
            re.IGNORECASE,
        )
        announced_at = parse_date(date_match.group(0)) if date_match else None

        # First line of the block as title (strip Markdown markup)
        first_line = re.sub(r"[#*_`\[\]]", "", block.split("\n")[0]).strip()
        title = first_line[:200] or f"{round_type or ''} {amount or ''} {currency or ''}".strip()

        investors = _parse_investors(block)

        events.append(
            {
                "title": title,
                "url": source_url,
                "source": source_label,
                "amount_value": amount,
                "amount_currency": currency,
                "round_type": round_type,
                "announced_at": announced_at,
                # stored in notes-style field via title if investors present
            }
        )
        if investors:
            events[-1]["title"] = f"{events[-1]['title']} — {investors}"

    return events


# ---------------------------------------------------------------------------
# Target URLs to scrape per company
# ---------------------------------------------------------------------------
def _target_urls(company_name: str, domain: Optional[str] = None) -> list[tuple[str, str]]:
    """Return [(url, label), ...] to scrape with Firecrawl for this company."""
    slug = _crunchbase_slug(company_name)
    encoded = re.sub(r"\s+", "+", company_name)
    urls = [
        (
            f"https://www.crunchbase.com/organization/{slug}/funding_rounds",
            "crunchbase",
        ),
        (
            f"https://techcrunch.com/search/?q={encoded}+funding",
            "techcrunch",
        ),
        (
            f"https://sifted.eu/?s={encoded}+funding",
            "sifted",
        ),
    ]
    return urls


# ---------------------------------------------------------------------------
# RSS fallback (used when FIRECRAWL_API_KEY is not set)
# ---------------------------------------------------------------------------
def _rss_fallback(company_name: str, limit: int) -> list[dict]:
    """Derive funding events from Google News RSS (no key required).

    Uses three complementary queries to maximise coverage:
      1. Funding rounds & investment news
      2. IPO / valuation news
      3. Acquisition & M&A news
    Results are deduplicated by URL before parsing.
    """
    queries = [
        f'"{company_name}" (funding OR raises OR "Series A" OR "Series B" OR "Series C" OR investment)',
        f'"{company_name}" (IPO OR valuation OR "goes public" OR SPAC OR listing)',
        f'"{company_name}" (acquisition OR acquires OR "merges with" OR buyout)',
    ]
    seen_urls: set[str] = set()
    events: list[dict] = []

    for query in queries:
        for art in _rss_fetch(query, limit):
            if art["url"] in seen_urls:
                continue
            seen_urls.add(art["url"])
            text = f"{art['title']} {art.get('summary', '')}"
            amount, currency = _parse_amount(text)
            round_type = _parse_round(text)
            if amount is None and round_type is None:
                continue
            events.append(
                {
                    "title": art["title"],
                    "url": art["url"],
                    "source": art.get("source"),
                    "amount_value": amount,
                    "amount_currency": currency,
                    "round_type": round_type,
                    "announced_at": art.get("published_at"),
                }
            )
    return events


def _rss_fetch(query: str, limit: int) -> list[dict]:
    """Minimal RSS fetch to avoid circular imports when calling the fallback."""
    import urllib.parse as _up
    import feedparser as _fp
    from .base import parse_date as _pd

    encoded = _up.quote(query)
    url = f"{config.GOOGLE_NEWS_RSS}?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    feed = _fp.parse(url)
    return [
        {
            "title": e.get("title", ""),
            "url": e.get("link", ""),
            "source": (e.get("source") or {}).get("title") if isinstance(e.get("source"), dict) else None,
            "published_at": _pd(e.get("published")),
            "summary": e.get("summary", ""),
        }
        for e in feed.entries[:limit]
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def fetch_funding(
    company_name: str,
    domain: Optional[str] = None,
    limit: int = 15,
) -> list[dict]:
    """Collect funding & startup intelligence for *company_name*.

    Uses Firecrawl (Crunchbase + TechCrunch + Sifted) when ``FIRECRAWL_API_KEY``
    is configured, otherwise falls back to Google News RSS.
    """
    if not config.FIRECRAWL_API_KEY:
        print("    [funding] No FIRECRAWL_API_KEY — using RSS fallback")
        return _rss_fallback(company_name, limit)

    all_events: list[dict] = []
    seen_titles: set[str] = set()

    for url, label in _target_urls(company_name, domain):
        print(f"    [funding] Firecrawl [{label}]: {url}")
        markdown = _firecrawl_scrape(url)
        if not markdown:
            print(f"    [funding] No content from {label}")
            continue

        events = _parse_markdown_events(markdown, url, label)
        for ev in events:
            key = ev["title"][:80].lower()
            if key not in seen_titles:
                seen_titles.add(key)
                all_events.append(ev)

        print(f"    [funding] {len(events)} event(s) parsed from {label}")

    if not all_events:
        print("    [funding] Firecrawl returned no events — using RSS fallback")
        return _rss_fallback(company_name, limit)

    return all_events[:limit]
