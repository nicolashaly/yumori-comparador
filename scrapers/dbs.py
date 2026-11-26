"""DBS Beauty Store (Magento): parseo puro de las páginas de marca (sin red ni base de datos) y el adaptador `dbs()`.

Su robots.txt veta `/*?` (cualquier parámetro: nada de `?p=`, `product_list_limit` ni filtros), `/catalog/`, `/index.php/`, `/checkout/`,
`/customer/`, `/review/` y `/sendfriend/`. Solo se piden las páginas de marca con URL limpia (`/marcas/<marca>`), que entregan toda la marca
en una solicitud (el encabezado dice "32 artículos" y trae 32 tarjetas; en SKIN1004 anuncia 22 y trae 21, una tarjeta oculta). Si una marca trae
menos tarjetas de las que anuncia se avisa en el registro, sin paginar (sería pedir un parámetro vetado). Ninguna marca se pasa de una página.
Una marca sin productos (Elizavecca y Unleashia desde noviembre de 2026) no trae contador, sino el aviso `EMPTY`: es una lectura completa.
Sin tarjetas ni ese aviso, la marca queda "sin leer" (lectura parcial), por si cambió el HTML.

Cada tarjeta (`li.product-item`) trae: id de producto, marca (en mayúsculas, no va dentro del título), nombre, descripción corta, precio
(`data-price-amount`, CLP), "Regular Price" tachado (`old-price`), imagen (lazy: `data-src`) y el formulario de agregar al carro. No trae
SKU, EAN ni stock: Magento oculta los agotados del listado, así que cada tarjeta con formulario cuenta como disponible. `gtin` queda en None.
"""
import html
import re
import time

from scrapers.common import ScrapeCompletion, images_of
from scrapers.http import Blocked, get, log

BASE = "https://dbs.cl"
DELAY = 10  # segundos entre páginas (cada una pesa ~0,5 MB)
# Solo marcas asiáticas y las de dermocosmética que ya tenemos (DERMO_BRANDS). DBS vende además perfumería y maquillaje occidental,
# que no es de Yumori: una marca no asiática ni dermocosmética aparecería como "asiática" porque DBS no es farmacia.
BRANDS = ["anua", "aestura", "beauty-of-joseon", "cosrx", "dr-althea", "elizavecca", "frudia", "innisfree", "isntree", "laneige", "leaders",
          "medicube", "mise-en-scene", "mizon", "skin1004", "some-by-mi", "tocobo", "torriden", "unleashia", "vt-cosmetics",
          "apivita", "nuxe"]

TILE = "<li class=\"item product product-item\">"
EMPTY = "message info empty"  # "No podemos encontrar productos que coincida con la selección": la marca existe pero hoy no tiene productos (sin contador de artículos)
TOTAL = re.compile(r'toolbar-number">(\d+)</span>\s*art')
NAME = re.compile(r'product-item-name"><a href="([^"]+)"[^>]*>([^<]+)</a>')
BRAND = re.compile(r'product-attribute-label"><a [^>]*>([^<]*)</a>')
SHORT = re.compile(r'product-short-description"><a [^>]*>([^<]*)</a>')
PRICE = re.compile(r'id="product-price-(\d+)"\s+data-price-amount="([\d.]+)"')
OLD = re.compile(r'id="old-price-\d+"\s+data-price-amount="([\d.]+)"')
IMAGE = re.compile(r'<img[^>]+class="product-image-photo[^"]*"[^>]*\sdata-src="([^"]+)"')


def parse_listing(page):
    """-> (ofertas, anunciados). Ofertas = dicts compatibles con db.save, precios en pesos. `anunciados`: cuántos productos dice la página
    que tiene la marca (None si no lo dice): si es más que len(ofertas), puede faltar alguno."""
    total = TOTAL.search(page)
    out = []
    for t in page.split(TILE)[1:]:
        name, price = NAME.search(t), PRICE.search(t)
        if not name or not price:
            continue
        old, brand, short, img = OLD.search(t), BRAND.search(t), SHORT.search(t), IMAGE.search(t)
        pid, price = price.group(1), round(float(price.group(2)))
        was = round(float(old.group(1))) if old else None
        image = html.unescape(img.group(1)) if img else None
        out.append(dict(
            ext_id=pid, sku=None, title=" ".join(html.unescape(name.group(2)).split()), variant=None,
            vendor=html.unescape(brand.group(1)).strip() or None if brand else None, url=name.group(1), image=image, images=images_of([image]),
            price=price, compare_at=was if was and was > price else None, available=int('data-role="tocart-form"' in t), currency="CLP",
            gtin=None, description=" ".join(html.unescape(short.group(1)).split()) or None if short else None,
        ))
    return out, int(total.group(1)) if total else None


def dbs(domain):
    """Las marcas asiáticas y de dermocosmética de DBS, una solicitud por marca (`BRANDS`)."""
    seen, short, missing = set(), [], []
    for n, slug in enumerate(BRANDS):
        if n:
            time.sleep(DELAY)
        try:
            page = get(f"{BASE}/marcas/{slug}", tries=1, text=True)
            items, claimed = parse_listing(page)
        except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
            log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(seen)} productos leídos)")
            missing.append(slug)
            break
        except Exception as e:  # una marca que falla (404 si DBS la sacó) no debe perder las demás
            log(f"{domain} /marcas/{slug}: ERROR {e}")
            missing.append(slug)
            continue
        if not items and EMPTY not in page:  # ni tarjetas ni aviso de marca vacía: DBS cambió el HTML, no se da la marca por vaciada
            log(f"{domain} /marcas/{slug}: sin tarjetas ni aviso de marca vacía (¿cambió el HTML de DBS?)")
            missing.append(slug)
            continue
        if claimed is not None and claimed > len(items):
            short.append(f"{slug} ({len(items)} de {claimed})")
        new = [i for i in items if i["ext_id"] not in seen]
        seen.update(i["ext_id"] for i in new)
        log(f"{domain} /marcas/{slug}: " + (f"{len(items)} productos" + (f" de {claimed} anunciados" if claimed not in (None, len(items)) else "")
                                              if items else "0 productos (DBS muestra la marca vacía)"))
        yield from new
    if short:
        log(f"{domain}: marcas que anuncian más productos de los que traen (no se pagina: su robots.txt veta los parámetros): {', '.join(short)}")
    if missing:
        log(f"{domain}: marcas sin leer: {', '.join(missing)}")
    return ScrapeCompletion(bool(short or missing))
