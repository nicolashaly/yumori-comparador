"""Scrapea tiendas -> SQLite con historial de precios.

Uso: python scrape.py [dominio ...]   (sin argumentos: todas las tiendas)
     python scrape.py --diario        (se omite si ya hubo una corrida completa hoy)
     python scrape.py --estado        (cómo fue la última lectura de cada tienda)
"""
import sys
import time
from datetime import datetime, timezone

import publish_db
from db import BY_BRAND, DB, PAUSED, connect, done_today, save, short_read
from scrapers import brand_text
from scrapers.common import ScrapeCompletion
from scrapers.dbs import dbs
from scrapers.ecofarmacias import ecofarmacias
from scrapers.fx import update_fx
from scrapers.http import log
from scrapers.jsonld import jumpseller, tiendanube
from scrapers.nextdata import farmaloop
from scrapers.novasalud import novasalud
from scrapers.paris import paris
from scrapers.sfcc import sfcc
from scrapers.shopify import shopify
from scrapers.woocommerce import woocommerce
from scrapers.yesstyle import yesstyle


STORES = {  # dominio -> adaptador
    "vierosecosmetics.cl": woocommerce,
    "moonbow.cl": shopify,
    "nooki.cl": shopify,
    "coreanachile.cl": shopify,
    "www.bombeauty.cl": shopify,
    "sokobox.cl": shopify,
    "rakuencosmeticacoreana.cl": shopify,
    "quecoreana.cl": shopify,
    "arumi.cl": shopify,
    "www.koryobeauty.cl": tiendanube,
    "unniebeauty.cl": jumpseller,
    "www.farmaciasahumada.cl": sfcc,  # dermocosmética: ~11 páginas con 10 s de pausa; sin start (su robots.txt lo veta)
    "dermotienda.cl": shopify,  # dermocosmética, ~9 s; el SKU es el EAN
    "www.ecofarmacias.cl": ecofarmacias,  # farmacia: 2 categorías de la Store API, ~35 s
    "www.novasalud.cl": novasalud,  # farmacia: /dispositivos-medicos en 9 páginas con 20 s de pausa (~3 min)
    "www.farmaloop.cl": farmaloop,  # farmacia: 7 páginas de 15 con 10 s de pausa (~66 s); lectura parcial por diseño (db.PARTIAL)
    "www.paris.cl": paris,  # dermocosmética: 11 páginas con 10 s de pausa (~2 min); solo los 30 primeros por marca (db.PARTIAL)
    "dbs.cl": dbs,  # coreanas y dos marcas dermo: 22 páginas de marca con 10 s de pausa (~4 min)
    "www.wishtrend.com": lambda d: shopify(d, "USD"),  # internacionales: precios en USD
    "cosrx.com": lambda d: shopify(d, "USD", vendor="COSRX"),
    "beautyofjoseon.com": lambda d: shopify(d, "USD", vendor="Beauty of Joseon"),
    "www.yesstyle.com": yesstyle,  # al final: con sus pausas tarda hasta ~90 min y puede cortarse, no debe retrasar al resto
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scrape_store(db, domain, run):
    """Lee y guarda una tienda, y deja una fila en scrape_run con lo que pasó. Un error se registra y no detiene la corrida."""
    t0, started, bad = time.monotonic(), now(), []
    status, total, changed, error = "ok", None, None, None
    try:
        items, completion = collect(STORES[domain](domain))
        at = None if completion.complete and not completion.partial else short_read(db, domain, len(items))
        partial = completion.partial or at is not None
        if domain in BY_BRAND:
            at = None  # la cobertura la acredita metadata por marca, no la fecha global
        if partial and domain not in BY_BRAND and at is None:
            at = db.execute("SELECT MAX(last_seen) FROM listing WHERE store = ?", (domain,)).fetchone()[0]
            at = at or "1970-01-01T00:00:00+00:00"
        total, changed = save(db, domain, items, seen_at=at,
                              anomalies=bad, metadata=completion.metadata)
        if partial:
            status = "parcial"
            log(f"{domain}: lectura incompleta ({len(items)} productos): no se usa para marcar faltantes fuera de marcas completas")
        elif not total:
            status = "vacía"
    except Exception as e:
        status, error = "error", str(e)[:500]
        log(f"{domain}: ERROR {e}")
    if total:
        db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", ("scraped:" + domain, now()))
    db.execute("INSERT INTO scrape_run VALUES(?,?,?,?,?,?,?,?,?)",
               (run, domain, started, round(time.monotonic() - t0, 1), status, total, changed, len(bad), error))
    db.commit()
    if status != "error":
        log(f"{domain}: {total} variantes, {changed} con cambios" + (f", {len(bad)} precios anómalos" if bad else ""))
    for title, why in bad[:5]:
        log(f"{domain}: precio anómalo ({why}): {title}")


def collect(source):
    """Materializa ofertas y conserva el return del generador (list() lo pierde).

    Una excepción sin capturar descarta toda la lectura; adaptadores antiguos
    que retornan None mantienen su contrato.
    """
    items, iterator = [], iter(source)
    while True:
        try:
            items.append(next(iterator))
        except StopIteration as end:
            return items, end.value if isinstance(end.value, ScrapeCompletion) else ScrapeCompletion()


def report(db):
    """La última lectura de cada tienda, para revisar de un vistazo qué falló, cuándo y cuánto tardó."""
    rows = db.execute("""SELECT store, started, status, seconds, items, changed, anomalies, error FROM scrape_run r
                         WHERE started = (SELECT MAX(started) FROM scrape_run WHERE store = r.store) ORDER BY store""").fetchall()
    if not rows:
        return print("Todavía no hay corridas registradas.")
    for store, started, status, secs, items, changed, bad, error in rows:
        when = datetime.fromisoformat(started).astimezone().strftime("%d-%m %H:%M")
        print(f"{store:28} {when}  {status:8} {secs:7.1f} s  {items or 0:5} prod.  {changed or 0:5} cambios  {bad or 0:3} anómalos"
              + (f"  {error}" if error else ""))


if __name__ == "__main__":
    if "--estado" in sys.argv:
        report(connect(DB))
        sys.exit()
    daily = "--diario" in sys.argv
    sys.argv = [a for a in sys.argv if a != "--diario"]
    if daily and done_today(connect(DB)):
        log("scrape: ya hubo una corrida completa hoy, se omite")
        sys.exit()
    if sys.platform == "win32":  # que Windows no suspenda el PC por inactividad a media corrida (se libera al terminar el proceso)
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    log("scrape: inicio")
    started = now()
    db = connect(DB)
    def fx():
        try:
            log("dólar observado: %s = $%s" % update_fx(db))
            return True
        except Exception as e:
            log(f"dólar: ERROR {e}")
            return False
    fx_ok = fx()
    for domain in sys.argv[1:] or [d for d in STORES if d not in PAUSED]:
        scrape_store(db, domain, started)
    if not fx_ok:  # mindicador.cl a veces no responde (timeouts sueltos); tras una corrida larga casi siempre ya volvió
        fx()
    if not sys.argv[1:]:
        try:  # descripciones de los sitios oficiales de las marcas, una vez por semana (no son ofertas: ver scrapers/brand_text.py)
            brand_text.refresh(db)
        except Exception as e:
            log(f"textos de las marcas: ERROR {e}")
    if not sys.argv[1:]:  # corrida completa terminada: una tienda que no se pudo leer en ella queda "sin conexión" (ver Catalog.stale)
        db.execute("INSERT OR REPLACE INTO meta VALUES('run:done', ?)", (started,))
        db.commit()
        publish_db.publish()  # no hace nada sin data/publish.json y nunca lanza
    log("scrape: fin")
