"""Descripciones de los sitios oficiales de las marcas: solo el TEXTO, nunca el precio.

Muchas tiendas no entregan descripción (YesStyle, Stylevana, las farmacias), y sin texto describe.py no tiene de dónde sacar datos. El sitio
oficial de la marca sí la trae. Se guarda aparte, en la tabla `brand_text`: no son ofertas, así que no cuentan para precios, stock ni ofertas,
y no tocan el matching de precios ni los ids de producto. describe.py nunca copia el texto: extrae datos y redacta con plantillas.

Dominios verificados el 2026-10-04: título "Official", empresa y redes oficiales de la marca (y misshaus.com por búsqueda web). Todos son
Shopify y su robots.txt permite /products.json. Se descartaron Rom&nd, Lily by Red y Elizavecca (`Disallow: /`), Apivita (403) y las marcas
con sitio solo en coreano, que describe.py no entiende (ver docs/scraping/stores.md).
"""
import time
from datetime import datetime, timedelta, timezone

from scrapers.common import text_of
from scrapers.http import DELAY, Blocked, get, log

BRAND_SITES = {  # dominio -> marca forzada; None: la de cada producto (misshaus.com vende Missha, A'pieu y otras de Able C&C)
    "unleashiaworld.com": "Unleashia",
    "tirtir.global": "TirTir",
    "mixsoon.us": "Mixsoon",
    "tocobo.us": "Tocobo",
    "misshaus.com": None,
    "centellian24.com": "Centellian24",
}
EVERY_DAYS = 7  # las descripciones cambian poco: una lectura por semana basta (6 sitios, una solicitud cada uno, menos de un minuto)


def shopify_texts(domain, vendor=None):
    """Un registro por producto con descripción (body_html en texto plano), desde /products.json."""
    page = 1
    while True:
        products = get(f"https://{domain}/products.json?limit=250&page={page}")["products"]
        if not products:
            return
        for p in products:
            text = text_of(p.get("body_html"))
            if text:
                yield dict(ext_id=str(p["id"]), vendor=vendor or p.get("vendor") or "", title=p["title"], description=text,
                           url=f"https://{domain}/products/{p['handle']}")
        page += 1
        time.sleep(DELAY)


def refresh(db, force=False):
    """Vuelve a leer los sitios de BRAND_SITES si pasaron EVERY_DAYS desde la última vez (meta['brandtext:done']). Un sitio que bloquea
    (403/429) o falla se deja para la próxima, sin reintentar (ADR-003)."""
    now = datetime.now(timezone.utc)
    last = db.execute("SELECT value FROM meta WHERE key = 'brandtext:done'").fetchone()
    if last and not force and datetime.fromisoformat(last[0]) > now - timedelta(days=EVERY_DAYS):
        return
    ts = now.isoformat(timespec="seconds")
    for domain, vendor in BRAND_SITES.items():
        try:
            rows = list(shopify_texts(domain, vendor))
        except Blocked as e:
            log(f"{domain} (textos de la marca): bloqueado, se deja ({e})")
            continue
        except Exception as e:
            log(f"{domain} (textos de la marca): ERROR {e}")
            continue
        db.executemany("""INSERT INTO brand_text VALUES(?,?,?,?,?,?,?) ON CONFLICT(source, ext_id) DO UPDATE SET vendor=excluded.vendor,
                          title=excluded.title, description=excluded.description, url=excluded.url, seen=excluded.seen""",
                       [(domain, r["ext_id"], r["vendor"], r["title"], r["description"], r["url"], ts) for r in rows])
        db.commit()
        log(f"{domain} (textos de la marca): {len(rows)} productos con descripción")
        time.sleep(DELAY)
    db.execute("INSERT OR REPLACE INTO meta VALUES('brandtext:done', ?)", (ts,))
    db.commit()
