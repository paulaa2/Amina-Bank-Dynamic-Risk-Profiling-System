from __future__ import annotations

import datetime as dt
from typing import Optional

import requests
from dateutil import parser as date_parser

from .. import config

_session: Optional[requests.Session] = None


def http() -> requests.Session:
    """Lazily-built shared requests session with a sane User-Agent."""
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": config.USER_AGENT, "Accept": "*/*"})
        _session = s
    return _session


def parse_date(value) -> Optional[dt.datetime]:
    """Best-effort parse of any date/time string into a naive UTC datetime."""
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value
    try:
        parsed = date_parser.parse(str(value))
    except (ValueError, OverflowError, TypeError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed

ADVERSE_KEYWORDS = {
    "fraud": 1.0,
    "scam": 1.0,
    "money laundering": 1.0,
    "laundering": 0.9,
    "sanction": 0.9,
    "sanctions": 0.9,
    "bribery": 0.9,
    "corruption": 0.9,
    "embezzlement": 1.0,
    "ponzi": 1.0,
    "investigation": 0.7,
    "probe": 0.6,
    "lawsuit": 0.6,
    "indictment": 0.9,
    "indicted": 0.9,
    "charged": 0.6,
    "arrest": 0.8,
    "arrested": 0.8,
    "insolvency": 0.8,
    "bankruptcy": 0.8,
    "collapse": 0.7,
    "default": 0.6,
    "raid": 0.7,
    "regulator": 0.5,
    "fine": 0.6,
    "penalty": 0.6,
    "breach": 0.6,
    "terror": 1.0,
    "shell company": 0.9,
    "offshore": 0.6,
    "whistleblower": 0.6,
    "resign": 0.5,
    "resigned": 0.5,
    "delisted": 0.7,
}


def adverse_media_score(text: str) -> tuple[float, list[str]]:
    """Return (normalised 0..1 score, matched keywords) for a piece of text."""
    if not text:
        return 0.0, []
    lowered = text.lower()
    matched: list[str] = []
    score = 0.0
    for kw, weight in ADVERSE_KEYWORDS.items():
        if kw in lowered:
            matched.append(kw)
            score += weight
    normalised = min(1.0, score / 3.0)
    return round(normalised, 3), matched
