
from __future__ import annotations

from .. import config
from .base import http, parse_date


def _registrar(entities: list) -> str | None:
    for ent in entities or []:
        roles = ent.get("roles", [])
        if "registrar" in roles:
            for item in ent.get("vcardArray", [None, []])[1]:
                if item and item[0] == "fn":
                    return item[3]
            return ent.get("handle")
    return None


def _events(events: list) -> dict:
    out = {}
    for ev in events or []:
        action = ev.get("eventAction")
        if action:
            out[action] = parse_date(ev.get("eventDate"))
    return out


def _rdap(domain: str) -> dict:
    resp = http().get(f"{config.RDAP_BASE}/{domain}",
                      timeout=config.REQUEST_TIMEOUT, allow_redirects=True)
    if resp.status_code != 200:
        return {}
    data = resp.json()
    events = _events(data.get("events", []))
    nameservers = [ns.get("ldhName") for ns in data.get("nameservers", []) if ns.get("ldhName")]
    return {
        "registrar": _registrar(data.get("entities", [])),
        "statuses": data.get("status", []),
        "nameservers": nameservers,
        "registration_date": events.get("registration"),
        "last_changed_date": events.get("last changed") or events.get("last update of RDAP database"),
        "expiration_date": events.get("expiration"),
    }


def _wayback(domain: str) -> dict:
    try:
        resp = http().get(
            config.WAYBACK_AVAILABLE,
            params={"url": domain, "timestamp": "19960101"},
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return {}
        snap = resp.json().get("archived_snapshots", {}).get("closest", {})
        if not snap:
            return {}
        return {
            "wayback_first_snapshot": parse_date(snap.get("timestamp")),
            "wayback_last_snapshot_url": snap.get("url"),
        }
    except Exception:
        return {}


def fetch_domain(domain: str) -> dict | None:
    """Collect registration + archive metadata for a domain. ``None`` if nothing."""
    if not domain:
        return None
    record = {"domain": domain}
    try:
        record.update(_rdap(domain))
    except Exception as exc:
        print(f"  [domain] RDAP failed for {domain}: {exc}")
    record.update(_wayback(domain))
    return record
