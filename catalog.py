"""Arma el catálogo (productos agrupados por match.py) y responde las consultas de la web."""
import hashlib
import random
import json
import re
import sqlite3
import statistics
import time
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from describe import GROUPS, attributes, contents, norm
from match import MINI, is_pack, key_of, load_ex, words
from db import RETIRED, BY_BRAND, DB, PRICE_RANGE, anomaly, connect, sync_aliases
from scrapers.dermo import BRANDS as DERMO_NAMES

PAGE_SIZE = 24
GALLERY = 4  # imágenes por producto: la principal + hasta 3 más
IVA = 0.19  # IVA a las compras del extranjero (Ley 21.713, desde 25-oct-2025)
MIN_REVIEWS = 5  # reseñas mínimas para mostrar la nota en la card (una nota con 1-2 reseñas engaña)
DEAL_DAYS = 14  # ventana del precio de referencia: el más alto que vimos en estos días
DEAL_PCT = 10  # baja mínima (%) para contar como oferta en el filtro y en Catalog.deals
DEAL_MIN = 20  # productos en oferta que debe tener una tienda para aparecer en Catalog.deals
DEAL_SHOW = 20  # baja mínima (%) para la franja de ofertas del inicio (Catalog.deal_picks): solo las que valen la pena
# Eventos de ofertas (hora de Chile, ambos días incluidos). Solo cuentan las bajas que EMPEZARON dentro de sus fechas: una rebaja que ya
# venía de antes no es del evento. Las tiendas no marcan sus productos como "Cyber" en lo que leemos, así que no hay otra forma honesta de
# saberlo. Black Friday se calcula solo cada año (black_friday); CyberDay (junio) y el Cyber de octubre los fija cada año la Cámara de
# Comercio de Santiago: anotarlos aquí cuando se anuncien. `theme` elige el logo propio del evento (server.EVENT_ICONS y style.css).
# `early` (opcional): la previa. Muchas tiendas adelantan sus rebajas: desde ese día se activa la sección y se cuentan las bajas, pero las
# fechas del evento que se muestran siguen siendo start-end (el sitio aclara desde cuándo contamos).
EVENTS = [
    # previa desde el 1-oct: Arumi (58 bajas el 1-oct) y Sokobox (835, el 2-oct) adelantaron sus rebajas
    {"slug": "cyber", "name": "Cyber", "start": "2026-10-05", "end": "2026-10-07", "early": "2026-10-01", "theme": "cyber"},
]


def black_friday(year):
    """Black Friday: el viernes siguiente al cuarto jueves de noviembre (Acción de Gracias en EE.UU.), hasta el lunes (Cyber Monday)."""
    nov1 = date(year, 11, 1)
    thursday = nov1 + timedelta(days=(3 - nov1.weekday()) % 7 + 21)
    return {"slug": "black-friday", "name": "Black Friday", "start": (thursday + timedelta(days=1)).isoformat(),
            "end": (thursday + timedelta(days=4)).isoformat(), "theme": "black-friday"}


def all_events(today=None):
    """Los eventos anotados más Black Friday del año pasado y de este, por fecha de inicio."""
    y = (today or date.today()).year
    return sorted(EVENTS + [black_friday(y - 1), black_friday(y)], key=lambda ev: ev["start"])


def opens(ev):
    """Desde qué día cuenta el evento: su previa si tiene, si no su inicio."""
    return ev.get("early") or ev["start"]


def live_event(today=None):
    """El evento que está en curso hoy (hora local, contando su previa), o None."""
    d = (today or date.today()).isoformat()
    return next((ev for ev in all_events(today) if opens(ev) <= d <= ev["end"]), None)


def event_for(slug, today=None):
    """El evento de esa dirección: el que está en curso; si no, el que terminó hace menos de DEAL_DAYS (sus rebajas pueden seguir); si no,
    el próximo; si no, el último. None si no existe."""
    t = today or date.today()
    d, recent = t.isoformat(), (t - timedelta(days=DEAL_DAYS)).isoformat()
    evs = [ev for ev in all_events(today) if ev["slug"] == slug]
    return (next((ev for ev in evs if opens(ev) <= d <= ev["end"]), None) or next((ev for ev in reversed(evs) if recent <= ev["end"] < d), None)
            or next((ev for ev in evs if opens(ev) > d), None) or (evs[-1] if evs else None))


def in_event(o, ev):
    """¿La baja de esta oferta es del evento? Al menos DEAL_PCT, con stock y con su precio actual vigente desde dentro de sus fechas."""
    return o.available and o.drop >= DEAL_PCT and bool(o.since) and opens(ev) <= o.since <= ev["end"]
INTL_STORES = {"www.yesstyle.com", "www.stylevana.com", "www.wishtrend.com", "cosrx.com", "beautyofjoseon.com"}
STORE_NAMES = {
    "www.yesstyle.com": "YesStyle", "www.stylevana.com": "Stylevana", "www.wishtrend.com": "Wishtrend", "cosrx.com": "COSRX oficial",
    "beautyofjoseon.com": "Beauty of Joseon oficial", "www.farmaciasahumada.cl": "Farmacias Ahumada",
    "dermotienda.cl": "Dermotienda", "www.ecofarmacias.cl": "EcoFarmacias", "www.novasalud.cl": "Novasalud", "www.farmaloop.cl": "Farmaloop",
    "www.paris.cl": "Paris", "dbs.cl": "DBS Beauty Store",
    "sokobox.cl": "Sokobox", "rakuencosmeticacoreana.cl": "Rakuen", "vierosecosmetics.cl": "Vierose",
    "moonbow.cl": "Moonbow", "kosmeticos.cl": "Kosmeticos", "quecoreana.cl": "¡Qué Coreana!",
    "arumi.cl": "Arumi", "www.koryobeauty.cl": "KoryoBeauty", "unniebeauty.cl": "Unnie Beauty", "nooki.cl": "Nooki", "coreanachile.cl": "Coreana Chile",
    "www.bombeauty.cl": "Bom Beauty", "kbelleza.cl": "K Belleza", "bellezacoreana.cl": "Belleza Coreana",
}
# Farmacias y tiendas de dermocosmética: que vendan una marca no la vuelve asiática (ver section_of). Paris y DBS no están: son tiendas
# generales y sus adaptadores solo leen marcas de DERMO_BRANDS (y asiáticas, DBS), justamente para no empujar marcas a la sección asiática.
PHARMACY_STORES = {"www.farmaciasahumada.cl", "dermotienda.cl", "www.ecofarmacias.cl", "www.novasalud.cl", "www.farmaloop.cl"}


def brand_slug_of(name):
    """El slug de marca de `Product.brand_slug` ("La Roche-Posay" -> "la-roche-posay"), para escribir DERMO_BRANDS legible."""
    return "-".join(re.findall(r"[a-z0-9]+", words(name).replace("&", " ")))


