"""YesStyle (HTML renderizado en el servidor): parseo puro de los listados (sin red ni base de datos) y el adaptador `yesstyle()`.

Solo se leen páginas de listado (`/en/<marca>/list.html/bpt.299_bid.<id>?pn=N`). Su robots.txt prohíbe la API de producto,
las búsquedas (`?q`) y las URLs con coma; nada de eso se usa.
"""
import html
import re
import sqlite3
import time
from datetime import datetime, timezone

from db import DB
from match import NOT_BRANDS, words
from scrapers.common import ScrapeCompletion
from scrapers.http import Blocked, get, log

BASE = "https://www.yesstyle.com"
PAGE_SIZE = 100  # productos por página de listado
CARD = re.compile(r'<a [^>]*itemContainer[^>]*href="(/en/([^"/]+)/info\.html/pid\.(\d+))"[^>]*>(.*?)</a>', re.S)
BRAND_URL = re.compile(r"^https://www\.yesstyle\.com/en/([^/]+)/list\.html/(bpt\.299_bid\.\d+)$")
PRICE = r"US\$(?:\xa0|&nbsp;|\s)*([\d,]+\.\d{2})"


def cents(s):
    return round(float(s.replace(",", "")) * 100)


def parse_listing(page):
    """-> lista de ofertas (dict compatible con db.save). Precios en centavos de USD; las tarjetas en otra moneda se omiten."""
    out = []
    for href, slug, pid, body in CARD.findall(page):
        now = re.search(rf"<b[^>]*>{PRICE}</b>", body)
        if not now:
            continue
        was = re.search(rf"<span[^>]*>{PRICE}</span>", body)
        img = next((u for u in re.findall(r'<img[^>]*\ssrc="(https://[^"]+)"', body) if not u.endswith(".svg")), None)
        brand = re.search(r"<span[^>]*>([^<]+)</span>\s*-\s*(?:<!-- -->)?", body)
        price = cents(now.group(1))
        out.append(dict(
            ext_id=pid, sku=None,
            title=" ".join(w.capitalize() if w.isalpha() else w for w in slug.replace("-", " ").split()),  # el slug viene en minúsculas;
            # se capitaliza cada palabra salvo las que traen números ("30ml"), que el resto del sitio ya muestra en minúsculas
            variant=None,
            vendor=html.unescape(brand.group(1)).strip() if brand else None,
            url=BASE + href, image=img,
            price=price, compare_at=cents(was.group(1)) if was and cents(was.group(1)) > price else None,
            available=1,  # el listado solo muestra productos a la venta
            currency="USD",
        ))
    return out


def brand_pages(sitemap_xml):
    """-> {marca sin símbolos ni guiones: (slug, 'bpt.299_bid.N')} desde brand_sitemap.xml."""
    pages = {}
    for loc in re.findall(r"<loc>([^<]+)</loc>", sitemap_xml):
        m = BRAND_URL.match(loc)
        if m:
            pages[m.group(1).replace("-", "")] = (m.group(1), m.group(2))
    return pages


def brand_url(slug, code, pn):
    return f"{BASE}/en/{slug}/list.html/{code}?pn={pn}"


YESSTYLE_TOP = 40  # marcas de nuestro catálogo que se buscan en YesStyle (las de más productos)
YESSTYLE_MAX_PAGES = 1  # 100 productos por página (los más vendidos). Cloudflare corta tras ~6 solicitudes por corrida:
# con 1 página por marca entran ~6 marcas por corrida en vez de 2 (más marcas, menos profundidad; decisión del usuario)
YESSTYLE_MAX_BRANDS = 4  # marcas por corrida. Con 45 s de pausa, el 429 llegaba siempre en la 7.ª solicitud (sitemap + 5 marcas, a diario del 2026-09-21
# al 2026-10-05): se para antes, con margen, para no llegar nunca al bloqueo. La rotación por antigüedad cubre las 40 marcas en ~10 corridas.
YESSTYLE_DELAY = 90  # segundos entre páginas (era 45). Antes: con 1 s y ~15 s respondió 429; con 20 s aguantó 6 páginas (~2 min)


def yesstyle(domain):
    """Precios en USD (centavos) de las marcas de nuestro catálogo, desde los listados por marca de YesStyle."""
    db = sqlite3.connect(DB, timeout=60)
    vendors = db.execute("SELECT vendor FROM listing WHERE currency='CLP' AND vendor IS NOT NULL "
                         "GROUP BY lower(vendor) ORDER BY count(*) DESC").fetchall()
    read = dict(db.execute("SELECT substr(key, 10), value FROM meta WHERE key LIKE 'yesstyle:%'"))
    read.update(db.execute("SELECT substr(key, 19), value FROM meta WHERE key LIKE 'yesstyle_observed:%'"))
    db.close()
    pages = brand_pages(get(f"{BASE}/brand_sitemap.xml", text=True))
    time.sleep(YESSTYLE_DELAY)  # el sitemap pesa ~850 KB: también cuenta para su límite de ritmo
    chosen = {}
    for (vendor,) in vendors:
        key = re.sub(r"[^a-z0-9]", "", words(vendor))
        if key in pages and key not in NOT_BRANDS and key not in chosen:
            chosen[key] = vendor
        if len(chosen) == YESSTYLE_TOP:
            break
    # Cloudflare corta tras unas pocas páginas por corrida: si siempre se partiera por la misma marca, las del final no se
    # leerían nunca. Se rota por visita, aunque su ventana de 100 no agote la marca.
    order = sorted(chosen, key=lambda k: read.get(k, ""))
    log(f"yesstyle: {len(chosen)} marcas encontradas de las {YESSTYLE_TOP} principales, {sum(k not in read for k in chosen)} nunca leídas")
    metadata, done = [], []
    partial = len(order) > YESSTYLE_MAX_BRANDS
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for key in order[:YESSTYLE_MAX_BRANDS]:
        slug, code = pages[key]
        try:
            complete = False
            for pn in range(1, YESSTYLE_MAX_PAGES + 1):
                page = get(brand_url(slug, code, pn), text=True)
                items = parse_listing(page)
                if pn == 1:
                    metadata.append(("yesstyle_observed:" + key, ts))
                yield from items
                time.sleep(YESSTYLE_DELAY)
                # Contar tarjetas originales: omitir un precio no prueba el fin.
                cards = len(CARD.findall(page))
                if 0 < cards < PAGE_SIZE and len(items) == cards:
                    complete = True
                    break
            if complete:
                done.append(key)
                metadata.append(("yesstyle:" + key, ts))
            else:
                partial = True
        except Blocked as e:
            log(f"yesstyle: {e}. Se detiene hasta la próxima corrida ({len(done)} marcas completas en esta)")
            return ScrapeCompletion(True, tuple(metadata))
        except Exception as e:
            partial = True
            log(f"yesstyle {chosen[key]}: ERROR {e}")
    return ScrapeCompletion(partial, tuple(metadata))
