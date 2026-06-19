"""Central configuration. Reads optional values from a .env file."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional at runtime
    pass
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'risk_profiling.db').as_posix()}"

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
GLEIF_API = "https://api.gleif.org/api/v1/lei-records"
OPENSANCTIONS_API = "https://api.opensanctions.org"
OPENSANCTIONS_BULK_CSV = (
    "https://data.opensanctions.org/datasets/latest/sanctions/targets.simple.csv"
)
RDAP_BASE = "https://rdap.org/domain"
WAYBACK_AVAILABLE = "https://archive.org/wayback/available"

OPENSANCTIONS_API_KEY = os.getenv("OPENSANCTIONS_API_KEY") or None
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY") or None

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
USER_AGENT = "AminaRiskProfiling/0.1 (+hackathon prototype)"

SANCTIONS_CACHE = DATA_DIR / "opensanctions_targets.csv"
SANCTIONS_CACHE_TTL_HOURS = 24
