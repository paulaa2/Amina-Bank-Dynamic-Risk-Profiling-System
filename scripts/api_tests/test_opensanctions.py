import csv
import os
import re
import sys
import time
import requests
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))

BULK_CSV_URL = "https://data.opensanctions.org/datasets/latest/sanctions/targets.simple.csv"
CACHE_PATH = Path("data/opensanctions_targets.csv")
CACHE_TTL_H = 24

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SUFIJOS = {
    "inc", "ltd", "limited", "llc", "plc", "corp", "corporation",
    "gmbh", "ag", "sa", "se", "bv", "nv", "co", "company", "group",
    "holdings", "pjsc", "ojsc", "jsc", "cjsc", "oao", "zao", "ooo",
}


def _normalizar(nombre: str) -> set[str]:
    texto = _PUNCT.sub(" ", (nombre or "").lower())
    tokens = _WS.sub(" ", texto).strip().split()
    return {t for t in tokens if t and t not in _SUFIJOS}


def _descargar_bulk() -> bool:
    """Descarga el CSV bulk si no existe o está caducado."""
    if CACHE_PATH.exists():
        age_h = (time.time() - CACHE_PATH.stat().st_mtime) / 3600
        if age_h < CACHE_TTL_H and CACHE_PATH.stat().st_size > 0:
            print(f"  [cache] Usando CSV local ({CACHE_PATH.stat().st_size // 1024 / 1024:.1f} MB)")
            return True
    print(f"  [descarga] Obteniendo dataset bulk desde {BULK_CSV_URL} ...")
    with requests.get(BULK_CSV_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        tmp = CACHE_PATH.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_content(1 << 16):
                fh.write(chunk)
        tmp.replace(CACHE_PATH)
    print(f"  [descarga] Guardado en {CACHE_PATH} ({CACHE_PATH.stat().st_size // 1024 / 1024:.1f} MB)")
    return True


def buscar_en_csv(nombre: str, min_score: float = 0.85) -> list[dict]:
    """Busca una empresa/persona en el CSV local por solapamiento de tokens."""
    _descargar_bulk()
    q = _normalizar(nombre)
    if not q:
        return []
    resultados = []
    with open(CACHE_PATH, encoding="utf-8", newline="") as fh:
        for fila in csv.DictReader(fh):
            nombres_cand = [fila.get("name", "")]
            nombres_cand += [a for a in (fila.get("aliases") or "").split(";") if a]
            mejor_score, mejor_nombre = 0.0, None
            for nombre_cand in nombres_cand:
                c = _normalizar(nombre_cand)
                if not c:
                    continue
                if c == q:
                    score = 1.0
                elif q <= c or c <= q:
                    score = len(q & c) / max(len(q | c), 1)
                else:
                    continue
                if score > mejor_score:
                    mejor_score, mejor_nombre = score, nombre_cand
            if mejor_score >= min_score:
                resultados.append({
                    "nombre_coincidencia": mejor_nombre,
                    "score": round(mejor_score, 3),
                    "schema": fila.get("schema"),
                    "id": fila.get("id"),
                    "paises": fila.get("countries"),
                    "datasets": fila.get("dataset", "")[:80],
                    "sanciones": fila.get("sanctions", "")[:120],
                    "url": f"https://www.opensanctions.org/entities/{fila.get('id')}/",
                })
    resultados.sort(key=lambda r: r["score"], reverse=True)
    return resultados[:5]


# --- PRUEBA DE FUNCIONAMIENTO ---
if __name__ == "__main__":
    empresas_test = [
        "VTB Bank",
        "Gazprombank",
        "Surgutneftegas",
        "OpenAI",           # No debería aparecer en sanciones
        "Wirecard AG",      # Tampoco (fue fraude contable, no sancionada como entidad)
    ]

    for empresa in empresas_test:
        print(f"\n{'='*60}")
        print(f"Búsqueda: {empresa}")
        print(f"{'='*60}")
        hits = buscar_en_csv(empresa)
        if not hits:
            print("  -> Sin coincidencias en listas de sanciones (OK)")
        else:
            for idx, h in enumerate(hits, 1):
                print(f"\n  [{idx}] *** SANCIONADO *** score={h['score']}")
                print(f"       Nombre coincidente : {h['nombre_coincidencia']}")
                print(f"       Schema / ID        : {h['schema']} / {h['id']}")
                print(f"       Países             : {h['paises']}")
                print(f"       Datasets           : {h['datasets']}")
                print(f"       Sanciones          : {h['sanciones']}")
                print(f"       URL                : {h['url']}")
