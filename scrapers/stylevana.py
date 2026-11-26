"""Stylevana (Magento, tienda `en_US` en USD): parseo puro de los listados por marca (sin red ni base de datos) y el adaptador `stylevana()`.

Solo se leen páginas de marca (`/en_US/brands/<marca>.html?product_list_limit=36&p=N`; 36 es una de las opciones que ofrece su propio
selector de "12 / 24 / 36"). Su robots.txt bloquea `*/rest/V1/`, `*/ajax/`, `*/quickview/`, `*/catalogsearch/result/` y `*/checkout/`;
nada de eso se usa. Se lee `en_US` y no `es_LATAM` porque ahí los precios salen en pesos y las ofertas internacionales de Yumori van en
USD (ver docs/scraping/stores.md). El listado no trae stock: Magento solo muestra lo que está a la venta.
"""
import html
import re
import sqlite3
import time
import urllib.error
from datetime import datetime, timedelta, timezone

from db import DB
from match import NOT_BRANDS, words
from scrapers.common import ScrapeCompletion
from scrapers.http import Blocked, get, log

BASE = "https://www.stylevana.com/en_US"
PAGE_SIZE = 36  # productos por página (12, 24 o 36 en su selector)
CARD = re.compile(r'data-container="product-grid" data-product-id="(\d+)" data-name="([^"]*)"(.*?)'
                  r'(?=data-container="product-grid" data-product-id="|</ol>|\Z)', re.S)
BRAND = re.compile(r'data-ui-id="page-title-wrapper"\s*>([^<]+)<')
MULTI = re.compile(r"(\d\s?(?:ml|g))\s*\*\s*([2-9]|\d\d)ea\b", re.I)  # "Twin Pack 50ml*2ea": N unidades que el título no marca como pack
TOTAL = re.compile(r'of\s*<span class="toolbar-number">(\d+)</span>\s*results')


def cents(s):
    return round(float(s) * 100)


def parse_listing(page, vendor=None):
    """-> (ofertas, total de resultados de la marca). Ofertas = dicts compatibles con db.save, precios en centavos de USD.
    `vendor`: la marca como la escriben las tiendas chilenas (AMPLEN y no "ample:n"); si falta, la del título de la página."""
    brand = BRAND.search(page)
    vendor = vendor or (html.unescape(brand.group(1)).strip() if brand else None)
    out = []
    for pid, name, body in CARD.findall(page):
        price = re.search(r'data-price-amount="([\d.]+)"\s+data-price-type="finalPrice"', body)
        if not price or not cents(price.group(1)):  # sin precio o a 0 (regalos): no es una oferta
            continue
        was = re.search(r'data-price-amount="([\d.]+)"\s+data-price-type="rrpPrice"', body)
        url = re.search(r'class="product-item-link"\s+href="([^"]+)"', body)
        img = re.search(r'data-original="(https://[^"]+)"', body)
        sku = re.search(r'data-product-sku="([^"]+)"', body)
        now = cents(price.group(1))
        out.append(dict(
            ext_id=pid, sku=sku.group(1) if sku else None,
            title=" ".join(MULTI.sub(r"\1 (\2ea) Set", html.unescape(name)).replace(" - ", " ").split()),  # "COSRX - Snail Essence - 100ml"
            # -> "COSRX Snail Essence 100ml"; "50ml*2ea" -> "50ml (2ea) Set", como ya escribe Stylevana sus sets (si no, se cruzaría con el suelto)
            variant=None, vendor=vendor,
            url=html.unescape(url.group(1)) if url else f"{BASE}/catalog/product/view/id/{pid}", image=img.group(1) if img else None,
            price=now, compare_at=cents(was.group(1)) if was and cents(was.group(1)) > now else None,
            available=1,  # el listado solo muestra productos a la venta
            currency="USD",
        ))
    total = TOTAL.search(page)
    return out, int(total.group(1)) if total else len(out)


def brand_url(slug, pn):
    return f"{BASE}/brands/{slug}.html?product_list_limit={PAGE_SIZE}&p={pn}"


# Marca (vendor sin símbolos ni mayúsculas) -> slug en Stylevana, cuando no es el slug simple. Salen de su sitemap.
SLUGS = {"romnd": "romand", "amplen": "ample-n", "lilybyred": "lilybyred", "centellian24": "centellian-24", "tiam": "tia-m",
         "ksecret": "ksecret", "immeme": "i-m-meme"}


