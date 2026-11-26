"""Adaptador VTEX genérico (catálogo público `/api/catalog_system/pub/products/search`): parseo puro y el generador `vtex()`.

Sirve para cualquier tienda VTEX (Farmacias del Dr. Simi, y las que vengan). La tienda se limita por categorías (`fq=C:/<id>/`) o por marcas
(`fq=B:<id>`) de cosmética y dermocosmética; nunca se lee el catálogo entero de una farmacia.

Reglas de VTEX que se respetan:
- el rango `_from`/`_to` es de a 50 como máximo y VTEX no entrega más allá de la posición 2.500 (responde 400): `STEP` y `MAX_ITEMS`. Un filtro
  que llega al tope se avisa como lista incompleta (hay que partirlo en subcategorías o marcas);
- el filtro del servidor solo acota: cada producto se revisa contra `categoriesIds` o `brandId` pedidos, para que un `fq` mal escrito (o ignorado)
  no cuele productos de otras categorías;
- pausa de `DELAY` segundos entre páginas. Su API pública limita por ritmo: la sonda de Farmacias del Dr. Simi dio 429 a la tercera solicitud
  con 6 s de pausa. Ante 403 o 429 se corta y se guarda lo leído, sin reintentar.

Cada producto trae uno o más `items` (SKU). Se guarda un listing por SKU, con el vendedor por defecto (`sellerDefault`): `Price` es el precio
para todos (`price`) y `ListPrice` el "antes" (solo si es mayor). Un SKU sin precio (`Price` 0, VTEX lo entrega así cuando se agotó) se descarta:
no hay precio que confirmar. El EAN viene en el item (`ean`) o, si el producto tiene un solo SKU, en la especificación `EANCode`.
"""
import time
from collections import defaultdict
from urllib.parse import quote

from scrapers.common import ScrapeCompletion, gtin, images_of, text_of
from scrapers.http import Blocked, get, log
from scrapers.sfcc import NOT_COSMETICS

STEP = 50  # máximo de VTEX por solicitud (_to - _from + 1)
MAX_ITEMS = 2500  # VTEX no entrega posiciones mayores
DELAY = 20  # segundos entre páginas


def parse_product(p, wanted=None):
    """Un producto de la API -> lista de ofertas (una por SKU con precio), compatibles con db.save. `wanted`: función que dice si el producto
    entra (por categoría o marca); si no entra, lista vacía."""
    if wanted and not wanted(p):
        return []
    items = p.get("items") or []
    spec_ean = (p.get("EANCode") or [None])[0] if len(items) == 1 else None  # con varios SKU no se sabe de cuál es
    out = []
    for it in items:
        sellers = it.get("sellers") or []
        seller = next((s for s in sellers if s.get("sellerDefault")), sellers[0] if sellers else None)
        offer = (seller or {}).get("commertialOffer") or {}
        price = round(offer.get("Price") or 0)
        if price <= 0:
            continue
        was = round(offer.get("ListPrice") or 0)
        images = [i["imageUrl"] for i in it.get("images") or [] if i.get("imageUrl")]
        name = p["productName"]
        out.append(dict(
            ext_id=str(it["itemId"]), sku=p.get("productReference") or None, gtin=gtin(it.get("ean") or spec_ean), title=name,
            variant=it["name"] if len(items) > 1 and it.get("name") and it["name"] != name else None,
            vendor=p.get("brand") or None, url=p["link"], image=images[0] if images else None, images=images_of(images),
            price=price, compare_at=was if was > price else None, currency="CLP",
            available=int(bool(offer.get("IsAvailable")) and (offer.get("AvailableQuantity") or 0) > 0),
            description=text_of(p.get("description") or p.get("metaTagDescription")),
        ))
    return out


def vtex(domain, categories=(), brands=(), delay=DELAY):
    """Lee las categorías (ids, p. ej. "279") y marcas (ids) pedidas, de a `STEP`, con pausa de `delay`. Un listing por SKU."""
    cats = [f"/{c.strip('/')}/" for c in categories]
    filters = [(f"C:{c}", lambda p, c=c: any(i.startswith(c) for i in p.get("categoriesIds") or [])) for c in cats]
    filters += [(f"B:{b}", lambda p, b=b: str(p.get("brandId")) == str(b)) for b in brands]
    seen, dropped, short, n = set(), defaultdict(list), [], 0
    for fq, wanted in filters:
        start = 0
        while start < MAX_ITEMS:
            if n:
                time.sleep(delay)
            n += 1
            url = f"https://{domain}/api/catalog_system/pub/products/search?fq={quote(fq, safe=':/')}&_from={start}&_to={start + STEP - 1}"
            try:
                page = get(url, tries=1)
            except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
                log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(seen)} productos leídos)")
                return _report(domain, dropped, short + [f"{fq} (cortada por bloqueo)"])
            except Exception as e:  # un filtro que falla no debe perder los demás
                log(f"{domain} {fq}: ERROR {e}")
                short.append(f"{fq} (error)")
                break
            for p in page:
                offers = parse_product(p, wanted)
                if not offers:
                    dropped["fuera del filtro o sin precio"].append(p.get("productName", "?"))
                    continue
                rule = next((r for r, rx in NOT_COSMETICS.items() if rx.search(p["productName"])), None)
                if rule:
                    dropped[rule].append(p["productName"])
                    continue
                for o in offers:
                    if o["ext_id"] not in seen:
                        seen.add(o["ext_id"])
                        yield o
            if len(page) < STEP:
                break
            start += STEP
        else:
            short.append(f"{fq} (llegó al tope de {MAX_ITEMS}: partir el filtro)")
    return _report(domain, dropped, short)


def _report(domain, dropped, short):
    for rule, titles in dropped.items():
        log(f"{domain}: descartados por '{rule}': {len(titles)} (por ejemplo: {'; '.join(titles[:3])})")
    if short:
        log(f"{domain}: filtros con la lista incompleta: {', '.join(short)}")
    return ScrapeCompletion(bool(short))
