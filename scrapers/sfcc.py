"""Farmacias Ahumada (Salesforce Commerce Cloud): parseo puro de los listados (sin red ni base de datos) y el adaptador `sfcc()`.

Solo se leen páginas de marca y de rutina con `?sz=N`, que entregan toda la lista en una solicitud. Su robots.txt veta `/*start`
(la paginación y el botón "Más resultados"), `/*pref`, `/*srule`, `/*pmin`, `/*pmax`, `*view=grid`, `*view=list` y `*/quickview`:
nada de eso se pide jamás. Si una página aún muestra el botón `show-more`, la lectura quedó incompleta y se avisa en el registro.

Trampa de precios: en un tile con `cmr-price-display` el precio grande (con el logo de CMR Falabella) es el de quien paga con esa tarjeta;
el precio para todos va en `.cmr-price-display .value[content]`. Ese precio es `price`; el de la tarjeta se guarda aparte en
`card_price`/`card_name` (dato actual, sin historial) y nunca cuenta como mejor precio. El precio por litro o kilo (`.preccio-fracionado`) se ignora.
Un tile no trae EAN: `gtin` queda en None.
"""
import re
import time
from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import urljoin

from scrapers.common import ScrapeCompletion, images_of
from scrapers.http import Blocked, get, log

BASE = "https://www.farmaciasahumada.cl"
DELAY = 10  # segundos entre páginas (cada una pesa ~0,7 a 2,4 MB)
CARD_NAME = "CMR Falabella"
PAGES = [  # lista explícita: nada de descubrir rutas
    *((f"/dermocosmetica/marcas/{m}?sz=300") for m in ("eucerin", "la-roche-posay", "vichy", "avene", "cetaphil", "isdin", "isdinceutics",
                                                      "uriage", "ducray", "otras-marcas")),
    "/rutina-k?sz=100",
]
CATEGORIES = {"dermocosmética", "belleza", "promociones", "campañas"}  # primer elemento de data-categories que se acepta. Las dos últimas son
# vitrinas de campaña donde Ahumada pone cosmética normal (Skin1004, Cetaphil, Eucerin...); lo no cosmético cae igual por nombre

# Marca como la escribe Ahumada (sin mayúsculas ni símbolos) -> como la escriben las demás tiendas
BRANDS = {"larocheposay": "La Roche-Posay", "cerave": "CeraVe", "isdin": "ISDIN", "isdinceutics": "ISDINCEUTICS", "eucerin": "Eucerin",
          "vichy": "Vichy", "avene": "Avène", "cetaphil": "Cetaphil", "uriage": "Uriage", "ducray": "Ducray", "skin1004": "SKIN1004",
          "beautyofjoseon": "Beauty of Joseon", "tocobo": "Tocobo", "elizavecca": "Elizavecca", "cosrx": "COSRX"}

# Medicamentos y suplementos que Ahumada mezcla en Dermocosmética. Se descartan por el nombre (regla -> patrón).
# "ampolla", "vitamina" y "colágeno" solos NO sirven: nombran sérums y tratamientos capilares de cosmética (medido en las muestras).
NOT_COSMETICS = {
    "medicamento/suplemento": re.compile(
        r"\b(?:caps|capsulas?|cápsulas?|capsules?|comprimidos?|tabletas?|grageas?|sobres|softgels?|gomitas|jarabe|supositorios?|inyectable|comp)\b|"
        r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|ug|ui)\b|"
        r"\bsoluci[oó]n\b.*\d\s*%|\d\s*%.*\bsoluci[oó]n\b|\bxerac\b", re.I),
    "pack 3x2": re.compile(r"\b3\s*x\s*2\b", re.I),
}
SHOW_MORE = re.compile(r'class="show-more\b')
VOID = {"img", "input", "br", "hr", "meta", "link", "source", "col", "area", "base", "wbr", "embed", "param", "track"}


def clp(s):
    """'$13.132\xa0' -> 13132"""
    m = re.search(r"\$\s*([\d.]+)", s or "")
    return int(m.group(1).replace(".", "")) if m else None


