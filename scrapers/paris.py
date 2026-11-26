"""Paris.cl (Cencosud, Next.js): dermocosmética desde las páginas de marca, sin red ni base de datos en el parseo (`parse_page`).

El HTML trae el listado completo de la página dentro del flujo de Next (`self.__next_f.push([1,"..."])`, clave `productData`): nombre, marca,
slug, vendedor, imágenes y dos precios (`regular` = el de lista y `offer` = el que se paga, solo si hay oferta). Más fiable que las tarjetas.

Límite que manda todo: **el HTML solo trae los primeros 30 productos de cada página** (`?page=2` y `?sortby=` se ignoran en el servidor:
devuelven los mismos 30; la paginación real la hace el navegador con la API de Constructor.io, que aquí no se usa). Una marca con 137 productos
(Eucerin) entrega 30, los más "recomendados" por Paris. Por eso la lectura es parcial por diseño: ver `docs/scraping/stores.md`.

Paris es tienda por departamentos y también marketplace (`sellers`: "Paris" o un vendedor externo, incluso otra tienda de nuestra lista).
Se aceptan solo las marcas de `scrapers.dermo.BRANDS` (dermocosmética); el resto de la categoría (capilar, tatuajes, perfumes) no se guarda. No trae stock,
EAN ni precio con tarjeta Cencosud (solo etiquetas de campaña en `collections`): `gtin` y `card_price` quedan en None y `available` en 1.
"""
import json
import time

from scrapers.common import ScrapeCompletion, images_of
from scrapers.dermo import brand_of
from scrapers.http import Blocked, get, log
from scrapers.sfcc import strip_brand

BASE = "https://www.paris.cl"
DELAY = 10  # segundos entre páginas (cada una pesa ~2,7 MB)
D = "/belleza/dermocosmetica/"
PAGES = [D + p + "/" for p in ("isdin", "la-roche-posay", "vichy", "eucerin", "avene", "cerave", "uriage", "cetaphil", "ducray", "sets-dermocosmetica",
                              "proteccion-solar")]  # las de marca enlazadas desde /belleza/dermocosmetica/; "cuerpo" (2.811) y "rostro/<marca>" no sirven
FLIGHT = "<script>self.__next_f.push([1,"


def flight(page):
    """Junta los trozos de texto del flujo de Next (cada `push([1,"..."])` es un literal JSON)."""
    dec, out, pos = json.JSONDecoder(), [], 0
    while (i := page.find(FLIGHT, pos)) >= 0:
        s, pos = dec.raw_decode(page, i + len(FLIGHT))
        out.append(s)
    return "".join(out)


def product_data(page):
    """-> el dict `productData` de la página. ValueError si no está (Paris cambió su estructura): la página cuenta como fallida."""
    s = flight(page)
    key = '"productData":{"statusCode"'
    i = s.find(key)
    if i < 0:
        raise ValueError("Paris: no está productData en el HTML")
    return json.JSONDecoder().raw_decode(s, i + len('"productData":'))[0]


def parse_page(page):
    """-> (ofertas, total de la categoría, descartados por marca). Ofertas = dicts compatibles con db.save, precios en pesos."""
    d = product_data(page)
    out, other = [], 0
    for p in d["products"]:
        v = p["masterVariant"]
        pr = v["prices"]
        regular = pr.get("regular", {}).get("value", {}).get("centAmount")
        price = pr.get("offer", {}).get("value", {}).get("centAmount") or regular
        brand = brand_of(p.get("brand"))
        if not price or not p.get("name") or not p.get("slug"):
            continue
        if not brand:
            other += 1
            continue
        imgs = [i["url"] for i in v.get("images") or []]
        out.append(dict(
            ext_id=p["id"], sku=v.get("sku") or p["id"], title=strip_brand(" ".join(p["name"].split()), brand), variant=None, vendor=brand,
            url=f"{BASE}/{p['slug']}.html", image=imgs[0] if imgs else None, images=images_of(imgs),
            price=price, compare_at=regular if regular and regular > price else None,
            available=1, currency="CLP", gtin=None, card_price=None, card_name=None,
        ))
    return out, d.get("total"), other


def paris(domain):
    """Dermocosmética de Paris: una solicitud por página de marca o categoría (solo salen los primeros 30 de cada una)."""
    seen, short = set(), []
    for n, path in enumerate(PAGES):
        if n:
            time.sleep(DELAY)
        try:
            items, total, other = parse_page(get(BASE + path, tries=1, text=True))
        except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
            log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(seen)} productos leídos)")
            break
        except Exception as e:  # una página que falla no debe perder las demás
            log(f"{domain} {path}: ERROR {e}")
            continue
        new = [i for i in items if i["ext_id"] not in seen]  # una marca sale en su página y en las de categoría
        seen.update(i["ext_id"] for i in new)
        if total and total > 30:
            short.append(f"{path} ({total})")
        log(f"{domain} {path}: {len(items)} productos de marcas dermo ({len(new)} nuevos), {other} de otras marcas descartados, categoría de {total}")
        yield from new
    if short:
        log(f"{domain}: lectura parcial por diseño, el HTML solo trae 30 por página; categorías con más: {', '.join(short)}")
    return ScrapeCompletion(True)  # la ventana de 30 no acredita la categoría completa
