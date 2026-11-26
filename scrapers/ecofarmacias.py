"""EcoFarmacias (WooCommerce): dermocosmética y protectores solares de una farmacia con 7.194 productos (3.744 medicamentos).

Se lee la Store API (`/wp-json/wc/store/v1/products`, permitida por su robots.txt) solo de dos categorías: Dermocosmética y Protectores Solares
(~350 productos distintos, 4 solicitudes). Reutiliza `woocommerce()` con el filtro `category` y le agrega lo que esta tienda no entrega:
- **Marca:** la API no la trae (`brands` viene vacío): se busca en el título con una lista (`BRANDS`); lo que no calza queda sin marca.
- **EAN:** viene en el SKU ("3337875597272"); un sufijo ",1" marca los duplicados de remate.
- **Remates:** unidades próximas a vencer se publican como un segundo producto ("... DESCUENTO Venc" o SKU con ",1"): otro
  producto para el comprador, no el precio habitual, así que no se leen.
- **No cosmético:** la categoría mezcla medicamentos y verrugas (adapaleno, Lunar Off): se descartan por nombre, con las reglas de Ahumada
  más las propias.
Casi el 80% del catálogo de esas categorías está sin stock (se guarda igual, como "sin stock").
"""
import re
import time
from collections import defaultdict

from scrapers.common import ScrapeCompletion, gtin
from scrapers.http import Blocked, log
from scrapers.sfcc import NOT_COSMETICS, strip_brand
from scrapers.woocommerce import woocommerce

DELAY = 10  # segundos entre páginas (cada una pesa ~0,5 MB)
CATEGORIES = (1450, 112)  # Dermocosmética, Protectores Solares (ids de /products/categories; `belleza` y `cuidado-personal` mezclan perfumería y Nivea)

# Marca -> patrón que la reconoce en el título (la primera que calza gana; orden = más específica primero)
BRANDS = {
    "La Roche-Posay": r"(?:la[\s-]*)?roche[\s-]*posay", "Eucerin": "eucerin", "ISDIN": r"isdin|fotoultra|ureadin", "Avène": r"av[eèé]ne", "Vichy": "vichy",
    "CeraVe": "cerave", "Cetaphil": "cetaphil", "Uriage": "uriage", "Ducray": "ducray", "Bioderma": "bioderma", "Apivita": "apivita",
    "Heliocare": "heliocare", "Nuxe": "nuxe", "SVR": r"svr", "Sesderma": "sesderma", "Filorga": "filorga", "A-Derma": r"a[\s-]*derma",
    "Mustela": "mustela", "Leti": r"leti\b", "Nivea": "nivea", "Dove": "dove", "Simonds": r"simond", "Leblon": "leblon", "Rayfilter": "rayfilter",
    "Raytan": "raytan", "Rayito de Sol": r"rayito de sol", "Teatrical": "teatrical", "Cicatricure": "cicatricure", "Bio-Oil": r"bio[\s-]*oil",
    "L'Oréal": r"l['’]?or[eé]al|revitalift", "Stratamark": "stratamark", "Pielarmina": "pielarmina",
}
BRAND_RX = [(b, re.compile(rf"\b(?:{p})", re.I)) for b, p in BRANDS.items()]

# Remates de unidades por vencer y medicamentos que la categoría Dermocosmética mezcla (regla -> patrón sobre el nombre)
NOT_HERE = {**NOT_COSMETICS,
            "remate": re.compile(r"\bDESCUENTO\b|\bvenc\b", re.I),
            "medicamento": re.compile(r"\badapaleno\b|\bverrugas?\b|\bpapilomas?\b|\bxerolan\b|\bsprainer\b|\bheridas?\b", re.I)}


def brand_of(title):
    return next((b for b, rx in BRAND_RX if rx.search(title)), None)


def clean(items):
    """Ofertas de `woocommerce()` -> (ofertas listas para db.save, descartados por regla)."""
    out, dropped, seen = [], defaultdict(list), set()
    for i in items:
        sku = i["sku"] or ""
        rule = next((r for r, rx in NOT_HERE.items() if rx.search(i["title"])), None) or ("remate" if "," in sku else None)
        if rule:
            dropped[rule].append(i["title"])
        elif i["ext_id"] not in seen:  # un producto puede estar en las dos categorías
            seen.add(i["ext_id"])
            brand = brand_of(i["title"])
            ean = gtin(sku) if len(sku) >= 12 else None
            out.append({**i, "title": strip_brand(i["title"], brand), "vendor": brand, "sku": sku or None, "gtin": ean, "currency": "CLP"})
    return out, dict(dropped)


def ecofarmacias(domain):
    items = []
    partial = False
    for n, cat in enumerate(CATEGORIES):
        if n:
            time.sleep(DELAY)
        try:
            items += list(woocommerce(domain, f"&category={cat}", DELAY))
        except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
            log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(items)} productos leídos)")
            partial = True
            break
    out, dropped = clean(items)
    for rule, titles in dropped.items():
        log(f"{domain}: descartados por '{rule}': {len(titles)} (por ejemplo: {'; '.join(titles[:3])})")
    log(f"{domain}: {len(out)} productos, {sum(1 for i in out if not i['vendor'])} sin marca reconocida")
    yield from out
    return ScrapeCompletion(partial)
