"""Tiendas Next.js que traen los productos en `<script id="__NEXT_DATA__">`: Falabella (páginas de marca) y Farmaloop (categoría de
dermocosmética). Parseo puro (sin red ni base de datos) más un adaptador por tienda: `falabella()` y `farmaloop()`.

Falabella: solo `/falabella-cl/brand/<MARCA>` (su robots.txt solo veta basket, myaccount, checkout y orders), con `?page=N` (48 por página).
Se incluye solo lo que vende y despacha Falabella (`sellerId == FALABELLA_CHILE`): los vendedores de terceros del marketplace quedan fuera
(precios y productos que nadie de la tienda garantiza, y el sitio no puede decir quién vende). Los packs (`productType == BUNDLE`) tampoco.
El JSON del listado no trae el precio CMR (solo las cuotas sin interés con CMR): `card_price` queda en None. Sin stock ni EAN en el listado.

Farmaloop: solo las páginas de categoría (`/categoria/dermocosmetica/` y sus seis subcategorías). Su paginación es del navegador (`?page=`,
`?pagina=` y `?p=` se ignoran y devuelven siempre los mismos 15 productos), así que cada página aporta solo los 15 primeros: lectura parcial
y así se avisa en el registro. No se pide ninguna ficha ni se usa su API interna. Su robots.txt veta `/productos`; las fichas reales viven en
`/products/<slug>/` y solo se guarda ese enlace para la persona, nunca se pide. Ojo con el precio: Farmaloop vende lotes cercanos a vencer con
descuento ("mientras más cerca al vencimiento más bajo el precio"), y `bestPrice` es el del lote más corto. Aquí solo cuenta el lote más barato
con stock que vence a MIN_MONTHS meses o más; si ninguno cumple, el producto no se ofrece (no es el mismo producto que en otra tienda).
El precio "normal" del lote es el `compare_at`. Trae EAN (`ean`), que va a `gtin`.
"""
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

from scrapers.common import ScrapeCompletion, gtin, images_of
from scrapers.http import Blocked, get, log
from scrapers.sfcc import BRANDS, NOT_COSMETICS, norm_brand, strip_brand  # mismas reglas de medicamentos, marcas y marca en el título

NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def next_data(page):
    """HTML -> el `pageProps` del JSON de Next.js. ValueError si la página no lo trae (otra plantilla, bloqueo o cambio del sitio)."""
    m = NEXT_DATA.search(page)
    if not m:
        raise ValueError("la página no trae __NEXT_DATA__")
    return json.loads(m.group(1))["props"]["pageProps"]


def pretty_brand(name):
    """Marca en mayúsculas como la escribe Falabella ("LA ROCHE POSAY", "APIVITA") -> como las demás tiendas. SVR y otras siglas de 3 letras quedan."""
    b = norm_brand(name)
    return b.title() if b and b.isupper() and len(b) > 3 else b


# ---------------------------------------------------------------- Falabella

FALABELLA = "https://www.falabella.com/falabella-cl/brand/"
FALABELLA_DELAY = 12  # segundos entre páginas (cada una pesa ~2 MB); un 403 en la prueba del 2026-10-04 con 6 s de pausa
MAX_PAGES = 6  # por marca: Eucerin, la más grande, necesita 4 (166 productos)
OFFICIAL_SELLER = "FALABELLA_CHILE"
# Marcas de dermocosmética (nombre tal como lo escribe Falabella en la URL), probadas en vivo el 2026-10-04. Heliocare no trae productos, y
# Bioderma, SVR y Mustela solo los venden terceros (todos se descartan), así que no se piden. Filorga dio 403 en la prueba: tampoco se pide.
DERMO_PAGES = ["EUCERIN", "LA%20ROCHE%20POSAY", "VICHY", "AVENE", "CETAPHIL", "ISDIN", "URIAGE", "DUCRAY", "CERAVE", "APIVITA", "NUXE"]
# Marcas asiáticas con página de marca en su sitemap de marcas (2026-10-04). Sin probar en vivo: la prueba se cortó con un 403. Una página sin
# productos se lee como vacía y no estorba; si alguna trae productos de maquillaje o de terceros, se quita de aquí.
ASIAN_PAGES = ["LANEIGE", "COSRX", "SKIN1004", "BEAUTY%20OF%20JOSEON", "ANUA", "ROUND%20LAB", "TOCOBO", "TORRIDEN", "MEDICUBE", "NUMBUZIN",
               "KLAIRS", "MIXSOON", "ISNTREE", "NEOGEN", "MISSHA", "INNISFREE", "ETUDE%20HOUSE", "BANILA%20CO", "TIRTIR", "SULWHASOO", "ABIB",
               "APLB", "PURITO", "BIODANCE", "AESTURA", "BELIF", "SUNGBOON", "TONYMOLY"]
