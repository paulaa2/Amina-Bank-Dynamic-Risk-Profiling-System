import urllib.parse
import requests

BASE_URL = "https://api.gleif.org/api/v1/lei-records"
HEADERS = {"Accept": "application/vnd.api+json"}
TIMEOUT = 15


def buscar_por_nombre(nombre: str, limit: int = 3) -> list[dict]:
    """Busca registros LEI por nombre de entidad legal."""
    params = {
        "filter[entity.legalName]": nombre,
        "page[size]": limit,
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    items = resp.json().get("data", [])
    resultados = []
    for item in items:
        attrs = item.get("attributes", {})
        entity = attrs.get("entity", {})
        reg = attrs.get("registration", {})
        resultados.append({
            "lei": attrs.get("lei") or item.get("id"),
            "nombre_legal": (entity.get("legalName") or {}).get("name"),
            "estado_entidad": entity.get("status"),
            "estado_lei": reg.get("status"),
            "pais": (entity.get("legalAddress") or {}).get("country"),
            "jurisdiccion": entity.get("jurisdiction"),
            "url_gleif": f"https://search.gleif.org/#/record/{attrs.get('lei') or item.get('id')}",
        })
    return resultados


def buscar_por_lei(lei: str) -> dict | None:
    """Busca un registro LEI por código LEI exacto (20 caracteres)."""
    resp = requests.get(f"{BASE_URL}/{lei}", headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    item = resp.json().get("data", {})
    attrs = item.get("attributes", {})
    entity = attrs.get("entity", {})
    reg = attrs.get("registration", {})
    return {
        "lei": attrs.get("lei") or item.get("id"),
        "nombre_legal": (entity.get("legalName") or {}).get("name"),
        "estado_entidad": entity.get("status"),
        "estado_lei": reg.get("status"),
        "pais": (entity.get("legalAddress") or {}).get("country"),
        "proxima_renovacion": reg.get("nextRenewalDate"),
        "url_gleif": f"https://search.gleif.org/#/record/{attrs.get('lei') or item.get('id')}",
    }


# --- PRUEBA DE FUNCIONAMIENTO ---
if __name__ == "__main__":
    empresas_test = [
        ("Wirecard AG",        "529900A8LX4KL0YUTH71"),
        ("VTB Bank",           None),
        ("Gazprombank",        None),
    ]

    for nombre, lei_conocido in empresas_test:
        print(f"\n{'='*60}")
        print(f"Empresa: {nombre}")
        print(f"{'='*60}")

        # Búsqueda por nombre
        print(f"\n  [Búsqueda por nombre: '{nombre}']")
        resultados = buscar_por_nombre(nombre, limit=2)
        if not resultados:
            print("  -> Sin resultados")
        for idx, r in enumerate(resultados, 1):
            print(f"\n  [{idx}] {r['nombre_legal']}")
            print(f"       LEI         : {r['lei']}")
            print(f"       Estado      : {r['estado_entidad']} / {r['estado_lei']}")
            print(f"       País        : {r['pais']}  |  Jurisdicción: {r['jurisdiccion']}")
            print(f"       URL GLEIF   : {r['url_gleif']}")

        # Búsqueda por LEI si lo conocemos
        if lei_conocido:
            print(f"\n  [Lookup por LEI: {lei_conocido}]")
            r = buscar_por_lei(lei_conocido)
            if r:
                print(f"  -> {r['nombre_legal']}")
                print(f"     Estado      : {r['estado_entidad']} / {r['estado_lei']}")
                print(f"     Próx. renov.: {r['proxima_renovacion']}")
            else:
                print("  -> LEI no encontrado")
