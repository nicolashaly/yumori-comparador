"""Lee la nota de cada producto en tiendas Shopify que usan Judge.me y la guarda en listing.rating/reviews.

Es lento (1 request por producto, ~1 hora en total): correr aparte y de vez en cuando, no junto con scrape.py.
De la misma página (cero requests nuevos) saca el código de barras (GTIN) del producto principal, que Shopify no trae en products.json.
Uso: python ratings.py [dominio ...] [--limit N]   (--limit: solo las primeras N URL de cada tienda, para pruebas)
"""
import re
import sys
import time

from db import DB, PAUSED, connect
from scrapers.http import Blocked, get, log
from scrapers.jsonld import jsonld_gtin, jsonld_nodes

JUDGEME = ["sokobox.cl", "rakuencosmeticacoreana.cl", "arumi.cl", "moonbow.cl"]
DELAY = 5  # segundos entre fichas (1 request por producto, ~3.200 fichas: ~5 h). Propia, porque la de http.py (10 s) la llevaría a ~10 h
BADGE = re.compile(r"data-average-rating=['\"]([0-9.]+)['\"][^>]{0,80}data-number-of-reviews=['\"](\d+)")
# ponytail: Loox (Nooki, Bom Beauty) y Okendo (Coreana Chile) cargan la nota con JS; pendiente


def parse(html):
    """-> (nota, cantidad) o (None, None) si no hay reseñas."""
    m = BADGE.search(html)
    if not m or int(m.group(2)) == 0:
        return None, None
    return float(m.group(1)), int(m.group(2))


VARIANT = re.compile(r"[?&]variant=(\d+)")


def parse_gtins(html):
    """GTIN de los productos del JSON-LD de la página (nunca un regex sobre "barcode": la página trae también los de los recomendados)
    -> {id de variante: código}. La clave None es un código del producto sin variante identificable (la página no trae más de una).
    Formas reales: Sokobox, Product con gtin13 y `offers` en lista (el código es de la variante cuyo sku es el del Product);
    Rakuen y Arumi, Product con gtin y una oferta, o ProductGroup con un Product por variante en `hasVariant`; Moonbow no publica."""
    out = {}
    for node in jsonld_nodes(html, ("Product", "ProductGroup")):
        for u in node.get("hasVariant", []) if node["@type"] == "ProductGroup" else [node]:
            offs = u.get("offers")
            offs = [o for o in (offs if isinstance(offs, list) else [offs]) if isinstance(o, dict)]
            vid = lambda o: (m := VARIANT.search(str(o.get("url") or o.get("@id") or ""))) and m.group(1)
            for o in offs:  # código propio de cada oferta
                if (code := jsonld_gtin({}, o)) and vid(o):
                    out[vid(o)] = code
            mine = offs if len(offs) == 1 else [o for o in offs if u.get("sku") and o.get("sku") == u["sku"]]
            if (code := jsonld_gtin(u, {})) and (len(offs) <= 1 or len(mine) == 1):  # varias ofertas sin poder saber cuál: no se adivina
                out.setdefault(mine and vid(mine[0]) or None, code)
    return out


def gtins_for(listings, codes):
    """listings: [(id, ext_id)] de una misma URL; codes: parse_gtins() -> [(id, código)] solo de los que se pueden atar con certeza:
    por id de variante (ext_id en Shopify) o, si el código no tiene variante, solo cuando la URL tiene un único listing."""
    return [(i, c) for i, ext in listings if (c := codes.get(ext) or (codes.get(None) if len(listings) == 1 else None))]


def run(db, stores, limit=None):
    """Lee las tiendas en orden; un bloqueo corta solo la tienda actual."""
    log("ratings: inicio")
    for store in stores:
        urls = [r[0] for r in db.execute("SELECT DISTINCT url FROM listing WHERE store=?", (store,))][:limit]
        con = gtins = 0
        status = "listo"
        for i, url in enumerate(urls, 1):
            try:
                html = get(url, text=True, sign=True)  # fichas de tiendas Shopify (ADR-010)
                rating, reviews = parse(html)
            except Blocked as e:
                log(f"{url}: {e}")
                status = "detenido por bloqueo"
                break
            except Exception as e:
                log(f"{url}: {e}")
                time.sleep(DELAY)
                continue
            db.execute("UPDATE listing SET rating=?, reviews=? WHERE store=? AND url=?", (rating, reviews, store, url))
            found = gtins_for(db.execute("SELECT id, ext_id FROM listing WHERE store=? AND url=?", (store, url)).fetchall(), parse_gtins(html))
            for lid, code in found:  # solo si hay código: nunca se pisa uno existente con NULL
                db.execute("UPDATE listing SET gtin=? WHERE id=?", (code, lid))
            gtins += len(found)
            db.commit()  # una transacción corta por producto: así no bloquea a scrape.py ni al sitio mientras espera al siguiente request
            con += rating is not None
            if i % 50 == 0:
                log(f"{store}: {i}/{len(urls)}, {con} con reseñas, {gtins} con código de barras")
            time.sleep(DELAY)
        db.commit()
        log(f"{store}: {status}, {con} de {len(urls)} productos con reseñas, {gtins} listings con código de barras")
    log("ratings: fin")


if __name__ == "__main__":
    db = connect(DB)
    args = sys.argv[1:]
    limit = int(args.pop(args.index("--limit") + 1)) if "--limit" in args else None
    args = [a for a in args if a != "--limit"]
    run(db, args or [s for s in JUDGEME if s not in PAUSED], limit)
