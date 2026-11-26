"""Farmacias Novasalud (Magento, de Abbott): dermocosmética desde la categoría `/dispositivos-medicos` (así llaman a su cosmética), sin red ni
base de datos en el parseo (`parse_listing`).

Su robots.txt permite `?p=N` (la paginación) y veta casi todo el resto de los parámetros, así que se pide solo `/dispositivos-medicos` y
`/dispositivos-medicos?p=2`... (36 por página, ~9 páginas). Crawl-delay: 20 s solo figura para YandexBot, pero se respeta igual (`DELAY`).

Cada tarjeta trae `data-product-id`, nombre, URL, imagen, el precio en
`data-price-type="finalPrice"` (el que se paga: "Precio especial" si hay oferta) y, si hay oferta, `oldPrice` ("Precio normal"). El agotado
se marca con `div.stock.unavailable`. **No trae marca**: se saca del título o del slug de la URL con `scrapers.dermo`, y solo se guardan las
marcas de dermocosmética (la categoría mezcla perfumes, colonias, cremas de manos y otros genéricos de farmacia). El SKU de la tarjeta (7 dígitos, interno, solo está en las que se pueden comprar) no se usa: `sku` = `data-product-id` y `gtin` None. Los productos de esas marcas
sin la marca en el título ni en la URL (Cicaplast Gel B5) se pierden.
"""
import math
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin

from scrapers.common import ScrapeCompletion, images_of
from scrapers.dermo import brand_in
from scrapers.http import Blocked, get, log
from scrapers.sfcc import strip_brand

BASE = "https://www.novasalud.cl"
CATEGORY = "/dispositivos-medicos"
DELAY = 20  # segundos entre páginas (Crawl-delay de su robots.txt)
MAX_PAGES = 15  # tope por si el contador de la página cambia: hoy son 9
SIZE = re.compile(r"\d\s*(?:ml|g|gr|grs|l|kg)\b", re.I)
TOTAL = re.compile(r'class="toolbar-number">(\d+)</span>-<span class="toolbar-number">(\d+)</span> de <span class="toolbar-number">(\d+)<')


class Cards(HTMLParser):
    """Junta los `li.product-item` de una página. Cada tarjeta queda como dict con los textos y atributos crudos."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards, self.card, self.depth, self.link = [], None, 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if self.card is None:
            if tag == "li" and "product-item" in cls:
                self.card = dict(pid=None, title="", href=None, image=None, price=None, old=None, unavailable=False)
                self.depth = 1
            return
        t = self.card
        if tag == "li":
            self.depth += 1
        if a.get("data-product-id") and not t["pid"]:
            t["pid"] = a["data-product-id"]
        if tag == "a" and "product-item-link" in cls:
            t["href"], self.link = a.get("href"), True
        elif tag == "img" and "product-image-photo" in cls and not t["image"]:
            t["image"] = a.get("src")
        elif tag == "span" and (a.get("data-price-amount") or "").isdigit():
            kind = a.get("data-price-type")
            if kind == "finalPrice":
                t["price"] = int(a["data-price-amount"])
            elif kind == "oldPrice":
                t["old"] = int(a["data-price-amount"])
        elif tag == "div" and "stock" in cls and "unavailable" in cls:
            t["unavailable"] = True

    def handle_endtag(self, tag):
        if self.card is None:
            return
        if tag == "a":
            self.link = False
        elif tag == "li":
            self.depth -= 1
            if self.depth == 0:
                self.cards.append(self.card)
                self.card = None

    def handle_data(self, data):
        if self.card is not None and self.link:
            self.card["title"] += data


def clean_title(title):
    """Quita el relleno de SEO de Novasalud: "Cerave Foaming Cleanser 236ml - Gel Limpiador Espumoso" -> "Cerave Foaming Cleanser 236ml".
    Solo se corta tras un tamaño y si lo que sigue no trae cifras ("Eucerin Kids Protector Solar FPS50+ - 400ml" conserva el tamaño)."""
    t = " ".join(title.split())
    m = re.search(r"\s(?:-|–)\s|:\s", t)
    if m and SIZE.search(t[:m.start()]) and not re.search(r"\d", t[m.end():]):
        t = t[:m.start()]
    return re.sub(r"\s*-?\s*Nova\s?Salud$", "", t, flags=re.I).strip()


def parse_listing(page):
    """-> (ofertas, descartados, (primero, último, total) del contador de la página o None). Ofertas = dicts compatibles con db.save, precios en pesos.
    `descartados`: cuántos no eran de las marcas de dermocosmética o no traían precio."""
    p = Cards()
    p.feed(page)
    p.close()
    out, dropped = [], 0
    for t in p.cards:
        title = clean_title(t["title"])
        slug = (t["href"] or "").rstrip("/").rsplit("/", 1)[-1]
        brand = brand_in(title) or brand_in(slug)
        if not (t["pid"] and title and t["price"] and t["href"] and brand):
            dropped += 1
            continue
        out.append(dict(
            ext_id=t["pid"], sku=t["pid"], title=strip_brand(title, brand), variant=None, vendor=brand, url=urljoin(BASE, t["href"]),
            image=t["image"], images=images_of([t["image"]]), price=t["price"], compare_at=t["old"] if t["old"] and t["old"] > t["price"] else None,
            available=0 if t["unavailable"] else 1, currency="CLP", gtin=None, card_price=None, card_name=None,
        ))
    m = TOTAL.search(page)
    return out, dropped, tuple(map(int, m.groups())) if m else None


def novasalud(domain):
    """Dermocosmética de Novasalud: la categoría `/dispositivos-medicos` página por página (`?p=N`)."""
    seen, pages, n = set(), 1, 1
    partial = False
    while n <= min(pages, MAX_PAGES):
        if n > 1:
            time.sleep(DELAY)
        path = CATEGORY if n == 1 else f"{CATEGORY}?p={n}"
        try:
            items, dropped, counter = parse_listing(get(BASE + path, tries=1, text=True))
        except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
            log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(seen)} productos leídos)")
            return ScrapeCompletion(True)
        except Exception as e:  # una página que falla no debe perder las demás (el contador solo se conoce si la primera se leyó)
            log(f"{domain} {path}: ERROR {e}")
            partial = True
            n += 1
            continue
        if counter and n == 1:
            pages = math.ceil(counter[2] / counter[1])  # "Artículos 1-36 de 292"
        elif not counter and n == 1:
            log(f"{domain}: la página no trae el contador de artículos, solo se lee la primera")
            partial = True
        new = [i for i in items if i["ext_id"] not in seen]
        seen.update(i["ext_id"] for i in new)
        log(f"{domain} {path}: {len(items)} productos de marcas dermo ({len(new)} nuevos), {dropped} de otras marcas descartados")
        yield from new
        n += 1
    partial = partial or pages > MAX_PAGES
    return ScrapeCompletion(partial, complete=not partial)  # todas las páginas del contador, sin errores
