"""Test del collector Firecrawl — scraping de páginas de funding (requiere clave).

Usa el SDK oficial: pip install firecrawl-py

Plan gratuito: 1 000 créditos/mes, sin tarjeta de crédito.
Copia la clave en .env como: FIRECRAWL_API_KEY=fc-xxxxxxxx

Ejecución:
    python scripts/api_tests/test_firecrawl.py
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Allow running from project root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

_AMOUNT_RE = re.compile(
    r"(?P<cur>[$€£])\s?(?P<num>[\d,]+(?:\.\d+)?)\s?(?P<mult>billion|million|bn|m|b)?",
    re.IGNORECASE,
)
_ROUND_RE = re.compile(
    r"\b(pre-seed|seed|series\s+[a-h]|angel|ipo|bridge|growth|venture|funding round)\b",
    re.IGNORECASE,
)
_MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "m": 1e6}
_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}


def _parse_amount(texto: str):
    m = _AMOUNT_RE.search(texto or "")
    if not m:
        return None, None
    num = float(m.group("num").replace(",", ""))
    mult = (m.group("mult") or "").lower().strip()
    num *= _MULT.get(mult, 1.0)
    return num, _CURRENCY.get(m.group("cur"))


def _parse_round(texto: str):
    m = _ROUND_RE.search(texto or "")
    return m.group(0).title() if m else None


def raspar_url(url: str, app) -> str | None:
    """Llama a Firecrawl SDK y devuelve el Markdown de la pagina."""
    try:
        result = app.scrape(
            url,
            formats=["markdown"],
            only_main_content=True,
            wait_for=2000,
        )
        if isinstance(result, dict):
            return result.get("markdown")
        return getattr(result, "markdown", None)
    except Exception as exc:
        print(f"  -> Error Firecrawl: {exc}")
        return None


def extraer_eventos_funding(markdown: str, url_fuente: str) -> list[dict]:
    """Extrae eventos de financiacion del Markdown scrapeado."""
    eventos = []
    bloques = re.split(r"\n#{1,3} |\n---+\n", markdown)
    for bloque in bloques:
        amount, currency = _parse_amount(bloque)
        round_type = _parse_round(bloque)
        if amount is None and round_type is None:
            continue
        primera_linea = re.sub(r"[#*_`\[\]]", "", bloque.split("\n")[0]).strip()
        eventos.append({
            "titulo": primera_linea[:150] or f"{round_type} {amount}",
            "importe": f"{amount:,.0f} {currency}" if amount else "n/d",
            "ronda": round_type or "?",
            "fuente": url_fuente,
        })
    return eventos


# --- PRUEBA DE FUNCIONAMIENTO ---
if __name__ == "__main__":
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        print("ERROR: FIRECRAWL_API_KEY no esta configurado.")
        print("  Copia tu clave en el fichero .env: FIRECRAWL_API_KEY=fc-xxxx")
        raise SystemExit(1)

    from firecrawl import Firecrawl

    app = Firecrawl(api_key=api_key)

    empresa_test = "OpenAI"
    slug = "openai"

    urls_test = [
        (f"https://www.crunchbase.com/organization/{slug}/funding_rounds", "Crunchbase"),
        (f"https://techcrunch.com/search/?q={empresa_test}+funding", "TechCrunch"),
    ]

    print(f"--- Funding intelligence para: {empresa_test} ---")
    print(f"Clave Firecrawl: {api_key[:8]}... (ok)\n")

    for url, fuente in urls_test:
        print(f"\n[{fuente}] {url}")
        markdown = raspar_url(url, app)
        if not markdown:
            print("  -> Sin contenido")
            continue
        print(f"  Markdown obtenido: {len(markdown):,} caracteres")
        eventos = extraer_eventos_funding(markdown, url)
        if not eventos:
            print("  -> No se detectaron eventos de financiacion en este contenido")
        else:
            print(f"  {len(eventos)} evento(s) detectado(s):")
            for idx, ev in enumerate(eventos, 1):
                print(f"\n  [{idx}] {ev['titulo']}")
                print(f"       Ronda   : {ev['ronda']}")
                print(f"       Importe : {ev['importe']}")
                print(f"       Fuente  : {ev['fuente']}")