TRAILING = re.compile(r"(?:\s+(?:de|del|para|con|-|–))+\s*$", re.I)  # Falabella corta títulos a mitad ("Desodorante Power 3 50ml de")


def clp(p):
    """['23.990'] -> 23990"""
    s = re.sub(r"\D", "", (p or [""])[0])
    return int(s) if s else None


def parse_falabella(page):
    """-> (ofertas, descartados, paginas). Ofertas = dicts compatibles con db.save, precios en pesos. `paginas`: cuántas páginas tiene la marca."""
    pp = next_data(page)
    out, dropped = [], defaultdict(list)
    for r in pp.get("results") or []:
        title = TRAILING.sub("", " ".join((r.get("displayName") or "").split()))
        if r.get("sellerId") != OFFICIAL_SELLER:
            dropped["vendedor de terceros"].append(title)
            continue
        if r.get("productType") != "REGULAR":
            dropped["pack"].append(title)
            continue
        prices = {p["type"]: clp(p["price"]) for p in r.get("prices") or [] if not p.get("crossed")}
        price = prices.get("internetPrice") or prices.get("eventPrice")
        was = next((clp(p["price"]) for p in r.get("prices") or [] if p.get("crossed")), None)
        rule = next((n for n, rx in NOT_COSMETICS.items() if rx.search(title)), None)
        if not title or not price or not r.get("url"):
            dropped["sin precio o nombre"].append(title or str(r.get("productId")))
            continue
        if rule:
            dropped[rule].append(title)
            continue
        brand = pretty_brand(r.get("brand"))
        pics = [u for u in r.get("mediaUrls") or [] if "NoImage" not in u]
        out.append(dict(
            ext_id=str(r["productId"]), sku=str(r.get("skuId") or r["productId"]), title=strip_brand(title, brand), variant=None, vendor=brand,
            url=r["url"], image=pics[0] if pics else None, images=images_of(pics), price=price, compare_at=was if was and was > price else None,
            available=1, currency="CLP", gtin=None, card_price=None, card_name=None,  # sin campo de stock en el listado: lo que se muestra se vende
        ))
    pg = pp.get("pagination") or {}
    pages = -(-pg.get("count", 0) // pg["perPage"]) if pg.get("perPage") else 1
    return out, dict(dropped), pages


def falabella(domain):
    """Dermocosmética y cosmética asiática de Falabella desde sus páginas de marca, con pausa de 12 s. Un 403 o 429 corta la tienda."""
    seen, dropped, incomplete, n = set(), defaultdict(list), [], 0
    for brand in DERMO_PAGES + ASIAN_PAGES:
        page_no, pages = 1, 1
        while page_no <= min(pages, MAX_PAGES):
            if n:
                time.sleep(FALABELLA_DELAY)
            n += 1
            url = FALABELLA + brand + (f"?page={page_no}" if page_no > 1 else "")
            try:
                items, drop, pages = parse_falabella(get(url, tries=1, text=True))
            except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
                log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(seen)} productos leídos)")
                return _falabella_report(domain, dropped, incomplete + [url])
            except Exception as e:  # una página que falla no debe perder las demás
                log(f"{domain} {url}: ERROR {e}")
                incomplete.append(url)
                break
            for rule, titles in drop.items():
                dropped[rule] += titles
            new = [i for i in items if i["ext_id"] not in seen]
            seen.update(i["ext_id"] for i in new)
            log(f"{domain} {brand} p{page_no}/{pages}: {len(items)} productos ({len(new)} nuevos)")
            yield from new
            if not drop and not items:  # marca sin productos
                break
            page_no += 1
        if pages > MAX_PAGES:
            incomplete.append(brand)
    return _falabella_report(domain, dropped, incomplete)


def _falabella_report(domain, dropped, incomplete):
    for rule, titles in dropped.items():
        log(f"{domain}: descartados por '{rule}': {len(titles)} (por ejemplo: {'; '.join(titles[:3])})")
    if incomplete:
        log(f"{domain}: {len(incomplete)} páginas sin leer completas: {', '.join(incomplete)}")
    return ScrapeCompletion(bool(incomplete))


# ---------------------------------------------------------------- Farmaloop

FARMALOOP = "https://www.farmaloop.cl"
FARMALOOP_DELAY = 10
MIN_MONTHS = 6  # vencimiento mínimo del lote cuyo precio se muestra (ver el docstring del módulo)
FARMALOOP_PAGES = ["/categoria/dermocosmetica/", *(f"/categoria/dermocosmetica/{s}/" for s in
                                                  ("rostro", "proteccion-solar", "cuerpo", "capilar", "infantil", "belleza"))]
# Lo que Farmaloop mezcla en Dermocosmética y es medicamento (principio activo en el nombre), además de NOT_COSMETICS y de la receta.
MEDICINE = re.compile(r"\b(?:ketoconazol|minoxidil|alopek|tricoxane|clotrimazol|hidrocortisona|betametasona|clobetasol|adapaleno|tretino[ií]na|"
                      r"soluci[oó]n t[oó]pica)\b", re.I)