# Sección "dermocosmética": marcas no asiáticas que se venden mucho en farmacias chilenas. Esta lista manda: una marca de aquí es siempre
# dermocosmética, aunque alguna tienda asiática también la venda (YesStyle con CeraVe). Las marcas que NO están aquí se deciden por quién las
# vende (ver section_of). Para sumar una marca basta agregar su nombre en scrapers/dermo.py; no cambia ningún id de producto.
DERMO_BRANDS = {brand_slug_of(n) for n in DERMO_NAMES}  # la lista vive en scrapers/dermo.py: los adaptadores de Paris y Novasalud la usan


def section_of(brand, sold_outside_pharmacy):
    """"asiatica" o "dermocosmetica", decidida por MARCA y no por tienda (así un mismo producto no cambia de sección según dónde se compre):
    1. una marca de DERMO_BRANDS es dermocosmética siempre;
    2. si no, y alguna tienda que NO es farmacia (chilena o del extranjero) vende la marca, es asiática: SKIN1004 en Ahumada entra a la
       comparación asiática de siempre y suma un precio chileno;
    3. si no (solo la venden farmacias y no está en la lista: Isispharma), es dermocosmética: las tiendas asiáticas no la conocen.
    `brand`: la tupla de la clave de match.py. `sold_outside_pharmacy`: para una marca conocida, si alguna tienda no farmacia la vende;
    sin marca se decide por el propio producto."""
    if brand_slug_of(" ".join(brand)) in DERMO_BRANDS:
        return "dermocosmetica"
    return "asiatica" if sold_outside_pharmacy else "dermocosmetica"


def store_name(domain):
    return STORE_NAMES.get(domain, domain.removeprefix("www."))


@dataclass
class Offer:
    listing_id: int
    store: str
    price: int
    compare_at: int | None
    available: bool
    url: str
    rating: float | None
    reviews: int | None
    drop: int = 0  # % que bajó frente al precio más alto de los últimos DEAL_DAYS en nuestro historial (0 si no bajó o no es confiable). Ver price_drops()
    stale: str | None = None  # tienda sin conexión: fecha de la última lectura confirmada (y available=False)
    gone: str | None = None  # la tienda respondió pero ya no lo lista: cuándo se vio por última vez (y available=False). Ver missing()
    suspect: str | None = None  # precio que parece un error de carga (db.anomaly): por qué (y available=False)
    card_price: int | None = None  # precio solo con la tarjeta de la tienda (listing.card_price), dato actual. NUNCA cuenta como precio: ver Product.card_offers
    card_name: str | None = None  # la tarjeta ("CMR Falabella")
    ref: int | None = None  # el precio "antes" que respalda drop: el más alto de los últimos DEAL_DAYS en nuestro historial (None si no bajó)
    since: str | None = None  # día (hora local, "2026-10-05") desde el que rige su precio actual (ver price_since): decide si una baja es de un evento


@dataclass
class IntlOffer:
    """Oferta de una tienda del extranjero. Precio en centavos de USD; el CLP con IVA es solo una estimación (sin envío)."""
    listing_id: int
    store: str
    cents: int
    compare_cents: int | None
    url: str
    available: bool = True
    stale: str | None = None
    gone: str | None = None
    suspect: str | None = None


def clp_estimate(cents, usd_clp):
    return round(cents / 100 * usd_clp * (1 + IVA))


def pid_of(brand, toks, sizes, mini):
    """Id estable del producto: hash de su clave de match.py (si cambian las reglas de matching, cambian los ids)."""
    return hashlib.sha1(repr((brand, sorted(toks), sizes, mini)).encode()).hexdigest()[:10]


@dataclass
class Product:
    id: str
    name: str
    brand: str
    brand_slug: str
    size: str
    mini: bool
    image: str | None
    images: list = field(default_factory=list)  # hasta GALLERY urls distintas; la primera es la principal
    alts: list = field(default_factory=list)  # la primera imagen de cada OTRA tienda: respaldo si la principal no carga (tienda caída)
    offers: list = field(default_factory=list)  # con stock primero, cada grupo de menor a mayor precio
    intl: list = field(default_factory=list)  # IntlOffer, de menor a mayor precio; no cuenta para el mejor precio
    search: str = ""
    key: tuple = ()  # clave de match.py (marca, palabras, tamaños, miniatura)
    matched_by: str = "texto"  # cómo se agrupó: "texto" (la clave), "gtin" (además se unieron grupos que comparten código de barras) o "nombre"
    # (se unió un nombre más corto de la misma marca y tamaño: match.merge_similar)
    is_pack: bool = False  # set / kit / duo / rutina / N-pack: no entra en la comparación de un producto individual
    aliases: frozenset = frozenset()  # solo individuales: sus nombres normalizados, para reconocerlos dentro de la descripción de un pack
    pack_text: str = ""  # solo packs: títulos y descripciones normalizados
    text: str = ""  # títulos y descripciones de todas las tiendas, normalizados (para describe.py)
    kind: str = ""  # tipo de producto (sérum, protector solar...), deducido del nombre
    group: str = ""  # categoría: facial, maquillaje, cabello, cuerpo, accesorios (vacío si no se reconoce)
    skin: list = field(default_factory=list)  # tipos de piel que mencionan las tiendas
    actives: list = field(default_factory=list)  # compuestos destacados que mencionan las tiendas
    includes: list = field(default_factory=list)  # solo packs: [(id del producto, cantidad)]
    included_in: list = field(default_factory=list)  # solo individuales: [(id del pack, cantidad)]
    contents: list = field(default_factory=list)  # solo packs: [(nombre, tamaño)] que la descripción enumera tras "incluye:"
    content_rows: list = field(default_factory=list)  # solo packs: [(nombre, tamaño, id del producto suelto o None)]
    pack_sizes: dict = field(default_factory=dict)  # solo packs: id del producto -> tamaño que trae EL PACK ("20 ml"), si la descripción lo dice
    small_format: bool = False  # solo packs: viene en formato mini / de prueba (no en el tamaño normal de los productos sueltos)
    display_price: int | None = None  # precio a mostrar en CLP: el chileno si hay, si no un estimado desde la oferta internacional más barata
    display_is_estimate: bool = False  # True cuando display_price viene de convertir dólares (no hay ninguna tienda chilena)
    variant: str = ""  # solo si otro producto se llama igual (tonos de maquillaje): la variante de la tienda, para distinguirlos
    brand_site: str = ""  # dominio del sitio oficial de la marca cuyo texto se sumó a `text` (ver official_text); "" si ninguno
    section: str = "asiatica"  # "asiatica" o "dermocosmetica", por marca (ver section_of)

    @property
    def domestic(self):
        """¿Alguna tienda chilena lo vende? Si no, solo existe la oferta internacional (display_is_estimate)."""
        return bool(self.offers)

    @property
    def listed_in_chile(self):
        """¿Alguna tienda chilena aún lo lista, con o sin stock y aunque esté sin conexión? Criterio del sitemap: no cambia con un
        bloqueo pasajero (una tienda sin conexión marca todo sin stock) ni con cada quiebre de stock."""
        return any(not o.gone for o in self.offers)

    @property
    def in_stock(self):
        return [o for o in self.offers if o.available]

    @property
    def intl_in_stock(self):
        return [o for o in self.intl if o.available]

    @property
    def best_intl(self):
        """La oferta internacional a mostrar: la más barata con stock, o la más barata si ninguna tiene."""
        return (self.intl_in_stock or self.intl)[0] if self.intl else None

    @property
    def min_price(self):
        """Precio chileno más bajo, o None si el producto solo se vende en el extranjero (ver display_price)."""
        return (self.in_stock or self.offers)[0].price if self.offers else None

    @property
    def spread(self):
        s = self.in_stock
        return (s[-1].price - s[0].price) / s[-1].price if len(s) > 1 else 0.0

    @property
    def rating(self):
        """Oferta con la nota que muestra la card: la de la tienda con más reseñas (la más fiable), si llega a MIN_REVIEWS. None si ninguna."""
        rated = [o for o in self.offers if o.rating and o.reviews and o.reviews >= MIN_REVIEWS]
        return max(rated, key=lambda o: o.reviews) if rated else None

    @property
    def card_offers(self):
        """Ofertas con stock que tienen precio con tarjeta menor que su precio normal, de menor a mayor precio con tarjeta (a igualdad, tienda
        en orden alfabético). Aparte de offers a propósito: el precio con tarjeta exige una tarjeta de la tienda, así que no es el mejor precio,
        ni empata, ni es display_price, ni cuenta para drop, ofertas o filtros de precio."""
        return sorted((o for o in self.in_stock if o.card_price and o.card_price < o.price), key=lambda o: (o.card_price, words(store_name(o.store))))

    @property
    def drop(self):
        """% de baja más grande entre las ofertas que hoy tienen el mejor precio (el producto se puede comprar más barato que antes)."""
        s = self.in_stock  # ya viene de menor a mayor precio
        return max((o.drop for o in s if o.price == s[0].price), default=0)

    @property
    def drop_ref(self):
        """El precio "antes" que respalda drop (para tacharlo al lado del precio): la referencia de la oferta con el mejor precio que más bajó."""
        s = self.in_stock
        best = [o for o in s if o.price == s[0].price and o.drop]
        return max(best, key=lambda o: o.drop).ref if best else None

    def event_drop(self, ev):
        """Como drop, pero solo si esa baja empezó durante el evento `ev`: el mejor precio de hoy es una rebaja del evento (0 si no)."""
        s = self.in_stock
        return max((o.drop for o in s if o.price == s[0].price and in_event(o, ev)), default=0)


