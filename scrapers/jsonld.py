"""Tiendas que publican datos schema.org (JSON-LD): Tiendanube y Jumpseller."""
import html
import json
import re
import time

from scrapers.common import ScrapeCompletion, gtin, images_of, short_title, text_of
from scrapers.http import DELAY, Blocked, get, log


def jsonld_nodes(page, types=("Product",)):
    """Nodos schema.org (bloques JSON-LD) de una página con alguno de esos @type, sueltos o dentro de un @graph."""
    out = []
    for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for x in data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []:
            if isinstance(x, dict) and x.get("@type") in types:
                out.append(x)
    return out


def jsonld_products(page):
    """Productos schema.org (bloques JSON-LD) de una página, sueltos o dentro de un @graph."""
    return jsonld_nodes(page)


def jsonld_gtin(p, off):
    """Código de barras canónico (ver gtin()) de un producto schema.org o de su oferta: gtin13/gtin12/gtin8/gtin14/gtin y productID
    (Jumpseller lo usa para el código; gtin() descarta cualquier productID que no sea un código válido). None si no hay."""
    return next((g for k in ("gtin13", "gtin12", "gtin8", "gtin14", "gtin", "productID") for src in (p, off) if (g := gtin(src.get(k)))), None)


def item_from_jsonld(p, url=None):
    """Producto schema.org -> item de save() en CLP, o None si no trae precio."""
    off = p.get("offers")
    off = off[0] if isinstance(off, list) else off or {}
    if not off.get("price"):
        return None
    brand = p.get("brand")
    brand = html.unescape((brand.get("name") if isinstance(brand, dict) else brand) or "") or None
    name = html.unescape(p["name"])
    if brand and name.lower().startswith(brand.lower() + " - "):
        name = name[len(brand) + 3:]  # "Marca - Nombre" -> "Nombre"
    imgs = p.get("image")
    imgs = [u for u in (imgs if isinstance(imgs, list) else [imgs]) if isinstance(u, str) and u]
    image = imgs[0] if imgs else None
    rating = p.get("aggregateRating") or {}
    url = url or off.get("url") or p.get("url")
    # Jumpseller pone el código de barras en productID (Tiendanube no publica ninguno): ver jsonld_gtin()
    return dict(gtin=jsonld_gtin(p, off),
        ext_id=str(p.get("sku") or url), sku=p.get("sku") or None, title=name, variant=None, vendor=brand, url=url, image=image,
        rating=float(rating["ratingValue"]) if rating.get("reviewCount") else None,
        reviews=int(rating["reviewCount"]) if rating.get("reviewCount") else None,
        price=round(float(off["price"])), compare_at=None, available=int("InStock" in str(off.get("availability"))),
        description=text_of(p.get("description")), images=images_of(imgs),
    )


def tiendanube(domain):
    """Tiendanube: el listado /productos/?page=N ya trae los datos schema.org de cada producto (unos 60 por página)."""
    page = 1
    while True:
        prods = jsonld_products(get(f"https://{domain}/productos/?page={page}", text=True))
        if not prods:
            return
        for p in prods:
            if item := item_from_jsonld(p):
                yield item
        page += 1
        time.sleep(DELAY)


JUMPSELLER_DELAY = 5  # segundos entre productos (1 consulta por ficha; era 2,5). Unnie tarda ~80 min


def jumpseller(domain):
    """Jumpseller: no hay listado con datos estructurados, así que se lee la página de cada producto que publica su sitemap."""
    urls = re.findall(r"<loc>([^<]+)</loc>", get(f"https://{domain}/sitemap.xml", text=True))
    partial = False
    for u in urls:
        if "/marcas/" in u or u.rstrip("/") == f"https://{domain}" or u.endswith("/contact"):
            continue
        time.sleep(JUMPSELLER_DELAY)
        try:
            prods = jsonld_products(get(u, text=True))
        except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
            log(f"{domain}: {e}. Se detiene hasta la próxima corrida")
            return ScrapeCompletion(True)
        except Exception:  # una página que falla (404...) no debe perder las demás
            partial = True
            continue
        if prods and (item := item_from_jsonld(prods[0], u)):
            item["title"] = short_title(html.unescape(prods[0]["name"]), item["vendor"])
            yield item
    return ScrapeCompletion(partial)
