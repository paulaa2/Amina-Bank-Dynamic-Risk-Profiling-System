"""Corporate registry / ownership collector -> GLEIF LEI API (free, no key)."""
from __future__ import annotations

from .. import config
from .base import http, parse_date


def _format_address(addr: dict | None) -> str | None:
    if not addr:
        return None
    parts = [
        " ".join(addr.get("addressLines", []) or []),
        addr.get("postalCode"),
        addr.get("city"),
        addr.get("region"),
        addr.get("country"),
    ]
    return ", ".join(p for p in parts if p) or None


def _parse_record(item: dict) -> dict:
    attrs = item.get("attributes", {})
    entity = attrs.get("entity", {})
    registration = attrs.get("registration", {})
    rels = item.get("relationships", {})

    parent_lei = None
    parent = rels.get("direct-parent", {}).get("data") if rels else None
    if isinstance(parent, dict):
        parent_lei = parent.get("id")

    other_names = [n.get("name") for n in entity.get("otherNames", []) if n.get("name")]

    return {
        "lei": attrs.get("lei") or item.get("id"),
        "legal_name": (entity.get("legalName") or {}).get("name"),
        "other_names": other_names,
        "entity_status": entity.get("status"),
        "lei_status": registration.get("status"),
        "legal_form": (entity.get("legalForm") or {}).get("id"),
        "jurisdiction": entity.get("jurisdiction"),
        "country": (entity.get("legalAddress") or {}).get("country"),
        "address": _format_address(entity.get("legalAddress")),
        "registration_date": parse_date(registration.get("initialRegistrationDate")),
        "last_update_date": parse_date(registration.get("lastUpdateDate")),
        "parent_lei": parent_lei,
        "source_url": f"https://search.gleif.org/#/record/{attrs.get('lei') or item.get('id')}",
    }


def _query(params: dict) -> list[dict]:
    resp = http().get(config.GLEIF_API, params=params, timeout=config.REQUEST_TIMEOUT)
    if resp.status_code in (400, 404):
        return []
    resp.raise_for_status()
    return [_parse_record(item) for item in resp.json().get("data", [])]


def fetch_registry(legal_name: str | None = None, lei: str | None = None,
                   limit: int = 1) -> list[dict]:
    """Look up LEI records by exact LEI, falling back to (fuzzy) legal-name search."""
    if lei:
        records = _query({"filter[lei]": lei, "page[size]": limit})
        if records:
            return records
    if legal_name:
        return _query({"filter[entity.legalName]": legal_name, "page[size]": limit})
    return []