def slug_of(vendor):
    key = re.sub(r"[^a-z0-9]", "", vendor.lower())
    return SLUGS.get(key) or re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", vendor.lower())).strip("-")


STYLEVANA_TOP = 40  # marcas de nuestro catálogo que se buscan (las de más productos); no todas caben en una corrida
STYLEVANA_MAX_PAGES = 10  # 360 productos por marca como tope de seguridad
STYLEVANA_MAX_REQUESTS = 36  # tope por corrida: no se empieza una marca nueva al pasarlo. 36 x ~22 s = ~13 min
STYLEVANA_DELAY = 20  # segundos entre páginas (~1,2 MB c/u)
NOT_FOUND_DAYS = 30  # una marca que Stylevana no tiene (404) no se vuelve a pedir en este plazo


def stylevana(domain):
    """Listados por marca en USD, rotados por antigüedad dentro del presupuesto."""
    db = sqlite3.connect(DB, timeout=60)
    vendors = db.execute("SELECT vendor FROM listing WHERE currency='CLP' AND vendor IS NOT NULL "
                         "GROUP BY lower(vendor) ORDER BY count(*) DESC").fetchall()
    dead = dict(db.execute("SELECT substr(key, 14), value FROM meta WHERE key LIKE 'stylevana404:%'"))
    read = dict(db.execute("SELECT substr(key, 11), value FROM meta WHERE key LIKE 'stylevana:%'"))
    read.update(db.execute("SELECT substr(key, 20), value FROM meta WHERE key LIKE 'stylevana_observed:%'"))
    db.close()
    limit = (datetime.now(timezone.utc) - timedelta(days=NOT_FOUND_DAYS)).isoformat(timespec="seconds")
    chosen = {}
    for (vendor,) in vendors:
        key = re.sub(r"[^a-z0-9]", "", words(vendor))
        if key and key not in NOT_BRANDS and key not in chosen and dead.get(key, "") < limit:
            chosen[key] = vendor
        if len(chosen) == STYLEVANA_TOP:
            break
    log(f"stylevana: {len(chosen)} marcas candidatas, tope de {STYLEVANA_MAX_REQUESTS} solicitudes")
    done, missing, requests, metadata = [], [], 0, []
    partial = False
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for key in sorted(chosen, key=lambda k: read.get(k, "")):
        vendor = chosen[key]
        if requests >= STYLEVANA_MAX_REQUESTS:
            partial = True
            break
        slug = slug_of(vendor)
        try:
            complete, seen = False, set()
            for pn in range(1, STYLEVANA_MAX_PAGES + 1):
                page = get(brand_url(slug, pn), tries=1, text=True)
                items, total = parse_listing(page, vendor)
                requests += 1
                if pn == 1:
                    metadata.append(("stylevana_observed:" + key, ts))
                if pn == 1 and requests - 1 + min(-(-total // PAGE_SIZE), STYLEVANA_MAX_PAGES) > STYLEVANA_MAX_REQUESTS:
                    partial = True  # la marca completa no cabe: se conserva el presupuesto anterior
                    log(f"stylevana {vendor}: {total} productos no caben en el tope de la corrida, se salta")
                    time.sleep(STYLEVANA_DELAY)
                    break
                yield from items
                seen.update(i["ext_id"] for i in items)
                time.sleep(STYLEVANA_DELAY)
                if not items or pn * PAGE_SIZE >= total:
                    # Sin contador o con tarjetas perdidas no hay prueba de cobertura.
                    complete = TOTAL.search(page) is not None and len(seen) >= total
                    break
            if complete:
                done.append(key)
                metadata.append(("stylevana:" + key, ts))
            else:
                partial = True
        except Blocked as e:  # nos pidieron parar: se corta toda la corrida y se guarda lo ya leído
            log(f"stylevana: {e}. Se detiene hasta la próxima corrida ({len(done)} marcas completas en esta, {requests} solicitudes)")
            return ScrapeCompletion(True, tuple(metadata))
        except Exception as e:  # una marca que falla no debe perder las demás
            requests += 1
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                missing.append(key)  # Stylevana no tiene esa marca (o su slug es otro): no se insiste
                metadata.append(("stylevana404:" + key, ts))
                metadata.append(("stylevana_observed:" + key, ts))
            else:
                log(f"stylevana {vendor}: ERROR {e}")
            partial = True
            time.sleep(STYLEVANA_DELAY)
    log(f"stylevana: {len(done)} marcas leídas, {len(missing)} sin página, {requests} solicitudes")
    return ScrapeCompletion(partial, tuple(metadata))