def clean(title, brand, size):
    t = re.sub(r"[«»“”\"]", "", title)
    t = re.sub(r"\s+", " ", t).strip()
    if brand:
        b = re.escape(brand)
        t = re.sub(rf"^\W*{b}\b\W*", "", t, flags=re.I)  # "Marca Nombre" -> "Nombre"
        t = re.sub(rf"\s*[–—-]\s*{b}\s*$", "", t, flags=re.I)  # "Nombre – Marca" -> "Nombre"
    if size:
        t = re.sub(r"\s*\b\d+(?:[.,]\d+)?\s*(?:ml|gr|g|oz|kg)\b", "", t, flags=re.I)
    t = t.strip(" -–—:")
    return (t.title() if t.isupper() else t) or title


SMALL_WORDS = {"mini", "minis", "miniatura", "miniaturas", "trial"}  # en el título o la descripción del pack: formato pequeño


def size_after(text, alias):
    """Tamaño que la descripción del pack menciona justo después del nombre del producto ("... Toner 20ml"), o ""."""
    i = text.find(f" {alias} ")
    while i >= 0:
        m = re.fullmatch(r"([0-9]+)(ml|gr|g)", text[i + len(alias) + 2:].split(" ", 1)[0])
        if m:
            return f"{m.group(1)} {'ml' if m.group(2) == 'ml' else 'g'}"
        i = text.find(f" {alias} ", i + 1)
    return ""


def multipack_base(key):
    """Si el pack es el mismo producto x N ("2-Pack", "2pcs bundle set"): (clave del producto base, N). Si no, None."""
    brand, toks, sizes, mini = key
    digits = [t for t in toks if re.fullmatch(r"[2-9]", t)]
    pcs = [t for t in toks if re.fullmatch(r"[2-9]pcs?", t)]
    if not (pcs or (digits and toks & {"pack", "packs"})):
        return None
    n = int(pcs[0][0] if pcs else digits[0])
    return (brand, frozenset(toks - {"pack", "packs", "bundle", "set", "of", "pcs", *pcs, str(n)}), sizes, mini), n


def missing(db):
    """Listings que su tienda dejó de devolver (borrados o despublicados): {listing_id: cuándo se vio por última vez}.

    save() marca con la misma hora (`last_seen`) todo lo que devuelve una corrida, así que la última lectura de una tienda es su
    last_seen más reciente y lo que quedó atrás no vino en ella. Las tiendas de db.BY_BRAND (YesStyle, Stylevana) se leen por marca,
    no completas: ahí un listing solo falta si su marca se leyó completa (meta <prefijo>:<marca>) después de la última vez que se vio, y esa lectura
    alcanzó a guardarse (un last_seen de la marca posterior). Sin last_seen (bases de antes de la columna) no se marca nada hasta
    que la tienda se vuelva a leer."""
    try:
        rows = db.execute("SELECT l.id, l.store, l.vendor, l.last_seen, MAX(p.ts) FROM listing l JOIN price p ON p.listing_id = l.id GROUP BY l.id").fetchall()
        brand_read = {(store, k): v for store, pre in BY_BRAND.items()  # (tienda, marca) -> última lectura completa de esa marca
                      for k, v in db.execute("SELECT substr(key, ?), value FROM meta WHERE key LIKE ?", (len(pre) + 2, pre + ":%"))}
    except sqlite3.OperationalError:  # base creada antes de last_seen o de meta
        return {}
    def group(store, vendor):
        return (store, re.sub(r"[^a-z0-9]", "", words(vendor or ""))) if store in BY_BRAND else store
    last = {}  # tienda (o tienda + marca) -> su lectura más reciente
    for _, store, vendor, seen, _ in rows:
        if seen:
            k = group(store, vendor)
            last[k] = max(last.get(k, ""), seen)
    out = {}
    for lid, store, vendor, seen, price_ts in rows:
        k = group(store, vendor)
        read = brand_read.get(k) if store in BY_BRAND else last.get(k)
        if read and (seen or "") < read <= last.get(k, ""):
            out[lid] = seen or price_ts  # sin last_seen: su último precio es lo último confirmado
    return out