class Tiles(HTMLParser):
    """Junta los `div.product-tile` de una página. Cada tile queda como dict con los textos y atributos crudos."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tiles, self.tile, self.depth, self.stack = [], None, 0, []

    def ctx(self, name):
        return any(name in c for _, c in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if self.tile is None:
            if tag == "div" and "product-tile" in cls and a.get("data-pid"):
                self.tile = dict(pid=a["data-pid"], cats=a.get("data-categories", ""), sales="", brand="", title="", href=None, image=None,
                                 alt=None, cmr=None, strike=None, unavailable=False, card_badge=False)
                self.depth, self.stack = 1, []
            return
        t = self.tile
        if tag == "div":
            self.depth += 1
        if tag in VOID:
            pass
        else:
            self.stack.append((tag, cls))
        if tag == "img" and "tile-image" in cls:
            t["image"], t["alt"] = a.get("src"), a.get("alt")
        elif tag == "img" and "cmr_falabella" in (a.get("src") or ""):
            t["card_badge"] = True
        elif tag == "a" and self.ctx("pdp-link") and not t["href"]:
            t["href"] = a.get("href")
        elif tag == "span" and "value" in cls and a.get("content", "").isdigit():
            if self.ctx("cmr-price-display"):
                t["cmr"] = int(a["content"])
            elif self.ctx("strike-through"):
                t["strike"] = int(a["content"])
        elif tag == "button" and "product-tile-add-to-cart" in cls:
            t["unavailable"] = a.get("data-is-unavailable") == "true"

    def handle_endtag(self, tag):
        if self.tile is None:
            return
        for i in range(len(self.stack) - 1, -1, -1):  # cierra hasta la etiqueta que corresponde (hay `</span>` sueltos)
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.tiles.append(self.tile)
                self.tile = None

    def handle_data(self, data):
        t = self.tile
        if t is None:
            return
        if self.ctx("preccio-fracionado"):
            return
        if self.ctx("product-tile-brand"):
            t["brand"] += data
        elif self.ctx("pdp-link"):
            t["title"] += data
        elif self.ctx("sales"):
            t["sales"] += data


def norm_brand(name):
    name = " ".join((name or "").split())
    return BRANDS.get(re.sub(r"[^a-z0-9]", "", name.lower()), name or None)


def strip_brand(title, brand):
    """Ahumada pone la marca en medio o al final del título ("Serum Eucerin Hyaluron Filler 30 mL", "Mascarilla Centella Watergel
    Skin1004"), y el sitio la antepone al mostrar el nombre: quedaba "Eucerin Serum Eucerin...". Se quita de esas posiciones; al
    inicio la quita catalog.clean(). Se hace aquí y no en clean() porque en otras tiendas una marca en medio suele ser parte del
    nombre ("SPF Daily Duo: Tocobo Edition")."""
    words = re.findall(r"\w+", (brand or "").lower())  # \w incluye letras con tilde ("Avène")
    if not words:
        return title
    b = r"[\s.-]*".join(map(re.escape, words))
    t = re.sub(rf"(?<=\S)\s+{b}(?=\s+\S|\s*$)", "", title, flags=re.I)
    return " ".join(t.split()) or title


def parse_listing(page):
    """-> (ofertas, descartados, incompleta). Ofertas = dicts compatibles con db.save, precios en pesos.
    `descartados`: regla -> títulos que esa regla dejó fuera. `incompleta`: la página todavía ofrece "mostrar más"."""
    p = Tiles()
    p.feed(page)
    p.close()
    out, dropped = [], defaultdict(list)
    for t in p.tiles:
        title = " ".join(t["title"].split())
        cat = t["cats"].split(",")[0].strip().lower()
        sales = clp(t["sales"])
        price = t["cmr"] or sales  # CMR: el precio para todos es el de .cmr-price-display, el grande es con tarjeta
        if not title or not price or not t["href"]:
            dropped["sin precio o nombre"].append(title or t["pid"])
            continue
        if cat not in CATEGORIES:
            dropped["categoría " + (t["cats"].split(",")[0] or "vacía")].append(title)
            continue
        rule = next((r for r, rx in NOT_COSMETICS.items() if rx.search(title)), None)
        if rule:
            dropped[rule].append(title)
            continue
        card = t["cmr"] and sales and sales < price  # el precio con tarjeta solo vale si es menor que el de todos
        was = t["strike"]
        out.append(dict(
            ext_id=t["pid"], sku=t["pid"], title=strip_brand(title, t["brand"]), variant=None, vendor=norm_brand(t["brand"]),
            url=urljoin(BASE, t["href"]), image=t["image"], images=images_of([t["image"]]),
            price=price, compare_at=was if was and was > price else None,
            available=0 if t["unavailable"] else 1, currency="CLP", gtin=None,
            card_price=sales if card else None, card_name=CARD_NAME if card else None,
        ))
    return out, dict(dropped), bool(SHOW_MORE.search(page))


def sfcc(domain):
    """Dermocosmética de Ahumada desde sus páginas de marca (una solicitud por marca) y la de rutina coreana."""
    seen, dropped, incomplete = set(), defaultdict(list), []
    for n, path in enumerate(PAGES):
        if n:
            time.sleep(DELAY)
        try:
            items, drop, more = parse_listing(get(BASE + path, tries=1, text=True))
        except Blocked as e:  # nos pidieron parar: se corta y se guarda lo ya leído
            log(f"{domain}: {e}. Se detiene hasta la próxima corrida ({len(seen)} productos leídos)")
            incomplete.append(path)
            break
        except Exception as e:  # una página que falla no debe perder las demás
            log(f"{domain} {path}: ERROR {e}")
            incomplete.append(path)
            continue
        if more:
            incomplete.append(path)
            log(f"{domain} {path}: todavía ofrece 'show-more', lista incompleta (no se pagina: su robots.txt veta start)")
        for rule, titles in drop.items():
            dropped[rule] += titles
        new = [i for i in items if i["ext_id"] not in seen]  # una marca aparece en su página y en otras-marcas o en rutina-k
        seen.update(i["ext_id"] for i in new)
        log(f"{domain} {path.split('?')[0]}: {len(items)} productos ({len(new)} nuevos)")
        yield from new
    for rule, titles in dropped.items():
        log(f"{domain}: descartados por '{rule}': {len(titles)} (por ejemplo: {'; '.join(titles[:3])})")
    if incomplete:
        log(f"{domain}: {len(incomplete)} páginas sin leer completas: {', '.join(incomplete)}")
    return ScrapeCompletion(bool(incomplete))
