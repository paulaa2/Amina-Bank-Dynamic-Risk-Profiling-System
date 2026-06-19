import requests
from datetime import datetime

RDAP_BASE = "https://rdap.org/domain"
WAYBACK_URL = "https://archive.org/wayback/available"
TIMEOUT = 15


def _parse_fecha(valor: str | None) -> str:
    if not valor:
        return "n/d"
    try:
        dt = datetime.fromisoformat(valor.rstrip("Z"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(valor)[:10]


def consultar_rdap(dominio: str) -> dict:
    """Obtiene datos de registro WHOIS/RDAP para un dominio."""
    resp = requests.get(
        f"{RDAP_BASE}/{dominio}",
        timeout=TIMEOUT,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}

    data = resp.json()

    # Registrar
    registrar = None
    for ent in data.get("entities", []):
        if "registrar" in ent.get("roles", []):
            vcard = ent.get("vcardArray", [None, []])[1]
            for item in vcard:
                if item and item[0] == "fn":
                    registrar = item[3]
                    break

    # Fechas de eventos
    fechas = {}
    for ev in data.get("events", []):
        accion = ev.get("eventAction")
        if accion:
            fechas[accion] = _parse_fecha(ev.get("eventDate"))

    # Servidores de nombre
    ns = [n.get("ldhName") for n in data.get("nameservers", []) if n.get("ldhName")]

    return {
        "dominio": data.get("ldhName") or dominio,
        "registrar": registrar,
        "estados": data.get("status", []),
        "nameservers": ns[:4],
        "fecha_registro": fechas.get("registration", "n/d"),
        "ultimo_cambio": fechas.get("last changed") or fechas.get("last update of RDAP database", "n/d"),
        "expiracion": fechas.get("expiration", "n/d"),
    }


def consultar_wayback(dominio: str) -> dict:
    """Busca el snapshot más antiguo disponible en Wayback Machine."""
    try:
        resp = requests.get(
            WAYBACK_URL,
            params={"url": dominio, "timestamp": "19960101"},
            timeout=TIMEOUT,
        )
        snap = resp.json().get("archived_snapshots", {}).get("closest", {})
        if not snap:
            return {"disponible": False}
        ts_raw = snap.get("timestamp", "")
        ts_fmt = f"{ts_raw[:4]}-{ts_raw[4:6]}-{ts_raw[6:8]}" if len(ts_raw) >= 8 else ts_raw
        return {
            "disponible": snap.get("available", False),
            "primera_captura": ts_fmt,
            "url_snapshot": snap.get("url"),
        }
    except Exception as exc:
        return {"disponible": False, "error": str(exc)}


# --- PRUEBA DE FUNCIONAMIENTO ---
if __name__ == "__main__":
    dominios_test = [
        "wirecard.com",
        "ftx.com",
        "openai.com",
        "vtb.ru",
        "gazprombank.ru",
    ]

    for dominio in dominios_test:
        print(f"\n{'='*60}")
        print(f"Dominio: {dominio}")
        print(f"{'='*60}")

        print("\n  [RDAP / WHOIS]")
        rdap = consultar_rdap(dominio)
        if "error" in rdap:
            print(f"  -> Error: {rdap['error']}")
        else:
            print(f"  Registrar     : {rdap['registrar'] or 'n/d'}")
            print(f"  Registro      : {rdap['fecha_registro']}")
            print(f"  Último cambio : {rdap['ultimo_cambio']}")
            print(f"  Expira        : {rdap['expiracion']}")
            print(f"  Estados       : {rdap['estados']}")
            print(f"  Nameservers   : {rdap['nameservers']}")

        print("\n  [Wayback Machine — snapshot más antiguo]")
        wb = consultar_wayback(dominio)
        if not wb.get("disponible"):
            print(f"  -> Sin snapshots  ({wb.get('error', '')})")
        else:
            print(f"  Primera captura : {wb['primera_captura']}")
            print(f"  URL snapshot    : {wb['url_snapshot']}")