def price_drops(db, now=None):
    """{listing_id: precio de referencia}: el más alto que tuvo cada listing en CLP durante los últimos DEAL_DAYS, sin contar el precio actual.
    La tabla price solo guarda cambios, así que una fila vale desde su ts hasta el ts de la siguiente: cuenta si siguió vigente dentro de la
    ventana (la siguiente es de hace menos de DEAL_DAYS). La fila actual no tiene siguiente y queda fuera. Una sola consulta para todos."""
    since = ((now or datetime.now(timezone.utc)) - timedelta(days=DEAL_DAYS)).isoformat(timespec="seconds")
    return dict(db.execute("""
        SELECT listing_id, MAX(price) FROM (
          SELECT p.listing_id, p.price, LEAD(p.ts) OVER (PARTITION BY p.listing_id ORDER BY p.ts, p.rowid) AS nxt
          FROM price p JOIN listing l ON l.id = p.listing_id WHERE l.currency = 'CLP')
        WHERE nxt >= ? AND price BETWEEN ? AND ? GROUP BY listing_id""", (since, *PRICE_RANGE["CLP"])))  # un precio de relleno no es referencia


def price_since(db):
    """{listing_id: ts (UTC) desde el que rige su precio actual}: la última fila cuyo precio cambió frente a la anterior. Una fila que
    solo cambió el stock o el precio tachado no cuenta como un precio nuevo."""
    return dict(db.execute("""
        SELECT listing_id, MAX(ts) FROM (
          SELECT listing_id, ts, price, LAG(price) OVER (PARTITION BY listing_id ORDER BY ts, rowid) AS prev FROM price)
        WHERE prev IS NULL OR prev != price GROUP BY listing_id"""))


def local_day(ts):
    """Instante UTC guardado -> día en hora local ("2026-10-05"), o None."""
    return datetime.fromisoformat(ts).astimezone().date().isoformat() if ts else None


def discount(ref, price):
    """% entero que bajó `price` frente a `ref`, o 0 si no bajó. Una baja demasiado grande para creerla la marca antes db.anomaly()
    (la oferta queda "por confirmar" y sin stock), así que aquí no llega."""
    if not ref or price >= ref:
        return 0
    return round((ref - price) / ref * 100)


def size_label(sizes):
    return " + ".join(re.sub(r"(\d)(ml|g|oz|kg)$", r"\1 \2", s) for s in sizes)


# regalos y promos de las tiendas Shopify de las marcas: su "descripción" es relleno ("Gift with purchase only", "used for the app
# BOGOS.io... do not delete") y no describe el producto
GIFT = re.compile(r"🎁|free gift|gift with purchase|special price|100% off|bogos|do not delete|sample sachets?", re.I)


def brand_texts(db):
    """{marca (tupla de match.py): [(palabras, tamaños, mini, descripción, dominio)]} desde brand_text (sitios oficiales de las marcas).
    Sin packs: no se sabe a qué producto del set corresponde cada dato."""
    out = defaultdict(list)
    try:
        rows = db.execute("SELECT source, vendor, title, description FROM brand_text").fetchall()
    except sqlite3.OperationalError:  # base anterior a la tabla
        return out
    for source, vendor, title, desc in rows:
        b = tuple(re.findall(r"[a-z0-9]+", words(vendor or "").replace("&", " ")))
        if b and desc and not is_pack(title) and not GIFT.search(f"{title} {desc[:200]}") and len(desc) >= 60:
            _, toks, sizes, mini = key_of(vendor, title, {b})
            out[b].append((toks, sizes, mini, desc, source))
    return out


def official_text(index, brand, toks, sizes, mini):
    """(descripción, dominio) del sitio oficial de la marca para este producto, o (None, None). Solo si calza UN producto oficial (o varios
    con el mismo texto): misma marca y formato (mini o no), el mismo tamaño si los dos lo dicen, y las palabras de un nombre contenidas en las
    del otro con al menos 2 en común ("Relief Sun Aqua Fresh" con "Relief Sun Aqua-Fresh : Rice + B5"; el tono que nuestro título agrega,
    "Zero Velvet Tint 05 Witty", no estorba). Es más flexible que la clave de match.py porque solo aporta texto a describe.py: no une
    precios ni cambia ids. Con dos productos oficiales distintos posibles no se adivina."""
    found = {(d, s) for t, sz, m, d, s in index.get(brand, ()) if m == mini and len(t & toks) >= 2 and (t <= toks or toks <= t)
             and (not sz or not sizes or sz == sizes)}
    return next(iter(found)) if len({d for d, _ in found}) == 1 else (None, None)


def same_line(a, b):
    """¿Son el mismo producto en otra versión (otro tamaño, su miniatura, otro tono o el nombre mal escrito)? Misma marca y comparten la
    mayoría de las palabras del nombre ("Esencia Advanced Snail 96..." y "(Miniatura) Advanced Snail 96...": sí; dos sérums distintos: no)."""
    if a.brand_slug != b.brand_slug:
        return False
    ta, tb = set(words(a.name).split()) - MINI, set(words(b.name).split()) - MINI
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.5