# Farmaloop no trae marca: se busca en el nombre (o en el laboratorio) entre las de dermocosmética y las que Ahumada también escribe.
FARMALOOP_BRANDS = ["ISDINCEUTICS", "ISDIN", "Eucerin", "La Roche-Posay", "Vichy", "Avène", "Cetaphil", "Uriage", "Ducray", "CeraVe", "Bioderma",
                    "Apivita", "Heliocare", "Nuxe", "SVR", "Sesderma", "Filorga", "A-Derma", "Mustela", "Klorane", "Nivea", "Isispharma"]


def plain(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).split())


def brand_of(name, lab):
    text = f" {plain(name)} {plain(lab)} "
    return next((norm_brand(b) for b in FARMALOOP_BRANDS if f" {plain(b)} " in text), None)


def lot_price(batches, today):
    """-> (precio, normal) del lote más barato con stock que vence al menos MIN_MONTHS meses después de `today`; (None, None) si no hay."""
    limit = (today + timedelta(days=round(MIN_MONTHS * 30.4))).isoformat()
    ok = [b for b in batches if b.get("active") and (b.get("stock") or 0) > 0 and (b.get("expireDate") or "")[:10] >= limit and b.get("settlementPrice")]
    b = min(ok, key=lambda b: b["settlementPrice"], default=None)
    return (b["settlementPrice"], b.get("normalPrice")) if b else (None, None)


def parse_farmaloop(page, today=None):
    """-> (ofertas, descartados). Ofertas = dicts compatibles con db.save, precios en pesos."""
    today = today or date.today()
    out, dropped = [], defaultdict(list)
    for r in next_data(page).get("products") or []:
        name = " ".join((r.get("fullName") or "").split())
        if not name or not r.get("sku") or not r.get("slug"):
            dropped["sin nombre o enlace"].append(name or str(r.get("sku")))
            continue
        rx_type = r.get("prescriptionType") or ""
        rule = "receta" if r.get("requiresPrescription") or (rx_type and "sin receta" not in rx_type.lower()) else \
            "medicamento" if MEDICINE.search(name) else next((n for n, rx in NOT_COSMETICS.items() if rx.search(name)), None)
        if rule:
            dropped[rule].append(name)
            continue
        in_stock = bool(r.get("availableForSale"))
        price, was = lot_price(r.get("batchs") or [], today) if in_stock else (None, None)
        if in_stock and not price:
            dropped[f"vence en menos de {MIN_MONTHS} meses"].append(name)
            continue
        price, was = price or r.get("basePrice"), was or r.get("basePrice")  # sin stock: el precio normal, marcado como no disponible
        if not price:
            dropped["sin precio"].append(name)
            continue
        brand = brand_of(name, r.get("laboratoryName"))
        out.append(dict(
            ext_id=str(r["sku"]), sku=str(r["sku"]), title=strip_brand(name, brand).strip(" -–—"), variant=None, vendor=brand,
            url=f"{FARMALOOP}/products/{r['slug']}/", image=r.get("photoURL"), images=images_of([r.get("photoURL")]), price=price,
            compare_at=was if was and was > price else None, available=int(in_stock), currency="CLP", gtin=gtin(r.get("ean")),
            card_price=None, card_name=None,
        ))
    return out, dict(dropped)


def farmaloop(domain):
    """Dermocosmética de Farmaloop: 7 páginas de categoría (15 productos cada una, sin paginación posible), con pausa de 10 s."""
    seen, dropped, failed = set(), defaultdict(list), []
    for n, path in enumerate(FARMALOOP_PAGES):
        if n:
            time.sleep(FARMALOOP_DELAY)
        try:
            items, drop = parse_farmaloop(get(FARMALOOP + path, tries=1, text=True))
        except Blocked as e:
            log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(seen)} productos leídos)")
            break
        except Exception as e:
            log(f"{domain} {path}: ERROR {e}")
            failed.append(path)
            continue
        for rule, titles in drop.items():
            dropped[rule] += titles
        new = [i for i in items if i["ext_id"] not in seen]  # la categoría general repite lo de las subcategorías
        seen.update(i["ext_id"] for i in new)
        log(f"{domain} {path}: {len(items)} productos ({len(new)} nuevos)")
        yield from new
    log(f"{domain}: lectura parcial por diseño: cada página muestra solo 15 y su paginación no se puede pedir ({len(seen)} productos distintos)")
    for rule, titles in dropped.items():
        log(f"{domain}: descartados por '{rule}': {len(titles)} (por ejemplo: {'; '.join(titles[:3])})")
    if failed:
        log(f"{domain}: {len(failed)} páginas sin leer: {', '.join(failed)}")
    return ScrapeCompletion(True)  # ventana de 15 productos por página, sin paginación