class Catalog:
    def __init__(self, db, sync=True):
        """`sync`: anota en `db` los ids que cambiaron (listing.pid y product_alias, ver db.sync_aliases); False para armar el catálogo sin escribir."""
        ref, since, btexts = price_drops(db), price_since(db), brand_texts(db)
        self.products = []
        fx = db.execute("SELECT usd_clp, date FROM fx ORDER BY date DESC LIMIT 1").fetchone()
        self.usd_clp, self.fx_date = fx if fx else (None, None)
        try:
            scraped = dict(db.execute("SELECT substr(key, 9), value FROM meta WHERE key LIKE 'scraped:%'"))
        except sqlite3.OperationalError:  # base creada antes de la tabla meta
            scraped = {}
        # una tienda bloqueada (ej. YesStyle con 429) puede no completar nunca una corrida con total>0, así que
        # "scraped:<tienda>" nunca se escribe y quedaría afuera del cálculo para siempre, ocultando que sus precios
        # no se han vuelto a verificar. Si falta ese dato, se usa la fecha en que se vio por primera vez (la más
        # desfavorable posible), para que igual "se note" en vez de desaparecer del cálculo.
        first_seen = dict(db.execute("SELECT l.store, MIN(p.ts) FROM listing l JOIN price p ON p.listing_id = l.id GROUP BY l.store"))
        seen = {s: scraped.get(s) or first_seen[s] for s in first_seen if s not in RETIRED}  # tienda -> última lectura confirmada
        # "Sin conexión": la tienda no se pudo leer en la última corrida completa (sitio caído, dominio vencido, bloqueo).
        # Se compara con el inicio de esa corrida, no con el reloj ni con la tienda más al día: así una corrida a medias no marca
        # a las que todavía no le tocan, y si el scraping no corre en días no se marcan todas.
        try:
            done = db.execute("SELECT value FROM meta WHERE key = 'run:done'").fetchone()
        except sqlite3.OperationalError:
            done = None
        self.stale = {s: ts for s, ts in seen.items() if done and ts < done[0]}
        # la más antigua entre las que están al día; las sin conexión no desaparecen: se avisan una por una en su tienda y sus ofertas
        self.last_update = min((ts for s, ts in seen.items() if s not in self.stale), default=None)
        self.missing = missing(db)
        self.suspect = {}  # listing_id -> motivo: precio que parece un error de carga (db.anomaly), "por confirmar"
        groups, info = load_ex(db)
        try:  # precio con tarjeta (listing.card_price/card_name): se lee aparte y tolerante, una base sin las columnas no tiene ninguno
            cards = {i: (cp, cn) for i, cp, cn in db.execute("SELECT id, card_price, card_name FROM listing WHERE card_price IS NOT NULL")
                     if PRICE_RANGE["CLP"][0] <= cp <= PRICE_RANGE["CLP"][1]}
        except sqlite3.OperationalError:
            cards = {}
        brands_outside = {k[0] for k, rows in groups.items() if any(r[1] not in PHARMACY_STORES for r in rows)}  # marcas que vende alguna tienda no farmacia
        current = {}  # listing_id -> id del producto en que quedó
        spelling = defaultdict(Counter)  # marca -> grafías del vendor (CosRx / Cosrx / COSRX), gana la más común
        for (brand, *_), rows in groups.items():
            for r in rows:
                if r[12] == "CLP" and r[4] and tuple(re.findall(r"[a-z0-9]+", words(r[4]).replace("&", " "))) == brand:
                    spelling[brand][r[4]] += 1
        hints = {}  # id -> variante de la tienda que da el nombre (se usa solo si otro producto se llama igual)
        for (brand, toks, sizes, mini), rows in groups.items():
            # tienda sin conexión o producto que la tienda ya no lista: su último precio no se puede confirmar, así que cuenta como sin
            # stock (fuera del mejor precio y del "desde $X", al final de la lista) y se muestra con su aviso propio en vez de "sin stock"
            for r in rows:
                why = anomaly(r[6], ref.get(r[0]), r[12])  # ref solo existe para CLP; en USD se revisa solo el rango
                if why:
                    self.suspect[r[0]] = why
            # un precio anómalo tampoco se puede confirmar: mismo trato que las anteriores, con su propio aviso ("Precio por confirmar")
            rows = [r[:8] + (0,) + r[9:] if r[1] in self.stale or r[0] in self.missing or r[0] in self.suspect else r for r in rows]
            best = {}  # tienda -> fila más barata, prefiriendo con stock
            for r in rows:
                if r[12] == "CLP" and r[6] > 0 and (r[1] not in best or (r[8], -r[6]) > (best[r[1]][8], -best[r[1]][6])):
                    best[r[1]] = r
            foreign = {}  # tienda extranjera -> fila más barata, prefiriendo con stock (igual que `best`)
            for r in rows:
                if r[12] == "USD" and r[6] > 0 and (r[1] not in foreign or (r[8], -r[6]) > (foreign[r[1]][8], -foreign[r[1]][6])):
                    foreign[r[1]] = r
            if not best and not foreign:
                continue  # sin ningún precio válido en ninguna moneda: nada que mostrar
            pid = pid_of(brand, toks, sizes, mini)
            current.update((r[0], pid) for r in rows)
            rs = sorted(best.values(), key=lambda r: (not r[8], r[6]))
            offers = [Offer(r[0], r[1], r[6], r[7], bool(r[8]), r[5], r[10], r[11],
                            discount(ref.get(r[0]), r[6]) if r[8] else 0, self.stale.get(r[1]), self.missing.get(r[0]), self.suspect.get(r[0]),
                            *cards.get(r[0], (None, None)))
                      for r in rs]
            for o in offers:
                o.since = local_day(since.get(o.listing_id))
                o.ref = ref.get(o.listing_id) if o.drop else None
            fs = sorted(foreign.values(), key=lambda r: (not r[8], r[6]))
            if rs:
                display_price, display_is_estimate = offers[0].price, False  # offers ya viene ordenado con stock primero
            elif fs and self.usd_clp:
                display_price, display_is_estimate = clp_estimate(fs[0][6], self.usd_clp), True
            else:
                display_price, display_is_estimate = None, False  # sin dólar del día: no se puede estimar (raro, requiere que fx esté vacía)
            brand_name = spelling[brand].most_common(1)[0][0] if spelling[brand] else " ".join(brand).title()
            size = size_label(sizes)
            title_row = rs[0] if rs else fs[0]  # sin oferta chilena: el nombre sale de la tienda internacional
            hints[pid] = (title_row[3] or "").strip()
            name = clean(title_row[2], brand_name, size)
            gallery = []  # primero las imágenes de la mejor tienda, luego se completa con las de las demás
            firsts = {}  # host -> su primera imagen, en el mismo orden (la tienda más barata primero)
            for r in rs + fs:
                for u in (json.loads(r[14]) if r[14] else [r[9]] if r[9] else []):
                    if u not in gallery:
                        gallery.append(u)
                    firsts.setdefault(urlparse(u).netloc, u)
            # las imágenes se cargan desde cada tienda: si una se cae, sus fotos no cargan. El navegador prueba entonces la de otra tienda
            alts = [u for h, u in firsts.items() if gallery and h != urlparse(gallery[0]).netloc][:3]
            pack = any(is_pack(f"{r[2]} {r[3] or ''}") for r in rows)
            official, site = (None, None) if pack else official_text(btexts, brand, toks, sizes, mini)  # texto del sitio oficial de la marca
            full = norm(" ".join(f"{r[2]} {r[13] or ''}" for r in rows) + (" " + official if official else ""))
            attrs = attributes(name, full)
            listed = max((contents(r[13] or "") for r in rows), key=len, default=[]) if pack else []
            aliases, pack_text = frozenset(), ""
            if pack:
                pack_text = full
            else:
                names = {" ".join(w for w in norm(clean(r[2], brand_name, size)).split() if w not in MINI) for r in rows}  # sin "mini": la miniatura y el tamaño normal comparten nombre
                aliases = frozenset(a for a in names if len(a.split()) >= 2 and len(a) >= 9)
            self.products.append(Product(
                id=pid, name=name, brand=brand_name, brand_slug="-".join(brand) or "sin-marca", size=size, mini=mini,
                image=gallery[0] if gallery else None, images=gallery[:GALLERY], alts=alts, offers=offers,
                intl=sorted((IntlOffer(r[0], r[1], r[6], r[7], r[5], bool(r[8]), self.stale.get(r[1]), self.missing.get(r[0]),
                                      self.suspect.get(r[0])) for r in foreign.values()), key=lambda o: o.cents),
                display_price=display_price, display_is_estimate=display_is_estimate,
                search=words(" ".join([brand_name] + [r[2] for r in rows] + ([] if pack else attrs["terms"]))),  # los términos permiten buscar "sunscreen" o "niacinamida"
                key=(brand, toks, sizes, mini), matched_by="gtin" if (brand, toks, sizes, mini) in info["gtin"] else "nombre" if (brand, toks, sizes, mini) in info["similar"] else "texto", is_pack=pack, aliases=aliases, pack_text=pack_text, text=full, contents=listed,
                kind="" if pack else attrs["kind"] or "", group="" if pack else attrs["group"] or "", brand_site=site or "",
                skin=[] if pack else attrs["skin"], actives=[] if pack else attrs["actives"],
                section=section_of(brand, (brand in brands_outside) if brand else any(r[1] not in PHARMACY_STORES for r in rows)),
            ))
        # Varios productos con el mismo nombre (casi siempre tonos de maquillaje: "Ink Velvet" en 30 tonos) se distinguen por su
        # variante. Sin esto, el sitio mostraría 30 tarjetas iguales y los buscadores verían 30 páginas con el mismo título.
        same = defaultdict(list)
        for p in self.products:
            same[(p.brand_slug, p.name, p.size, p.mini, p.is_pack)].append(p)
        for ps in same.values():
            if len(ps) > 1:
                for p in ps:
                    p.variant = "" if hints.get(p.id, "").lower() in ("", "default title") else hints[p.id]
        self.by_id = {p.id: p for p in self.products}
        # brands, stores e intl_*: solo la sección asiática, lo que el sitio mostraba antes de que existiera la dermocosmética (sus páginas
        # no cambian); la otra sección tiene los suyos (derm_brands, derm_stores)
        self.section_counts = Counter(p.section for p in self.products)  # productos y packs por sección
        self.brands = {}  # slug -> [nombre, cantidad], sección asiática
        self.derm_brands = {}  # idem, dermocosmética
        for p in self.products:
            if not p.is_pack:
                (self.derm_brands if p.section == "dermocosmetica" else self.brands).setdefault(p.brand_slug, [p.brand or "Sin marca", 0])[1] += 1
        asian = [p for p in self.products if p.section == "asiatica"]
        self.stores = Counter(o.store for p in asian for o in p.offers)
        self.derm_stores = Counter(o.store for p in self.products if p.section == "dermocosmetica" for o in p.offers)
        self.intl_stores = Counter(o.store for p in asian for o in p.intl)  # todos, se vendan o no también en Chile
        self.intl_matched = Counter(o.store for p in asian if p.domestic for o in p.intl)  # el subconjunto que sí cruza con Chile
        # tienda -> % de baja de sus propias ofertas, contando lo mismo que verá Explorar con tienda=X y el filtro de ofertas (misma regla, _match): el número
        # del banner es exactamente el de la lista y no uno parecido
        by_store = defaultdict(list)
        for p in self.products:
            if self._match(p, stock=True):
                for o in p.offers:
                    if o.drop >= DEAL_PCT and o.store not in self.stale:
                        by_store[o.store].append(o.drop)
        # en orden alfabético por nombre visible, a propósito: el banner rota entre tiendas y el orden no debe insinuar preferencia
        self.deals = sorted(({"store": s, "name": store_name(s), "count": len(d), "median": round(statistics.median(d)), "max": max(d)}
                             for s, d in by_store.items() if len(d) >= DEAL_MIN), key=lambda x: words(x["name"]))
        self._facets = {}
        self._link_packs()
        # ids que cambiaron desde la última vez (cambio de reglas de matching o de datos): el viejo apunta al nuevo. Los listings sin id guardado
        # parten de su id por texto (antes de unir por GTIN), así el primer armado con GTIN no deja huérfanos los favoritos guardados.
        self.synced = False
        origin = info["origin"]
        baseline = lambda l: pid_of(*origin[l]) if l in origin else None
        if sync:
            # Si no hay pid previo, recuperar la clave histórica anterior a conservar SPF.
            # Así la primera reconstrucción también preserva enlaces de bases antiguas.
            if db.execute("SELECT 1 FROM listing WHERE pid IS NULL LIMIT 1").fetchone():
                legacy = load_ex(db, gtin=False, preserve_spf=False)[1]["origin"]
                baseline = lambda l: pid_of(*legacy[l]) if l in legacy else None
            self.alias, self.synced = sync_aliases(db, current, baseline, return_status=True)
        else:
            self.alias = {}

    def resolve(self, pid):
        """El id actual de un producto, sea `pid` vigente o un alias de un id anterior (favoritos y enlaces guardados); None si ya no existe."""
        seen = set()
        while pid not in self.by_id:
            if pid in seen or pid not in self.alias:
                return None
            seen.add(pid)
            pid = self.alias[pid]
        return pid

    def facets(self, stock=True, group="", section="asiatica"):
        """Cantidades por categoría, tipo de piel y compuesto. Con stock=True solo cuentan los productos con stock en alguna tienda, con
        `group` solo los de esa categoría y con `section` solo los de esa sección ("" = todas), igual que la lista, para que los números coincidan."""
        if (stock, group, section) not in self._facets:
            singles = [p for p in self.products if not p.is_pack and (p.in_stock or p.intl_in_stock or not stock) and (not group or p.group == group)
                       and (not section or p.section == section)]
            self._facets[(stock, group, section)] = {"groups": Counter(p.group for p in singles if p.group), "skin": Counter(s for p in singles for s in p.skin),
                                   "actives": Counter(a for p in singles for a in p.actives), "singles": singles}
        return self._facets[(stock, group, section)]

    def _link_packs(self):
        """Une cada pack con los productos que contiene. Multi-pack del mismo producto: exacto. Set con nombre: solo si el título o
        la descripción de las tiendas nombran al producto (misma marca); de 1 a 8 productos, más que eso es una coincidencia dudosa."""
        singles = [p for p in self.products if not p.is_pack]
        by_key = {p.key: p for p in singles}
        by_base, by_brand = defaultdict(list), defaultdict(list)  # (marca, palabras, miniatura) por si el pack no dice el tamaño
        for p in singles:
            by_base[(p.key[0], p.key[1], p.key[3])].append(p)
            by_brand[p.brand_slug].append(p)
        for pack in (p for p in self.products if p.is_pack):
            found = []
            pack.small_format = pack.mini or bool(SMALL_WORDS & set(pack.pack_text.split()))
            mb = multipack_base(pack.key)
            if mb:
                base_key, n = mb
                base = by_key.get(base_key)
                if base is None:
                    same = by_base.get((base_key[0], base_key[1], base_key[3]), [])
                    base = same[0] if len(same) == 1 else None
                if base:
                    found = [(base, n)]
            if not found and pack.contents and pack.brand_slug != "sin-marca":
                chosen = {}
                for iname_raw, size in pack.contents:
                    iname = " ".join(w for w in norm(iname_raw).split() if w not in MINI)  # sin "mini": el mini y el normal comparten nombre
                    cands = [(len(a), s) for s in by_brand[pack.brand_slug] for a in s.aliases if f" {a} " in f" {iname} "]
                    group = []
                    if cands:
                        best = max(n for n, _ in cands)
                        group = list({s.id: s for n, s in cands if n == best}.values())
                        if len(group) > 1:
                            group = [s for s in group if s.mini == pack.small_format]  # un pack de miniaturas contiene miniaturas
                        if len(group) > 1:  # sigue habiendo varios tamaños del mismo nombre: ya sabemos cuál trae ESTE pack
                            by_size = [s for s in group if s.size == size]
                            if len(by_size) == 1:
                                group = by_size
                    single = group[0] if len(group) == 1 else None  # si sigue habiendo varios no se adivina
                    pack.content_rows.append((iname_raw, size, single.id if single else None))
                    if single:
                        chosen[single.id] = (single, size)
                found = [(s, 1) for s, _ in chosen.values()]
                for s, size in chosen.values():
                    pack.pack_sizes[s.id] = size  # el tamaño que enumera la tienda manda sobre el que se deduzca del texto
            elif not found and pack.brand_slug != "sin-marca":
                by_name = defaultdict(list)  # nombre que coincide -> productos con ese nombre (varios si hay tamaños o tonos)
                for s in by_brand[pack.brand_slug]:
                    named = [a for a in s.aliases if f" {a} " in pack.pack_text]
                    if named:
                        by_name[max(named, key=len)].append(s)
                chosen = {}
                for alias, group in by_name.items():
                    if len(group) > 1:
                        group = [s for s in group if s.mini == pack.small_format]  # un pack de miniaturas contiene miniaturas
                    if len(group) > 1:  # sigue habiendo varios tamaños del mismo nombre: buscar el tamaño que la descripción menciona junto a él
                        wanted = size_after(pack.pack_text, alias)
                        by_size = [s for s in group if s.size == wanted] if wanted else []
                        if len(by_size) == 1:
                            group = by_size
                    if len(group) == 1:  # si sigue habiendo varios (otro tamaño u otro tono) no se adivina
                        chosen[group[0].id] = (group[0], alias)
                if 1 <= len(chosen) <= 8:
                    found = [(s, 1) for s, _ in chosen.values()]
                    for s, alias in chosen.values():
                        if size := size_after(pack.pack_text, alias):
                            pack.pack_sizes[s.id] = size
            for s, n in found:
                pack.includes.append((s.id, n))
                s.included_in.append((pack.id, n))

    def top_brands(self, n, section="asiatica"):
        """Marcas con más productos en la sección: [(slug, nombre, cantidad)]."""
        brands = self.derm_brands if section == "dermocosmetica" else self.brands
        c = sorted(((k, v[0], v[1]) for k, v in brands.items() if k != "sin-marca"), key=lambda x: -x[2])
        return c[:n]

    def top_spread(self, n=8, section="asiatica"):
        """Productos con tamaño conocido, en 2+ tiendas con stock, con la mayor diferencia de precio (tope 50% para evitar errores de matching)."""
        c = [p for p in self.products if not p.is_pack and p.size and len(p.in_stock) > 1 and p.spread <= 0.5 and (not section or p.section == section)]
        return sorted(c, key=lambda p: -p.spread)[:n]

    def drops(self, n=8, section="asiatica"):
        return sorted((p for p in self.products if not p.is_pack and p.drop > 0 and (not section or p.section == section)), key=lambda p: -p.drop)[:n]

    @staticmethod
    def _match(p, tokens=(), brand="", stores=(), pmin=None, pmax=None, stock=False, multi=False, packs=False,
               group="", kinds=(), skins=(), actives=(), deals=False, section="asiatica", event=None):
        """¿El producto pasa los filtros de Explorar? search() y counts() usan esta misma regla, así sus números no se contradicen.
        `section`: "asiatica" por defecto, a propósito: así Explorar, el banner de ofertas, /tiendas y todo lo que ya existía siguen dando lo de
        siempre sin tocarlos; la dermocosmética hay que pedirla ("dermocosmetica"), y "" junta las dos."""
        if section and p.section != section:
            return False
        if p.is_pack != packs or brand and p.brand_slug != brand:
            return False
        if group and p.group != group or kinds and p.kind not in kinds:
            return False
        if skins and not set(skins) & set(p.skin) or actives and not set(actives) & set(p.actives):
            return False
        if stores and not {o.store for o in p.offers} & set(stores):
            return False
        if stock and not p.in_stock and not p.intl_in_stock:  # "con stock" cuenta tanto tiendas chilenas como internacionales
            return False
        if multi and len(p.offers) < 2:
            return False
        # baja real en nuestro historial, no el precio tachado de la tienda. Con tiendas elegidas, la baja tiene que ser de esas tiendas:
        # si no, una tienda que no bajó nada aparecería "con ofertas" solo porque otra tienda rebajó un producto que ambas venden
        if deals and (max((o.drop for o in p.offers if o.store in stores), default=0) if stores else p.drop) < DEAL_PCT:
            return False
        if event and (max((o.drop for o in p.offers if o.store in stores and in_event(o, event)), default=0) if stores else p.event_drop(event)) < DEAL_PCT:
            return False
        if pmin is not None and (p.display_price is None or p.display_price < pmin):
            return False
        if pmax is not None and (p.display_price is None or p.display_price > pmax):
            return False
        return all(t in p.search for t in tokens)

    FACETS = {"cat": ("group", lambda p: [p.group] if p.group else []), "tipo": ("kinds", lambda p: [p.kind] if p.kind else []),
              "piel": ("skins", lambda p: p.skin), "ing": ("actives", lambda p: p.actives), "tienda": ("stores", lambda p: {o.store for o in p.offers})}

    def counts(self, q="", **filters):
        """El número de cada opción de los filtros de Explorar: cuántos productos quedan al marcarla, con los DEMÁS filtros aplicados
        (las opciones de un mismo filtro se suman entre sí, como en search()). Así el número coincide con la lista que se va a ver."""
        filters["tokens"] = words(q).split()
        out = {name: Counter(v for p in self.products if self._match(p, **{**filters, key: ()}) for v in values(p))
               for name, (key, values) in self.FACETS.items()}
        if filters.get("deals"):  # con el filtro de ofertas, cada tienda cuenta solo sus propias bajas (misma regla que _match con tiendas)
            rest = {**filters, "stores": (), "deals": False}
            out["tienda"] = Counter(o.store for p in self.products if self._match(p, **rest) for o in p.offers if o.drop >= DEAL_PCT)
        if filters.get("event"):  # en un evento, igual: cada tienda cuenta solo sus propias bajas del evento
            ev, rest = filters["event"], {**filters, "stores": (), "event": None}
            out["tienda"] = Counter(o.store for p in self.products if self._match(p, **rest) for o in p.offers if in_event(o, ev))
        return out

    def search(self, q="", brand="", stores=(), pmin=None, pmax=None, stock=False, multi=False, sort="", page=1, packs=False,
               group="", kinds=(), skins=(), actives=(), deals=False, section="asiatica", event=None):
        """packs=False: solo productos individuales; packs=True: solo packs. section: ver _match (por defecto solo asiática)."""
        f = dict(tokens=words(q).split(), brand=brand, stores=stores, pmin=pmin, pmax=pmax, stock=stock, multi=multi, packs=packs,
                 group=group, kinds=kinds, skins=skins, actives=actives, deals=deals, section=section, event=event)
        out = [p for p in self.products if self._match(p, **f)]
        price = lambda p: p.display_price if p.display_price is not None else 0  # sin dólar del día (rarísimo): se va al final igual
        keys = {
            "precio_asc": lambda p: (not (p.in_stock or p.intl_in_stock), price(p)),
            "precio_desc": lambda p: (not (p.in_stock or p.intl_in_stock), -price(p)),
            "ahorro": lambda p: -p.spread,
            "nombre": lambda p: words(p.name),
            "descuento": lambda p: (-(p.event_drop(event) if event else p.drop), words(p.name)),
        }
        out.sort(key=keys.get(sort) or (lambda p: (-len(p.offers) * bool(p.in_stock), not p.in_stock, words(p.name))))
        start = (page - 1) * PAGE_SIZE
        return out[start:start + PAGE_SIZE], len(out)

    def deal_picks(self, n=24, seed=None, section="asiatica", per_brand=2):
        """Productos para la franja de ofertas del inicio: el mejor precio de hoy bajó al menos DEAL_SHOW% frente a nuestro historial, con
        stock y sin packs. Sin favoritismo: se agrupan por la tienda que tiene ese precio y se intercalan (una de cada tienda por vuelta, en
        orden alfabético), así una tienda con cientos de rebajas no tapa a las demás. Dentro de cada tienda el orden cambia con `seed`
        (server pasa la hora: la franja rota sola), con a lo más `per_brand` por marca y sin otras versiones del mismo producto."""
        rng, by_store = random.Random(seed), defaultdict(list)
        for p in self.products:
            if not p.is_pack and (not section or p.section == section) and p.drop >= DEAL_SHOW and p.in_stock:
                s = p.in_stock
                o = max((o for o in s if o.price == s[0].price), key=lambda o: o.drop)  # la oferta que respalda p.drop
                by_store[o.store].append(p)
        queues = []
        for store in sorted(by_store, key=lambda d: words(store_name(d))):
            ps = sorted(by_store[store], key=lambda p: p.id)  # orden estable antes de mezclar: mismo seed, misma franja
            rng.shuffle(ps)
            queues.append(ps)
        out, per = [], Counter()
        while queues and len(out) < n:
            for q in list(queues):
                while q:
                    p = q.pop()
                    if per[p.brand_slug] < per_brand and not any(same_line(p, x) for x in out):
                        out.append(p)
                        per[p.brand_slug] += 1
                        break
                if not q:
                    queues.remove(q)
                if len(out) == n:
                    break
        return out

    def related(self, p, n=8, per_brand=2):
        """"También te podría interesar": productos del mismo tipo (si no se sabe, de la misma categoría), de la misma sección y con stock,
        ordenados por afinidad (ingredientes y tipos de piel en común, misma marca) y luego por cuántas tiendas los venden. Sin otros tonos del
        mismo producto (mismo nombre) y con a lo más `per_brand` por marca, para que haya variedad. Sin tipo ni categoría: nada (no se adivina)."""
        if not (p.kind or p.group):
            return []
        acts, skin = set(p.actives), set(p.skin)

        def score(c):
            return (len(acts & set(c.actives)) * 2 + len(skin & set(c.skin)) + (c.brand_slug == p.brand_slug), len(c.in_stock), c.id)

        same = (lambda c: c.kind == p.kind) if p.kind else (lambda c: c.group == p.group)
        cands = sorted((c for c in self.products if c is not p and c.is_pack == p.is_pack and c.section == p.section and same(c)
                        and (c.in_stock or c.intl_in_stock)), key=score, reverse=True)
        out, per = [], Counter()
        for c in cands:
            if per[c.brand_slug] < per_brand and not any(same_line(c, x) for x in [p] + out):
                out.append(c)
                per[c.brand_slug] += 1
                if len(out) == n:
                    break
        return out

    def suggest(self, q, n=6, section="asiatica"):
        """Sugerencias del buscador mientras se escribe: productos y packs con todas las palabras, primero los que tienen stock y
        están en más tiendas (los packs después de los individuales). Solo de la sección ("" = todas), como la búsqueda."""
        tokens = words(q).split()
        out = [p for p in self.products if tokens and all(t in p.search for t in tokens) and (not section or p.section == section)]
        out.sort(key=lambda p: (not (p.in_stock or p.intl_in_stock), p.is_pack, -len(p.offers), words(p.name)))
        return out[:n]

    def history(self, db, product):
        """Cambios de precio por tienda: {tienda: [(fecha, precio, disponible), ...]}."""
        return {o.store: db.execute("SELECT substr(ts,1,10), price, available FROM price WHERE listing_id=? ORDER BY ts, rowid",
                                    (o.listing_id,)).fetchall() for o in product.offers}


_cache = {"mtime": None, "built": 0.0, "catalog": None}
_cache_lock = threading.Lock()
REFRESH = 60  # segundos mínimos entre reconstrucciones (ratings.py escribe en la base mientras el sitio corre)


def get_catalog():
    """Catálogo en memoria; se reconstruye si cambió la base de datos y pasó al menos REFRESH segundos."""
    with _cache_lock:
        mtime = DB.stat().st_mtime
        cached = _cache["catalog"]
        if cached is None or ((_cache["mtime"] != mtime or not cached.synced) and time.time() - _cache["built"] > REFRESH):
            db = connect(DB)
            try:
                cat = Catalog(db)
            finally:
                db.close()
            _cache.update(mtime=DB.stat().st_mtime if cat.synced else mtime, built=time.time(), catalog=cat)
        return _cache["catalog"]
