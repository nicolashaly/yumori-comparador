"""Servidor web local de Yumori (solo stdlib).

Uso: python server.py [puerto]   ->   http://127.0.0.1:8000
"""
import json
import mimetypes
import os
import sqlite3
import sys
import threading
import traceback
from datetime import datetime
from html import escape as e
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from catalog import DEAL_DAYS, DEAL_PCT, DEAL_SHOW, INTL_STORES, PAGE_SIZE, PHARMACY_STORES, clp_estimate, get_catalog, store_name
import legal
import api
from catalog import event_for, in_event, live_event, opens
from describe import GROUPS, describe
from shipping import REVIEWED as SHIP_REVIEWED, SHIPPING
from match import clp
from db import BY_BRAND, DB, PARTIAL

STATIC = Path(__file__).parent / "static"
# URL pública del sitio (canónicas, Open Graph, sitemap). Al publicar, definir YUMORI_URL=https://dominio; sin ella se usa el Host de
# cada solicitud, que en local es http://127.0.0.1:8000.
SITE_URL = os.environ.get("YUMORI_URL", "").rstrip("/")
REQ = threading.local()  # base de la solicitud en curso (el servidor atiende cada solicitud en su propio hilo)
SITE_DESC = ("Compara precios de skincare, maquillaje y cuidado personal coreano, japonés y chino en tiendas de Chile, "
             "y encuentra dónde está más barato.")
SORTS = [("", "Relevancia"), ("precio_asc", "Precio: menor a mayor"), ("precio_desc", "Precio: mayor a menor"),
         ("ahorro", "Mayor diferencia entre tiendas"), ("descuento", "Mayor descuento"), ("nombre", "Nombre")]
DERM = "dermocosmetica"  # sección aparte (ver Catalog.section); la asiática es la de siempre y no necesita nombre
# Tiendas de dermocosmética que no se leen (Falabella nos bloqueó, Salcobrand prohíbe extraer, Cruz Verde solo existe con JavaScript): la ficha
# enlaza a su buscador y la persona mira. (nombre, URL de búsqueda, parámetro). Ver docs/scraping/stores.md.
SEARCH_ELSEWHERE = [("Cruz Verde", "https://www.cruzverde.cl/search?", "query"), ("Falabella", "https://www.falabella.com/falabella-cl/search?", "Ntt"),
                    ("Salcobrand", "https://salcobrand.cl/search_result?", "query")]
ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "heart": '<path d="M12 20s-7-4.4-9.3-9A5.2 5.2 0 0 1 12 6.5 5.2 5.2 0 0 1 21.3 11C19 15.6 12 20 12 20z"/>',
    "filter": '<path d="M4 6h16M7 12h10M10 18h4"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
    "tag": '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
}


def icon(name):
    return (f'<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def fmt(n):
    return f"{n:,}".replace(",", ".")


MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()


MESES_LARGOS = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def shipping_text(store):
    """El despacho de la tienda en una línea ("Despacho desde $3.990 · gratis sobre $59.990 en todo Chile"), o "" si no lo revisamos.
    Es un dato de la tienda, revisado a mano (ver shipping.py): nunca se suma al precio ni cambia el mejor precio."""
    s = SHIPPING.get(store)
    if not s:
        return ""
    parts = [f"desde {clp(s['desde'])}"] if s["desde"] else []
    if s["gratis"]:
        parts.append(f"gratis sobre {clp(s['gratis'])}" + (f" en {s['donde']}" if s["donde"] else ""))
    text = ("Despacho " + " · ".join(parts)) if parts else ("" if s.get("nota") else "Despacho no informado")
    return " · ".join(x for x in (text, s.get("nota", "")) if x)


EVENT_ICONS = {"cyber": "bolt", "black-friday": "tag", "cyberday": "bolt"}  # el logo propio de cada evento (colores en style.css)


def event_dates(ev):
    """"del 5 al 7 de octubre" (o "del 30 de septiembre al 2 de octubre")."""
    (_, m1, d1), (_, m2, d2) = ev["start"].split("-"), ev["end"].split("-")
    first = f"{int(d1)}" if m1 == m2 else f"{int(d1)} de {MESES_LARGOS[int(m1) - 1]}"
    return f"del {first} al {int(d2)} de {MESES_LARGOS[int(m2) - 1]}"


def today():
    return datetime.now().date().isoformat()  # hora local (Chile), igual que catalog.live_event


def event_logo(ev, cls=""):
    """Logo propio del evento: su ícono y su nombre con los colores de su tema. No es el logo oficial de nadie (son marcas registradas)."""
    return (f'<span class="ev-logo ev-{e(ev.get("theme", "cyber"))}{" " + cls if cls else ""}">'
            f'{icon(EVENT_ICONS.get(ev.get("theme"), "bolt"))}<span>{e(ev["name"])}</span></span>')


def fecha(iso):
    y, m, d = iso.split("-")
    return f"{int(d)} {MESES[int(m) - 1]} {y}"


def offline(o):
    """Aviso de una oferta que no se pudo confirmar en la última lectura: la tienda no respondió (stale), respondió sin este producto
    (gone) o publicó un precio que parece un error de carga (suspect). Neutro a propósito: no afirma que la tienda cerró, que el
    producto se descontinuó ni que el precio esté mal, solo lo que vimos."""
    if o.suspect:
        return ['<span class="tag tag-off">Precio por confirmar</span>', "<span>Muy distinto del habitual: confírmalo en la tienda</span>"]
    return [f'<span class="tag tag-off">{gone_label(o)[0]}</span>', f"<span>Último precio visto el {fecha((o.stale or o.gone)[:10])}</span>"]


def gone_label(o):
    """(etiqueta, frase del resumen). YesStyle y Stylevana se leen solo en parte (por marca, db.BY_BRAND): que no lo volvamos a ver no significa que
    la tienda lo haya sacado, solo que no lo leímos, así que ahí se dice "Sin actualizar" y no "No aparece en la tienda". Igual con las de
    db.PARTIAL (Paris, Farmaloop), que solo muestran una parte de cada listado."""
    if o.stale:
        return "Sin conexión", "Tienda sin conexión"
    if o.store in BY_BRAND or o.store in PARTIAL:
        return "Sin actualizar", "Precio sin actualizar"
    return "No aparece en la tienda", "Ya no aparece en la tienda"


def unconfirmed(o):
    """Resumen de arriba en la página de producto cuando la mejor oferta que queda no se pudo confirmar ("" si sí)."""
    if o.suspect:
        return "Precio por confirmar: muy distinto del habitual en esta tienda"
    return f"{gone_label(o)[1]}: último precio visto el {fecha((o.stale or o.gone)[:10])}" if o.stale or o.gone else ""


def usd(cents):
    """Centavos de USD -> 'US$1.234,50' (formato chileno)."""
    return "US$" + f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def stamp(iso):
    """Marca de tiempo UTC guardada -> "21 sep 2026, 20:10" en la hora local."""
    d = datetime.fromisoformat(iso).astimezone()
    return f"{d.day} {MESES[d.month - 1]} {d.year}, {d:%H:%M}"


def stars(rating, reviews):
    return f"★ {rating:.1f}".replace(".", ",") + f" · {reviews} reseña{'s' if reviews != 1 else ''}"


# ---------- piezas ----------

def absolute(path):
    return getattr(REQ, "base", SITE_URL) + path


def ld_json(data):
    """Datos estructurados (schema.org) en un <script type="application/ld+json">. No se ejecuta, así que la CSP no lo bloquea;
    "<" se escapa para que un texto con "</script>" no pueda cerrar la etiqueta."""
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("<", "\\u003c") + "</script>"


def clip(text, n=158):
    """Recorta una meta descripción en el último espacio antes de `n` caracteres (Google muestra ~155-160)."""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",;:·") + "…"


def head_meta(title, description, canonical, robots, image, og_type, jsonld):
    """Lo que leen buscadores y redes sociales: descripción, canónica, robots, Open Graph y datos estructurados."""
    url = absolute(canonical) if canonical is not None else ""
    tags = [f'<meta name="description" content="{e(clip(description or SITE_DESC))}">']
    if robots:
        tags.append(f'<meta name="robots" content="{robots}">')
    if url:
        tags.append(f'<link rel="canonical" href="{e(url)}">')
    og = {"og:site_name": "Yumori", "og:locale": "es_CL", "og:type": og_type, "og:title": title,
          "og:description": clip(description or SITE_DESC, 200), "og:url": url, "og:image": image}
    tags += [f'<meta property="{k}" content="{e(v)}">' for k, v in og.items() if v]
    tags.append(f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">')
    tags += [ld_json(d) for d in jsonld]
    return "\n".join(tags)


def layout(title, body, q="", show_search=True, current="", description="", canonical=None, robots="", image="", og_type="website", jsonld=(), search_action="/explorar"):
    search = (f'<form class="search" role="search" action="{search_action}">{icon("search")}'
              f'<input type="search" name="q" value="{e(q)}" placeholder="Buscar productos o marcas…" aria-label="Buscar" autocomplete="off">'
              f'<kbd>/</kbd></form>') if show_search else ""

    def link(href, text, cls=""):
        return f'<a href="{href}" class="{cls}"{" aria-current=page" if current == href else ""}>{text}</a>'

    cat = get_catalog()
    live = live_event()
    event_link = (f'<a class="nav-event" href="/{e(live["slug"])}" aria-label="{e(live["name"])}: rebajas detectadas"'
                  f'{" aria-current=page" if current == "/" + live["slug"] else ""}>{event_logo(live)}</a>') if live else ""
    cats_menu = (f'<div class="nav-item hide-sm">{link("/explorar", "Categorías")}<div class="dropdown"><div class="dropdown-panel">'
                 + "".join(f'<a class="chip" href="/explorar?cat={slug}">{e(name)} <span class="n">{fmt(cat.facets(True)["groups"].get(slug, 0))}</span></a>' for slug, name in GROUPS.items())
                 + '</div></div></div>')
    updated = f"Precios revisados por última vez el {stamp(cat.last_update)}. " if cat.last_update else ""
    top = "".join(f'<a class="chip" href="/explorar?marca={e(slug)}">{e(name)} <span class="n">{n}</span></a>' for slug, name, n in cat.top_brands(5))
    brands_menu = (f'<div class="nav-item hide-sm">{link("/marcas", "Marcas")}'
                   f'<div class="dropdown"><div class="dropdown-panel">{top}<a class="chip chip-accent" href="/marcas">Mostrar todas</a></div></div></div>')

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
{head_meta(title, description, canonical, robots, image, og_type, jsonld)}
<meta name="theme-color" content="#FCFAF7">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='13' fill='%23FADDE3'/%3E%3Ccircle cx='16' cy='16' r='5' fill='%23B0456A'/%3E%3C/svg%3E">
<link rel="stylesheet" href="/static/style.css"></head><body>
<div class="sakura" aria-hidden="true"></div>
<a class="skip" href="#main">Saltar al contenido</a>
<header class="navbar"><div class="container">
<a class="logo" href="/"><i></i>Yumori</a>{search}
<nav class="nav-links" aria-label="Principal">{event_link}{cats_menu}{brands_menu}{link("/tiendas", "Tiendas", "hide-sm")}{link("/packs", "Packs", "hide-sm")}{link("/dermocosmetica", "Dermocosmética", "hide-sm")}
<a href="/favoritos" aria-label="Favoritos"{" aria-current=page" if current == "/favoritos" else ""}>{icon("heart")}<span class="label">Favoritos</span><span class="fav-count"></span></a></nav>
<details class="menu"><summary class="btn btn-ghost btn-icon" aria-label="Menú">{icon("menu")}</summary>
<div class="menu-panel">{"".join(f'<a href="/explorar?cat={slug}">{e(name)}</a>' for slug, name in GROUPS.items())}<a href="/marcas">Marcas</a><a href="/tiendas">Tiendas</a><a href="/packs">Packs</a><a href="/dermocosmetica">Dermocosmética</a></div></details>
</div></header>
<main id="main" tabindex="-1">{body}</main>
<footer><div class="container"><p>Yumori compara precios de tiendas chilenas y del extranjero; no vende productos. {updated}Confirma siempre el precio y el stock en la tienda antes de comprar.</p>
<nav class="legal-links" aria-label="Información legal"><a href="/privacidad">Privacidad</a><a href="/terminos">Términos</a><a href="/cookies">Cookies</a></nav></div></footer>
<script src="/static/app.js" defer></script></body></html>"""


def img(url, alt="", alts=()):
    """`alts`: imágenes de respaldo de otras tiendas, que app.js prueba si esta no carga (la tienda está caída o no responde)."""
    if not url:
        return '<span class="no-img">Sin imagen</span>'
    backup = f' data-alts="{e(json.dumps(list(alts)))}"' if alts else ""
    return f'<img data-src-fade loading="lazy" decoding="async" referrerpolicy="no-referrer" src="{e(url)}" alt="{e(alt)}"{backup}>'


def price_bits(p):
    """(prefijo, precio o None, tiendas) de un producto, lo que comparten card() y las sugerencias del buscador."""
    n, stock = len(p.offers), p.in_stock
    if not p.domestic:
        return "Estimado", clp(p.display_price) if p.display_price is not None else None, "Solo en el extranjero"
    unconfirmed_only = not stock and all(o.stale or o.gone or o.suspect for o in p.offers)  # sin conexión, ya no lo listan o precio por confirmar
    prefix = "desde" if len(stock) > 1 else "" if stock else "sin confirmar" if unconfirmed_only else "sin stock"
    return prefix, clp(p.min_price), f"en {n} tiendas" if n > 1 else "1 tienda"


def deal_pill(p):
    """Etiqueta "-30%" de un producto que bajó (Product.drop frente a los últimos DEAL_DAYS días), o "" si no. Compartida por card() y las sugerencias."""
    if p.drop < DEAL_PCT:
        return ""
    return (f'<span class="deal-pill" title="Bajó {p.drop}% frente al precio más alto de los últimos {DEAL_DAYS} días">'
            f'<span aria-hidden="true">−{p.drop}%</span><span class="sr-only">Bajó {p.drop}%</span></span>')


def was(p):
    """El precio "antes" tachado al lado del precio, solo si hay etiqueta de descuento: es la misma referencia de deal_pill (el precio más alto
    que vimos en esa tienda en los últimos DEAL_DAYS días), nunca el precio tachado que publica la tienda (puede estar inflado)."""
    if p.drop < DEAL_PCT or not p.drop_ref:
        return ""
    return f' <s class="was"><span class="sr-only">Antes: </span>{clp(p.drop_ref)}</s>'


def card(p, note=""):
    prefix, amount, tiendas = price_bits(p)
    price = (f'<p class="card-price">{f"<small>{prefix}</small>" if prefix else ""}{amount}{was(p)}</p>' if amount
             else '<p class="card-price muted" style="font-size:var(--fs-md)">Ver precio</p>')
    meta = " · ".join(x for x in (("Pack mini" if p.small_format else "Pack") if p.is_pack else "", p.variant, p.size, "Miniatura" if p.mini else "", tiendas) if x)
    r = p.rating
    rating = (f'<span class="card-rating" title="{e(stars(r.rating, r.reviews))} en {e(store_name(r.store))}" '
              f'aria-label="Valoración {r.rating:.1f} de 5, {r.reviews} reseñas en {e(store_name(r.store))}">'
              f'<i aria-hidden="true">★</i>{f"{r.rating:.1f}".replace(".", ",")}</span>') if r else ""
    # toda la tarjeta lleva al producto (el ::after de .card-link la cubre), y la marca es un enlace aparte, encima, a todos sus productos
    # en su sección: un enlace no puede ir dentro de otro
    base = ("/dermocosmetica/packs" if p.is_pack else "/dermocosmetica") if p.section == DERM else "/packs" if p.is_pack else "/explorar"
    brand = (f'<a class="card-brand" href="{base}?{urlencode({"marca": p.brand_slug})}">{e(p.brand)}</a>' if p.brand_slug != "sin-marca"
             else f'<p class="card-brand">{e(p.brand)}</p>')
    return f"""<article class="card"><a class="card-link" href="/p/{p.id}">
<div class="card-img skeleton{'' if p.image else ' done'}">{img(p.image, alts=p.alts)}{deal_pill(p)}</div><h3 class="card-name">{e(p.name)}</h3></a>
<div class="card-body{" has-rating" if r else ""}">{brand}{price}<p class="card-meta">{e(meta)}</p>{f'<p class="card-note">{e(note)}</p>' if note else ""}{rating}</div>
<button class="fav" data-fav="{p.id}" aria-pressed="false" aria-label="Guardar {e(p.name)} en favoritos">{icon("heart")}</button></article>"""


def suggestions(cat, q):
    """Lista del buscador mientras se escribe (la pide app.js): tarjetas horizontales de productos reales, con miniatura al final,
    y un enlace a Explorar con el total que se va a ver ahí (sin packs ni agotados, igual que Explorar por defecto).
    Primero lo asiático (el foco del sitio) y, si sobra espacio, dermocosmética con su etiqueta; si esa sección también tiene resultados,
    su propio enlace "Ver ... en Dermocosmética" (así "eucerin" se encuentra desde cualquier página sin mezclar los dos listados)."""
    q = q.strip()[:100]
    items = cat.suggest(q)
    derm = cat.suggest(q, n=6 - len(items), section=DERM) if len(items) < 6 else []
    if not items and not derm:
        return f'<p class="sug-empty">No encontramos productos para «{e(q)}».</p>'
    rows = []
    for i, p in enumerate(items + derm):
        prefix, amount, tiendas = price_bits(p)
        meta = " · ".join(x for x in ("Dermocosmética" if p.section == DERM else "", p.brand, p.variant, p.size, "Pack" if p.is_pack else "", tiendas) if x)
        price = f'<span class="sug-price">{f"<small>{prefix}</small>" if prefix else ""}{amount or "Ver precio"}{was(p) if amount else ""}{deal_pill(p)}</span>'
        rows.append(f'<a class="sug" id="sug-{i}" role="option" aria-selected="false" href="/p/{p.id}"><span class="sug-body">'
                    f'<span class="sug-name">{e(p.name)}</span><span class="sug-meta">{e(meta)}</span>{price}</span>'
                    f'<span class="sug-img{"" if p.image else " done"}">{img(p.image, alts=p.alts)}</span></a>')
    for base, section, sid, where in (("/explorar", "asiatica", "sug-all", "Explorar"), ("/dermocosmetica", DERM, "sug-all-derm", "Dermocosmética")):
        total = cat.search(q, stock=True, section=section)[1]
        if total:
            rows.append(f'<a class="sug sug-all" id="{sid}" role="option" aria-selected="false" href="{base}?{urlencode({"q": q})}">'
                        f'Ver {"el resultado" if total == 1 else f"los {fmt(total)} resultados"} en {where}</a>')
    return "".join(rows)


def page(title, body, **kw):
    return 200, layout(title, body, **kw)


# ---------- páginas ----------

def event_callout(cat):
    """Aviso del evento en curso en el inicio, solo si ya detectamos rebajas (sin rebajas no se promete nada)."""
    ev = live_event()
    if not ev:
        return ""
    total = cat.search(stock=True, section="", event=ev)[1]
    if not total:
        return ""
    stores = {o.store for p in cat.products if not p.is_pack and p.event_drop(ev) for o in p.offers if in_event(o, ev)}
    return (f'<a class="event-callout" href="/{e(ev["slug"])}"><span>{event_logo(ev, "ev-md")} {event_dates(ev)}<br>'
            f'{fmt(total)} producto{"s" if total != 1 else ""} rebajado{"s" if total != 1 else ""} en '
            f'{len(stores)} tienda{"s" if len(stores) != 1 else ""}</span><span class="btn btn-primary btn-sm" aria-hidden="true">Ver {e(ev["name"])}</span></a>')


def deals_banner(cat):
    """Franja de ofertas del inicio: tarjetas de productos con una baja real de al menos DEAL_SHOW% (Catalog.deal_picks), que cambian cada
    hora. En pantallas con mouse avanza sola (app.js); en celular y tablet se desliza con el dedo. "Ver las N ofertas" lleva a Explorar con
    el filtro de descuento, y N es exactamente el total que se ve ahí. Vacía si no hay ninguna oferta así."""
    picks = cat.deal_picks(seed=datetime.now().strftime("%Y-%m-%d %H"))
    if not picks:
        return ""
    total = cat.search(stock=True, deals=True)[1]
    href = "/explorar?" + urlencode([("oferta", "1"), ("orden", "descuento")])
    return (f'<section class="deals" data-deals aria-label="Ofertas detectadas">'
            f'<div class="deals-head"><h2>Ofertas detectadas</h2><a class="link deals-all" href="{e(href)}">Ver las {fmt(total)} ofertas</a></div>'
            f'<div class="deals-track" tabindex="0" aria-label="Productos rebajados: desliza para ver más">{"".join(card(p) for p in picks)}</div>'
            f'<p class="deals-note">Bajas de al menos {DEAL_SHOW}% frente al precio más alto que Yumori vio en cada tienda en los últimos {DEAL_DAYS} días. '
            f'No es publicidad ni una promoción informada por las tiendas.</p></section>')


HERO_DECO = (  # adornos propios del inicio: destellos y flores de cerezo, solo decorativos (aria-hidden)
    '<svg class="hero-deco" viewBox="0 0 600 220" aria-hidden="true" focusable="false">'
    '<path class="spark s1" d="M60 70l5 15 15 5-15 5-5 15-5-15-15-5 15-5z"/>'
    '<path class="spark s2" d="M548 52l4 11 11 4-11 4-4 11-4-11-11-4 11-4z"/>'
    '<path class="spark s3" d="M520 168l3 8 8 3-8 3-3 8-3-8-8-3 8-3z"/>'
    '<path class="spark s4" d="M92 176l3 7 7 3-7 3-3 7-3-7-7-3 7-3z"/>'
    '<g class="bloom b1" transform="translate(30 132)"><circle r="6" cx="0" cy="-8"/><circle r="6" cx="7.6" cy="-2.5"/><circle r="6" cx="4.7" cy="6.5"/>'
    '<circle r="6" cx="-4.7" cy="6.5"/><circle r="6" cx="-7.6" cy="-2.5"/><circle class="core" r="3"/></g>'
    '<g class="bloom b2" transform="translate(575 120) scale(.75)"><circle r="6" cx="0" cy="-8"/><circle r="6" cx="7.6" cy="-2.5"/><circle r="6" cx="4.7" cy="6.5"/>'
    '<circle r="6" cx="-4.7" cy="6.5"/><circle r="6" cx="-7.6" cy="-2.5"/><circle class="core" r="3"/></g>'
    '</svg>')


def home(cat):
    chips = "".join(f'<a class="chip" href="/explorar?marca={e(slug)}">{e(name)} <span class="n">{n}</span></a>' for slug, name, n in cat.top_brands(10))
    shops = set(cat.stores) | set(cat.derm_stores) | {d for d in cat.intl_stores if d in INTL_STORES}  # chilenas, farmacias y del extranjero
    tags = '<a class="hero-tag t-rose" href="/explorar">K-beauty</a><a class="hero-tag t-lav" href="/explorar">J-beauty</a>' + (
        '<a class="hero-tag t-sage" href="/dermocosmetica">Dermocosmética</a>' if cat.section_counts[DERM] else "")
    body = f"""<div class="container"><section class="hero">{HERO_DECO}
<p class="hero-tags">{tags}</p>
<h1 class="hero-title">Tu skincare favorito, <em>al mejor precio</em></h1>
<p class="hero-sub">Comparamos {fmt(len(cat.products))} productos de belleza coreana y japonesa, maquillaje y marcas de farmacia en {len(shops)} tiendas
de Chile y del extranjero, con el historial de cada precio.</p>
<form class="search" role="search" action="/explorar">{icon("search")}<input type="search" name="q" placeholder="Busca un producto o una marca…" aria-label="Buscar" autocomplete="off"><kbd>/</kbd></form>
<div class="chips">{chips}</div></section>
{event_callout(cat)}{deals_banner(cat)}
<section class="section"><div class="section-head"><div><h2>Mayor diferencia entre tiendas</h2><p class="muted">El mismo producto, con precios distintos según dónde lo compres.</p></div>
<a class="link" href="/explorar?multi=1&orden=ahorro" aria-label="Ver más productos con diferencias de precio entre tiendas">Ver más</a></div>
<div class="grid">{"".join(card(p) for p in cat.top_spread())}</div></section>"""
    drops = cat.drops()
    if drops:
        body += f'<section class="section"><div class="section-head"><h2>Bajaron de precio</h2></div><div class="grid">{"".join(card(p) for p in drops)}</div></section>'
    asian = cat.section_counts["asiatica"]  # len(cat.products) cuenta también la dermocosmética
    body += f'<p class="muted" style="margin-top:var(--s-8);text-align:center;font-size:var(--fs-sm)">{fmt(asian)} productos · {len(cat.stores)} tiendas</p>'
    if cat.section_counts[DERM]:  # acceso discreto: el inicio sigue siendo asiático; sin productos no se ofrece una página vacía
        body += '<p class="home-more">¿Buscas dermocosmética de farmacia? <a class="link" href="/dermocosmetica">Ver dermocosmética</a></p>'
    body += "</div>"
    desc = (f"Compara precios de {fmt(len(cat.products))} productos de skincare coreano y japonés, maquillaje y dermocosmética "
            f"en {len(shops)} tiendas de Chile y del extranjero, y encuentra dónde está más barato.")
    site = {"@context": "https://schema.org", "@type": "WebSite", "name": "Yumori", "url": absolute("/"), "inLanguage": "es-CL", "description": desc}
    return page("Yumori · Compara precios de skincare y belleza en Chile", body, show_search=False, description=desc, canonical="/", jsonld=[site])


def num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def packs_callout(count, text, href):
    """Aviso destacado de que también hay packs (Explorar y los eventos): recuadro lavanda con el número en grande y un botón."""
    return (f'<a class="packs-callout" href="{e(href)}"><span><b>{e(count)}</b> {e(text)}</span>'
            f'<span class="btn btn-primary btn-sm" aria-hidden="true">Ver packs</span></a>')


def explore(cat, qs, packs=False, section="asiatica", event=None):
    """Explorar (/explorar), Packs (/packs) y, con section=DERM, Dermocosmética (/dermocosmetica y /dermocosmetica/packs): el mismo explorador,
    y todo (lista, conteos de los filtros, marcas y tiendas) con la misma sección, para que los números no contradigan la lista.
    Con `event` es la página de un evento de ofertas (/cyber, /black-friday... y su /packs): las dos secciones juntas, solo con las rebajas
    que empezaron durante el evento (catalog.in_event)."""
    cyber = bool(event)  # nombre interno de "página de evento"
    ev = event
    if cyber:
        section = ""  # un evento junta belleza asiática y dermocosmética
    derm = section == DERM
    base = (f"/{ev['slug']}/packs" if packs else f"/{ev['slug']}") if cyber else ("/dermocosmetica/packs" if packs else "/dermocosmetica") if derm else "/packs" if packs else "/explorar"
    if derm and not cat.section_counts[DERM]:
        return derm_empty()
    brands_of = {**cat.brands, **cat.derm_brands} if cyber else cat.derm_brands if derm else cat.brands
    stores_of = list(dict.fromkeys([*cat.stores, *cat.derm_stores])) if cyber else cat.derm_stores if derm else cat.stores
    g = lambda k: qs.get(k, [""])[0].strip()
    q, brand, stores, sort = g("q"), g("marca"), qs.get("tienda", []), g("orden") or ("descuento" if cyber else "")
    grp = g("cat") if g("cat") in GROUPS and not packs else ""
    kinds, skins, acts = qs.get("tipo", []), qs.get("piel", []), qs.get("ing", [])
    pmin, pmax, multi = num(g("min")), num(g("max")), g("multi") == "1"
    deals = g("oferta") == "1"
    stock = g("sinstock") != "1"  # por defecto se ocultan los productos sin stock en todas las tiendas
    pg = max(1, num(g("pagina")) or 1)
    items, total = cat.search(q, brand, stores, pmin, pmax, stock, multi, sort, pg, packs=packs, group=grp, kinds=kinds, skins=skins, actives=acts, deals=deals, section=section, event=ev)
    pages = max(1, -(-total // PAGE_SIZE))

    # números de cada filtro: cuántos quedan al marcarlo con los demás filtros aplicados (antes ignoraban marca, búsqueda, tienda...)
    n = cat.counts(q, brand=brand, stores=stores, pmin=pmin, pmax=pmax, stock=stock, multi=multi, packs=packs,
                   group=grp, kinds=kinds, skins=skins, actives=acts, deals=deals, section=section, event=ev)
    chip_n = cat.counts(q, brand=brand, stock=stock, section=section, event=ev)["cat"]  # los chips de categoría llevan a búsqueda + marca + stock (cat_link reinicia el resto)

    def top(counter, selected, k=None):
        """Las opciones más frecuentes, más las ya marcadas aunque ahora den 0 (si desaparecieran, no se podrían desmarcar)."""
        items = counter.most_common(k)
        return items + [(v, counter.get(v, 0)) for v in selected if v not in dict(items)]

    def url(**over):
        p = {"q": q, "marca": brand, "cat": grp, "min": pmin, "max": pmax, "sinstock": "" if stock else "1", "multi": "1" if multi else "", "oferta": "1" if deals else "", "orden": sort, "pagina": ""}
        p.update(over)
        pairs = [(k, v) for k, v in p.items() if v not in ("", None)]
        pairs += [("tienda", x) for x in stores] + [("tipo", x) for x in kinds] + [("piel", x) for x in skins] + [("ing", x) for x in acts]
        return base + ("?" + urlencode(pairs) if pairs else "")

    def cat_link(slug):  # cambiar de categoría reinicia los filtros de tipo, piel e ingrediente
        pairs = [(k, v) for k, v in (("q", q), ("marca", brand), ("cat", slug), ("sinstock", "" if stock else "1")) if v]
        return base + ("?" + urlencode(pairs) if pairs else "")

    label = (f"{ev['name']}: packs" if packs else ev["name"]) if cyber else ("Packs de dermocosmética" if packs else "Dermocosmética") if derm else "Packs" if packs else "Explorar"
    if cyber:
        title = f"{label}: «{q}»" if q else f"{label}: {brands_of[brand][0]}" if brand in brands_of else f"{label}: {GROUPS[grp]}" if grp else label
    elif q:
        title = f"{label}: «{q}»" if packs or derm else f"Resultados para «{q}»"
    elif brand in brands_of:
        title = brands_of[brand][0] + (" · packs" if packs else "")
    elif grp:
        title = f"{label}: {GROUPS[grp]}" if derm else GROUPS[grp]
    elif deals and not packs:
        title = f"Ofertas en {store_name(stores[0])}" if len(stores) == 1 else "Productos con descuento"
    else:
        title = label if derm else "Packs y sets" if packs else "Explorar"
    chip = f'<a class="chip" href="{url(marca="")}" aria-label="Quitar filtro de marca">{e(brands_of[brand][0])} {icon("close")}</a>' if brand in brands_of else ""
    chip += f'<a class="chip" href="{e(url(oferta=""))}" aria-label="Quitar filtro de descuento">Con descuento {icon("close")}</a>' if deals else ""
    cats = "" if packs else ('<nav class="chips cats" aria-label="Categorías">' + "".join(
        f'<a class="chip"{" aria-current=page" if slug == grp else ""} href="{cat_link(slug)}">{e(name)}'
        f'{f" <span class=n>{fmt(chip_n.get(slug, 0))}</span>" if slug else ""}</a>'
        for slug, name in [("", "Todo")] + list(GROUPS.items())) + "</nav>")

    def checks(name, counts, selected, fix=str):
        return "".join(f'<label class="check"><input type="checkbox" name="{name}" value="{e(v)}"{" checked" if v in selected else ""}>{e(fix(v))}<span class="n">{fmt(n)}</span></label>'
                       for v, n in counts)

    store_checks = checks("tienda", sorted(((d, n["tienda"].get(d, 0)) for d in stores_of), key=lambda x: -x[1]), stores, store_name)
    extra = "" if packs else (
        f'<details class="fgroup" open><summary>Tipo de producto</summary>{checks("tipo", top(n["tipo"], kinds, 16), kinds, lambda v: v[:1].upper() + v[1:])}</details>'
        f'<details class="fgroup"{" open" if skins else ""}><summary>Tipo de piel</summary>{checks("piel", top(n["piel"], skins), skins)}</details>'
        f'<details class="fgroup"{" open" if acts else ""}><summary>Ingrediente destacado</summary>{checks("ing", top(n["ing"], acts, 12), acts, lambda v: v[:1].upper() + v[1:])}</details>')
    opts = "".join(f'<option value="{v}"{" selected" if v == sort else ""}>{t}</option>' for v, t in SORTS)
    pager = ""
    if pages > 1:
        prev = f'<a class="btn btn-soft btn-sm" href="{url(pagina=pg - 1)}">Anterior</a>' if pg > 1 else ""
        nxt = f'<a class="btn btn-soft btn-sm" href="{url(pagina=pg + 1)}">Siguiente</a>' if pg < pages else ""
        pager = f'<nav class="pagination" aria-label="Paginación">{prev}<span>Página {pg} de {pages}</span>{nxt}</nav>'
    # una búsqueda mira solo esta sección: si la otra también tiene resultados se avisa, para que "eucerin" no parezca no existir
    other, n_other, cross = "asiatica" if derm else DERM, 0, ""
    if q and not packs and not cyber:
        n_other = cat.search(q, stock=stock, section=other)[1]
        o = ("/explorar", "belleza asiática", "Explorar") if derm else ("/dermocosmetica", "dermocosmética", "Dermocosmética")
        link_o = f'{o[0]}?{urlencode([(k, v) for k, v in (("q", q), ("sinstock", "" if stock else "1")) if v])}'
        cross = f'{fmt(n_other)} producto{"s" if n_other != 1 else ""} de {o[1]} que {"coincide" if n_other == 1 else "coinciden"}'
    if items:
        grid = f'<div class="grid">{"".join(card(p) for p in items)}</div>'
    elif cyber and not (qs.keys() - {"orden"}):  # sin filtros: no es que "no haya con esos filtros", es que aún no hay rebajas del evento
        grid = (f'<div class="empty"><p>Todavía no detectamos rebajas de {e(ev["name"])}.</p>'
                '<p class="small">Aparecen aquí a medida que revisamos los precios de cada tienda.</p>'
                '<p><a class="link" href="/explorar?oferta=1&amp;orden=descuento">Ver las ofertas detectadas</a></p></div>')
    else:  # sin resultados aquí pero con resultados en la otra sección, el camino a ellos va destacado en vez de una línea chica
        grid = (f'<div class="empty"><p>No encontramos {"packs" if packs else "productos"} con esos filtros.</p>'
                + (f'<p>Hay {cross}.</p><p><a class="btn btn-primary btn-sm" href="{link_o}">Ver en {o[2]}</a></p>' if n_other else "")
                + f'<p><a class="link" href="{base}">Ver {"todos los packs" if packs else "todo el catálogo"}</a></p></div>')
    if cyber:
        n_packs = 0 if packs else cat.search(q, brand, stock=stock, packs=True, section="", event=ev)[1]
        state = ("aún no empieza" if today() < opens(ev) else "empieza pronto, y algunas tiendas ya adelantaron sus rebajas" if today() < ev["start"]
                 else "terminó" if today() > ev["end"] else "está en curso")
        since = f'desde el {fecha(ev["early"])}' if ev.get("early") else "durante esas fechas"  # la previa: varias tiendas adelantan sus rebajas
        intro = (f'<p class="muted small">{e(ev["name"])} {event_dates(ev)}: {state}. Aquí están los productos que bajaron al menos {DEAL_PCT}% '
                 f'{since}, frente al precio más alto que Yumori vio en esa tienda en los últimos {DEAL_DAYS} días. Las rebajas que ya '
                 'venían de antes no cuentan. No es publicidad ni una lista entregada por las tiendas.</p>')
        if n_packs:
            intro += packs_callout(f"{fmt(n_packs)} pack{'s' if n_packs != 1 else ''} rebajado{'s' if n_packs != 1 else ''}", f"También en {ev['name']}", f"{base}/packs")
        elif packs:
            intro += f'<p class="muted small"><a class="link" href="/{e(ev["slug"])}">Volver a los productos de {e(ev["name"])}</a></p>'
    elif packs:
        intro = '<p class="muted small">Sets, kits, duos y packs de varias unidades. Cada pack se compara solo con el mismo pack en otras tiendas, no con los productos sueltos.</p>'
    elif q or brand:
        n_packs = cat.search(q, brand, stock=stock, packs=True, section=section)[1]
        link_q = urlencode([(k, v) for k, v in (("q", q), ("marca", brand)) if v])
        packs_base = "/dermocosmetica/packs" if derm else "/packs"
        intro = packs_callout(f"{fmt(n_packs)} pack{'s' if n_packs != 1 else ''}", "también coinciden con tu búsqueda", f"{packs_base}?{link_q}") if n_packs else ""
    else:
        intro = ""
    if items and n_other:
        intro += f'<p class="muted small">También hay {cross} · <a class="link" href="{link_o}">Ver en {o[2]}</a></p>'
    if derm and not q:
        intro += ('<p class="muted small">Marcas que se venden sobre todo en farmacias, con los precios de las tiendas chilenas que las tienen. '
                  'Un precio que exige una tarjeta de la tienda no cuenta como mejor precio: se muestra aparte en cada producto.</p>')
    if deals:
        intro += (f'<p class="muted small">Baja de al menos {DEAL_PCT}% frente al precio más alto que Yumori vio en esa tienda en los últimos {DEAL_DAYS} días. '
                  'No es publicidad ni un descuento informado por la tienda.</p>')
    rest = title[len(ev["name"]):] if cyber else ""  # ": packs", ": «q»"... va al lado del logo, en letra normal
    h1 = (f'<h1 class="ev-title">{event_logo(ev, "ev-xl")}{f"<span class=ev-rest>{e(rest)}</span>" if rest else ""}</h1>' if cyber else f"<h1>{e(title)}</h1>")
    body = f"""<div class="container"><div class="page-head">{h1}<p class="muted">{fmt(total)} {"packs" if packs else "productos"}</p>{intro}{cats}</div>
<div class="explore"><div class="overlay"></div>
<form class="filters" id="ff" action="{base}" method="get">
<div class="filters-head"><h2>Filtros</h2><button type="button" class="btn btn-ghost btn-icon" data-close-filters aria-label="Cerrar filtros">{icon("close")}</button></div>
<input type="hidden" name="q" value="{e(q)}"><input type="hidden" name="marca" value="{e(brand)}"><input type="hidden" name="cat" value="{e(grp)}">
{extra}<details class="fgroup"{" open" if stores else ""}><summary>Tiendas</summary>{store_checks}</details>
<div><h3>Precio (CLP)</h3><div class="range"><input class="field" type="number" name="min" min="0" step="1000" placeholder="Mín." value="{pmin if pmin is not None else ''}" aria-label="Precio mínimo"><input class="field" type="number" name="max" min="0" step="1000" placeholder="Máx." value="{pmax if pmax is not None else ''}" aria-label="Precio máximo"></div></div>
<div><h3>Disponibilidad</h3><label class="check"><input type="checkbox" name="sinstock" value="1"{"" if stock else " checked"}>Incluir productos sin stock</label>
<label class="check"><input type="checkbox" name="multi" value="1"{" checked" if multi else ""}>En 2 o más tiendas</label>
{"" if cyber else f'<label class="check"><input type="checkbox" name="oferta" value="1"{" checked" if deals else ""}>Solo con descuento</label>'}</div>
<div style="display:flex;gap:var(--s-2)"><button class="btn btn-primary btn-sm" type="submit">Aplicar</button><a class="btn btn-ghost btn-sm" href="{e(base + ('?' + urlencode({'q': q}) if q else ''))}">Limpiar</a></div>
</form>
<div class="results"><div class="toolbar"><div class="active-filters"><button type="button" class="btn btn-soft btn-sm filters-toggle" data-open-filters aria-controls="ff" aria-expanded="false">{icon("filter")}Filtros</button>{chip}</div>
<label class="sr-only" for="sort">Ordenar por</label><select class="select" id="sort" name="orden" form="ff" style="width:auto">{opts}</select></div>
{grid}{pager}</div></div></div>"""
    # Indexables: el listado general, por marca y por categoría (con su página). Búsquedas, filtros y orden son combinaciones casi
    # infinitas del mismo contenido: "noindex, follow" para que no compitan entre sí, pero sus enlaces a productos sí se siguen.
    used = {k for k, v in qs.items() if any(x.strip() for x in v)}
    indexable = used <= {"marca", "cat", "pagina"} and (brand in brands_of or not brand) and total > 0
    canon = [(k, v) for k, v in (("cat", grp), ("marca", brand if brand in brands_of else ""), ("pagina", str(pg) if pg > 1 else "")) if v]
    what = "packs" if packs else "productos"
    if derm:
        top3 = [name for _, name, _ in cat.top_brands(3, DERM)]
        where = "farmacias" if set(cat.derm_stores) <= PHARMACY_STORES else "farmacias y tiendas"
    if brand in brands_of:
        desc = f"Compara precios de {fmt(total)} {what} de {brands_of[brand][0]} en tiendas de Chile y encuentra dónde está más barato."
    elif grp:
        desc = (f"{GROUPS[grp]}: compara precios de {fmt(total)} productos de dermocosmética en {where} de Chile." if derm else
                f"{GROUPS[grp]}: compara precios de {fmt(total)} productos de belleza coreana, japonesa y china en tiendas de Chile.")
    elif packs:
        desc = (f"Sets, kits y packs de dermocosmética: compara {fmt(total)} packs en {where} de Chile." if derm else
                f"Sets, kits, duos y packs de belleza asiática: compara {fmt(total)} packs entre tiendas de Chile.")
    elif derm:
        desc = f"Dermocosmética: {', '.join(top3)} y más, en {where} de Chile. Compara precios de {fmt(total)} productos."
    else:
        desc = f"Explora {fmt(total)} productos de belleza asiática y compara sus precios en tiendas de Chile."
    seo_title = f"{title}: precios en Chile · Yumori" if (brand in brands_of or grp) and not q else f"{title} · Yumori"
    if derm and not (brand in brands_of or grp or q or packs):
        seo_title = f"Dermocosmética en {where} de Chile: precios · Yumori"
    if cyber:
        desc = f"{ev['name']} {event_dates(ev)}: {fmt(total)} {what} de belleza que bajaron de precio en tiendas de Chile, medido contra su precio habitual."
        seo_title = f"{title} {ev['start'][:4]}: rebajas reales en belleza · Yumori" if not (q or brand or grp) else f"{title} · Yumori"
    return page(seo_title, body, q=q, current=f"/{ev['slug']}" if cyber else "/dermocosmetica" if derm else "/packs" if packs else "", description=desc,
                canonical=base + ("?" + urlencode(canon) if canon else ""), robots="" if indexable else "noindex, follow",
                search_action="/dermocosmetica" if derm else "/explorar")


def derm_empty():
    """/dermocosmetica mientras ninguna farmacia tenga productos (aún no se lee): un aviso honesto en vez de un explorador sin nada."""
    body = """<div class="container"><div class="page-head"><h1>Dermocosmética</h1></div>
<div class="empty"><p>Estamos sumando farmacias a Yumori.</p>
<p class="small">Aquí vas a poder comparar marcas de farmacia como Eucerin, La Roche-Posay o CeraVe. Todavía no tenemos precios de dermocosmética para mostrar.</p>
<p class="small"><a class="link" href="/explorar">Explorar belleza asiática</a></p></div></div>"""
    return page("Dermocosmética · Yumori", body, current="/dermocosmetica", robots="noindex, follow",
                description="Dermocosmética de farmacias de Chile: estamos sumando farmacias para comparar sus precios.")


def content_card(name, size, single):
    """Una tarjeta de "Este pack incluye": con foto y enlace si el producto suelto está en el catálogo, o una tarjeta sin foto si no."""
    if single:
        note = f"En el pack: {size}" + (f" · suelto: {single.size}" if single.size and not same_size(size, single.size) else " (igual al suelto)")
        return card(single, note=note)
    return f"""<article class="card"><div class="card-img done"><span class="no-img">Sin imagen</span></div>
<div class="card-body"><h3 class="card-name">{e(name)}</h3><p class="card-meta">{e(size)}</p><p class="card-note">No lo tenemos suelto en el catálogo</p></div></article>"""


def same_size(a, b):
    return a.replace(" ", "") == b.replace(" ", "")


def pack_note(pack, single, n=1):
    """Qué trae el pack de este producto y en qué tamaño frente al suelto: así no se comparan precios de tamaños distintos."""
    inside = pack.pack_sizes.get(single.id, "")
    if n > 1:
        return f"{n} unidades en este pack"
    if inside and single.size and not same_size(inside, single.size):
        return f"En el pack: {inside} · suelto: {single.size}"
    if inside:
        return f"En el pack: {inside} (igual al suelto)" if single.size else f"En el pack: {inside}"
    if pack.small_format and not single.mini:
        return "En el pack viene en formato mini (tamaño no informado)"
    return ""


def product(cat, pid):
    p = cat.by_id.get(pid)
    if not p:
        return None
    db = sqlite3.connect(DB)
    hist = cat.history(db, p)
    db.close()
    stock = p.in_stock
    best = (stock or p.offers)[0] if p.offers else None  # None: nadie en Chile lo vende (ver p.best_intl)
    tied = [o for o in stock if o.price == stock[0].price] if stock else []  # todas las tiendas con el precio más bajo, no solo la primera
    tie = len(stock) > 1 and len(tied) > 1
    rows = []
    for o in p.offers:
        sub = []
        if len(stock) > 1 and o in tied:
            sub.append('<span class="tag">Mejor precio</span>')
        if o.stale or o.gone or o.suspect:
            sub += offline(o)
        elif not o.available:
            sub.append("Sin stock")
        if o.rating and o.reviews:
            sub.append(stars(o.rating, o.reviews))
        if shipping_text(o.store):
            sub.append(e(shipping_text(o.store)))
        was = f"<s>{clp(o.compare_at)}</s>" if o.compare_at and o.compare_at > o.price else ""  # un "antes" igual o menor no es descuento
        cls = " best-offer" if len(stock) > 1 and o in tied else "" if o.available else " out"
        rows.append(f"""<div class="offer{cls}"><div><div class="offer-store">{e(store_name(o.store))}</div><div class="offer-sub">{" ".join(f"<span>{s}</span>" if not s.startswith("<") else s for s in sub)}</div></div>
<div class="offer-price">{clp(o.price)}{was}</div>
<a class="btn btn-soft btn-sm" href="{e(o.url)}" target="_blank" rel="noopener nofollow sponsored" aria-label="Ver {e(p.name)} en {e(store_name(o.store))} (se abre en otra pestaña)">Ver en tienda</a></div>""")
    ship_note = (f'<p class="muted small">Los precios no incluyen despacho. Las condiciones de envío de cada tienda las revisamos en su sitio el '
                 f'{fecha(SHIP_REVIEWED)} y pueden cambiar: confírmalas al comprar.</p>') if any(o.store in SHIPPING for o in p.offers) else ""
    history = ""
    if p.domestic:  # sin oferta chilena no hay historial de precio en CLP que mostrar (ver ponytail más abajo)
        # la tabla price guarda una fila también cuando solo cambia el stock o el precio "antes": para el historial de PRECIO se
        # quitan los repetidos seguidos (si no, se vería "$20.000 → $20.000 → $18.000")
        runs = {s: [x[1] for i, x in enumerate(h) if i == 0 or x[1] != h[i - 1][1]] for s, h in hist.items()}
        changes = [f"<li>{e(store_name(s))}: {' → '.join(clp(x) for x in runs[s])} (desde el {fecha(h[0][0])})</li>"
                   for s, h in hist.items() if len(runs[s]) > 1]
        since = min((h[0][0] for h in hist.values() if h), default="")
        history = (f"<strong>Cambios de precio registrados</strong><ul>{''.join(changes)}</ul>" if changes else
                   f"Seguimos el precio de este producto desde el {fecha(since)}. Todavía no hay cambios que mostrar.")
    # ponytail: el historial de precio en dólares de las ofertas internacionales no se muestra todavía (existe en la tabla `price`
    # de cada listing, pero mezclarlo con el CLP de arriba requeriría marcar la moneda de cada punto). Agregar si se pide.
    intl = ""
    if p.intl:
        def intl_row(o):
            sub = ['<span class="tag tag-est">Estimado</span>' if cat.usd_clp else "", f"<span>{usd(o.cents)} + IVA 19%, sin envío</span>"]
            if o.stale or o.gone or o.suspect:
                sub += offline(o)
            elif not o.available:
                sub.append("<span>Sin stock</span>")
            price_html = f"≈ {clp(clp_estimate(o.cents, cat.usd_clp))}" if cat.usd_clp else usd(o.cents)  # sin dólar del día: se muestra en USD, sin convertir
            was = f"<s>{usd(o.compare_cents)}</s>" if o.compare_cents else ""
            return f"""<div class="offer{'' if o.available else ' out'}"><div><div class="offer-store">{e(store_name(o.store))}</div>
<div class="offer-sub">{" ".join(s for s in sub if s)}</div></div>
<div class="offer-price">{price_html}{was}</div>
<a class="btn btn-soft btn-sm" href="{e(o.url)}" target="_blank" rel="noopener nofollow sponsored" aria-label="Ver {e(p.name)} en {e(store_name(o.store))} (se abre en otra pestaña)">Ver en tienda</a></div>"""
        caption = ("Tiendas fuera de Chile que envían aquí. No entran en el mejor precio de arriba." if p.domestic else
                   "Por ahora ninguna tienda chilena lo vende: este es el precio de las tiendas del extranjero que envían a Chile.")
        fx_note = (f'<p class="muted small">Precio en dólares convertido al dólar observado del {fecha(cat.fx_date)} ({clp(round(cat.usd_clp))} por dólar) más 19% de IVA. '
                   'No incluye el envío internacional ni posibles cobros del courier: confirma el total en la tienda antes de comprar.</p>') if cat.usd_clp else ""
        intl = f"""<section class="section"><div class="section-head"><div><h2>Desde el extranjero</h2>
<p class="muted">{caption}</p></div></div><div class="offers">{"".join(intl_row(o) for o in p.intl)}</div>{fx_note}</section>"""
    derm = p.section == DERM
    home = ("/dermocosmetica/packs" if p.is_pack else "/dermocosmetica") if derm else "/packs" if p.is_pack else "/explorar"
    card_block = ""
    if p.card_offers:  # precio que exige una tarjeta de la tienda: va aparte y no es el mejor precio (p.card_offers ya viene ordenado)
        tarjeta = lambda o: o.card_name or "la tarjeta de la tienda"
        names = {tarjeta(o) for o in p.card_offers}
        note = (f"Precio exclusivo con {e(tarjeta(p.card_offers[0]))}; no lo paga cualquier cliente, por eso no cuenta como mejor precio." if len(names) == 1 else
                "Precios exclusivos con la tarjeta de cada tienda; no los paga cualquier cliente, por eso no cuentan como mejor precio.")
        crows = "".join(f"""<div class="offer"><div><div class="offer-store">{e(store_name(o.store))}</div><div class="offer-sub"><span class="tag tag-est">Con {e(tarjeta(o))}</span></div></div>
<div class="offer-price">{clp(o.card_price)}<small>Precio normal: {clp(o.price)}</small></div>
<a class="btn btn-soft btn-sm" href="{e(o.url)}" target="_blank" rel="noopener nofollow sponsored">Ver en {e(store_name(o.store))}<span class="sr-only"> con {e(tarjeta(o))} (se abre en otra pestaña)</span></a></div>""" for o in p.card_offers)
        card_block = (f'<section class="section section-sub"><div class="section-head"><div><h2>Con tarjeta de la tienda</h2><p class="muted">{note}</p></div></div>'
                      f'<div class="offers">{crows}</div></section>')
    if derm and not p.is_pack:  # tiendas que no leemos (bloqueo, términos o JavaScript): solo un enlace a su buscador, sin precio ni comparación
        q = f"{p.brand or ''} {p.name}".strip()
        links = " ".join(f'<a class="btn btn-soft btn-sm" href="{e(url + urlencode({param: q}))}" target="_blank" rel="noopener nofollow">{e(name)}'
                         f'<span class="sr-only"> (búsqueda en otra pestaña)</span></a>' for name, url, param in SEARCH_ELSEWHERE)
        card_block += (f'<section class="section section-sub"><div class="section-head"><div><h2>Búscalo también en</h2><p class="muted">Estas tiendas '
                       f'no las revisamos automáticamente, así que no mostramos su precio ni lo comparamos. El enlace abre su buscador con este producto.</p>'
                       f'</div></div><p class="search-elsewhere">{links}</p></section>')
    includes = ""
    if p.is_pack and p.content_rows:
        singles = {i: cat.by_id[i] for _, _, i in p.content_rows if i}
        smaller = p.small_format or any(s.size and not same_size(p.pack_sizes.get(i, s.size), s.size) for i, s in singles.items())
        warn = ('<div class="callout"><strong>Ojo con los tamaños.</strong> Este pack puede traer versiones más pequeñas (mini o de prueba) que los productos '
                'sueltos. Compara los ml de cada producto: el precio del producto suelto es el de su tamaño normal.</div>') if smaller else ""
        parts = "".join(content_card(name, size, singles.get(i)) for name, size, i in p.content_rows)
        includes = f"""<section class="section"><div class="section-head"><div><h2>Este pack incluye</h2>
<p class="muted">Los {len(p.content_rows)} productos y tamaños que indica la tienda. Cuando el producto suelto está en el catálogo, enlazamos a él.</p></div></div>{warn}<div class="grid">{parts}</div></section>"""
    elif p.is_pack and p.includes:
        comps = [(cat.by_id[i], n) for i, n in p.includes]
        smaller = p.small_format or any(p.pack_sizes.get(c.id) and c.size and not same_size(p.pack_sizes[c.id], c.size) for c, _ in comps)
        warn = ('<div class="callout"><strong>Ojo con los tamaños.</strong> Este pack puede traer versiones más pequeñas (mini o de prueba) que los productos '
                'sueltos de abajo. Los precios de abajo son los del producto suelto en su tamaño normal, así que no se pueden comparar directamente con el '
                'precio del pack. Cada tarjeta indica el tamaño que trae el pack cuando la tienda lo informa.</div>') if smaller else ""
        parts = "".join(card(c, note=pack_note(p, c, n)) for c, n in comps)
        includes = f"""<section class="section"><div class="section-head"><div><h2>Este pack incluye</h2>
<p class="muted">Según el título y la descripción de las tiendas. Cada producto se compara por separado.</p></div></div>{warn}<div class="grid">{parts}</div></section>"""
    included_in = ""
    if p.included_in:
        parts = "".join(card(cat.by_id[i], note=pack_note(cat.by_id[i], p, n)) for i, n in p.included_in[:8])
        included_in = f"""<section class="section"><div class="section-head"><div><h2>Se incluye en estos packs</h2>
<p class="muted">Este producto también se vende dentro de estos sets, a veces en tamaño mini. No cuentan en la comparación de precios de arriba.</p></div></div><div class="grid">{parts}</div></section>"""
    similar = cat.related(p)  # mismo tipo, con ingredientes o piel en común; sin otras versiones de este mismo producto (catalog.related)
    related = (f'<section class="section"><div class="section-head"><div><h2>También te podría interesar</h2>'
               f'<p class="muted">{"Otros packs" if p.is_pack else "Otros productos"} del mismo tipo, con ingredientes o tipo de piel en común.</p></div></div>'
               f'<div class="grid">{"".join(card(c) for c in similar)}</div></section>') if similar else ""
    info = describe(p.name, p.brand, p.size, p.text, p.is_pack, items=p.contents, small=p.small_format)
    about = ""
    ref = best or p.best_intl  # para el enlace "revisa la página del producto en...": la mejor oferta que haya, chilena o no
    if info and info["text"] and ref:  # sin texto (solo se detectó el tipo de piel, nada más) no hay nada que resumir: no mostrar un párrafo vacío
        chips = "".join(f'<span class="chip chip-static">{e(x)}</span>' for x in info["skin"])
        skin = f'<p class="for"><span class="muted">Especial para:</span> {chips}</p>' if chips else ""
        about = (f'<div class="about"><p>{e(info["text"])}</p>{skin}<p class="muted small">Este es un resumen elaborado por Yumori a partir de lo que informan '
                 f'las tiendas{" y el sitio oficial de la marca" if p.brand_site else ""} y puede no incluir todos los compuestos. Para ver la lista completa de ingredientes, revisa la '
                 f'<a class="link" href="{e(ref.url)}" target="_blank" rel="noopener nofollow sponsored">página del producto en {e(store_name(ref.store))}</a> o el envase.</p></div>')
    thumbs = "".join(
        f'<button type="button" class="thumb" data-full="{e(u)}" data-alt="{e(p.brand)} {e(p.name)}, imagen {n} de {len(p.images)}" aria-label="Ver imagen {n} de {len(p.images)}"{" aria-current=true" if n == 1 else ""}>'
        f'<img loading="lazy" referrerpolicy="no-referrer" src="{e(u)}" alt=""></button>' for n, u in enumerate(p.images, 1)) if len(p.images) > 1 else ""
    gallery = (f'<div class="gallery"><div class="product-img skeleton{"" if p.image else " done"}">'
               f'{img(p.image, f"{p.brand} {p.name}" + (f", imagen 1 de {len(p.images)}" if len(p.images) > 1 else ""), p.alts).replace("<img ", "<img id=main-img ", 1)}</div>{f"<div class=thumbs>{thumbs}</div>" if thumbs else ""}</div>')
    subtitle = " · ".join(x for x in (("Pack en formato mini" if p.small_format else "Pack") if p.is_pack else "", p.variant, p.size, "Miniatura" if p.mini else "") if x)
    if p.domestic:
        compared = (f"{len(stock)} tiendas con stock" if len(stock) > 1 else "1 tienda con stock" if stock else
                    unconfirmed(best) or "Sin stock por ahora")
        save = f' · hasta {p.spread:.0%} menos que la más cara' if p.spread >= 0.02 else ""
        big_gap = ('<p class="warn small">La diferencia entre tiendas es grande: confirma que sea el mismo tamaño y versión antes de comprar.</p>'
                   if p.spread >= 0.4 else "")
        price_para = (f'<p class="best"><span class="big"><strong>{clp(best.price)}</strong></span>'
                      f'{f"Mismo precio en {len(tied)} tiendas" if tie else f"{'Mejor precio en ' if len(stock) > 1 else 'En '}<strong>{e(store_name(best.store))}</strong>"}</p>')
        action_links = ("".join(f'<a class="btn btn-primary btn-lg" href="{e(o.url)}" target="_blank" rel="noopener nofollow sponsored">Ver en {e(store_name(o.store))}<span class="sr-only"> (se abre en otra pestaña)</span></a>'
                                for o in sorted(tied, key=lambda o: store_name(o.store))) if tie else
                        f'<a class="btn btn-primary btn-lg" href="{e(best.url)}" target="_blank" rel="noopener nofollow sponsored">Ver en {e(store_name(best.store))}<span class="sr-only"> (se abre en otra pestaña)</span></a>')
    else:  # nadie en Chile lo vende todavía: el precio es una estimación desde la tienda internacional más barata
        bi = p.best_intl
        compared, save, big_gap = unconfirmed(bi) if bi else "", "", ""
        price_para = (f'<p class="best"><span class="big"><strong>≈ {clp(p.display_price)}</strong></span>Estimado, en <strong>{e(store_name(bi.store))}</strong></p>'
                      if p.display_price is not None and bi else '<p class="best"><span class="big"><strong>Ver precio en la tienda</strong></span></p>')
        action_links = (f'<a class="btn btn-primary btn-lg" href="{e(bi.url)}" target="_blank" rel="noopener nofollow sponsored">Ver en {e(store_name(bi.store))}<span class="sr-only"> (se abre en otra pestaña)</span></a>'
                        if bi else "")
    body = f"""<div class="container">
<nav class="crumbs" aria-label="Ruta"><a href="/">Inicio</a>{' / <a href="/dermocosmetica">Dermocosmética</a>' if derm else ""}{f' / <a href="{"/dermocosmetica" if derm else "/explorar"}?cat={p.group}">{GROUPS[p.group]}</a>' if p.group else ""} / <a href="{home}?marca={e(p.brand_slug)}">{e(p.brand)}</a></nav>
<div class="product">{gallery}
<div><p class="eyebrow"><a href="{home}?marca={e(p.brand_slug)}">{e(p.brand)}</a></p><h1>{e(p.name)}</h1>
{f'<p class="muted" style="margin-top:var(--s-2)">{e(subtitle)}</p>' if subtitle else ''}
{about}
{price_para}
{f'<p class="muted" style="font-size:var(--fs-sm);margin-top:var(--s-1)">{compared}{save}</p>' if compared else ''}{big_gap}
<div class="actions">{action_links}
<button class="btn btn-soft btn-lg fav-btn" data-fav="{p.id}" aria-pressed="false">{icon("heart")}<span class="label">Guardar</span></button></div></div></div>
{f'<section class="section"><div class="section-head"><div><h2>Precios por tienda</h2>{ship_note}</div></div><div class="offers">{"".join(rows)}</div></section>' if p.domestic else ''}{card_block}{intl}{includes}
{f'<section class="section"><div class="section-head"><h2>Historial de precios</h2></div><div class="history">{history}</div></section>' if p.domestic else ''}{included_in}{related}</div>"""
    return page(f"{full_name(p)}: precio en Chile · Yumori", body, **product_seo(p, stock, info, home))


def full_name(p):
    """Marca, nombre, variante (solo si otro producto se llama igual) y tamaño: el nombre único de un producto para títulos y buscadores."""
    return " ".join(x for x in (p.brand, p.name, p.variant, p.size) if x)


def product_seo(p, stock, info, home):
    """Meta descripción, imagen y datos estructurados de un producto. Solo datos que el sitio ya muestra: precios de tiendas chilenas
    con stock confirmado (nunca la estimación desde el extranjero) y sin la nota de las tiendas (Google no admite reseñas tomadas de
    otros sitios)."""
    n, s = len(p.offers), len(stock)
    if stock:
        lead = f"{'desde ' if s > 1 else ''}{clp(min(o.price for o in stock))} en {s} tienda{'s' if s > 1 else ''} de Chile con stock"
    elif p.domestic:
        lead = f"sin stock por ahora en {n} tienda{'s' if n > 1 else ''} de Chile"
    elif p.display_price is not None:
        lead = f"≈ {clp(p.display_price)} estimado desde el extranjero, con IVA y sin envío"
    else:
        lead = "disponible en una tienda del extranjero"
    desc = f"{full_name(p)}: {lead}. Compara precios, stock e historial antes de comprar."
    data = {"@context": "https://schema.org", "@type": "Product", "name": full_name(p), "url": absolute(f"/p/{p.id}")}
    if p.brand and p.brand_slug != "sin-marca":
        data["brand"] = {"@type": "Brand", "name": p.brand}
    if p.images:
        data["image"] = p.images
    if info and info["text"]:
        data["description"] = info["text"]
    if stock:
        prices = [o.price for o in stock]
        data["offers"] = {"@type": "AggregateOffer", "priceCurrency": "CLP", "lowPrice": min(prices), "highPrice": max(prices),
                          "offerCount": len(stock), "availability": "https://schema.org/InStock"}
    derm = p.section == DERM
    crumbs = [("Inicio", "/")] + ([("Dermocosmética", "/dermocosmetica")] if derm else []) + \
             ([(GROUPS[p.group], f"{'/dermocosmetica' if derm else '/explorar'}?cat={p.group}")] if p.group else []) + \
             ([(p.brand, f"{home}?{urlencode({'marca': p.brand_slug})}")] if p.brand_slug != "sin-marca" else []) + [(p.name, f"/p/{p.id}")]
    trail = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": n, "item": absolute(u)} for i, (n, u) in enumerate(crumbs, 1)]}
    return dict(description=desc, canonical=f"/p/{p.id}", image=p.image or "", og_type="product", jsonld=[data, trail])


def brand_letters(brand_map, base, level):
    """Marcas agrupadas por letra, de la A a la Z y sin ranking: [(nombre, cantidad)] por slug -> enlaces a `base`."""
    by = {}
    for slug, (name, n) in brand_map.items():
        by.setdefault(name[:1].upper() if name[:1].isalpha() else "#", []).append((name, slug, n))
    return "".join(
        f'<section class="letter"><h{level}>{L}</h{level}><div class="chips" style="justify-content:flex-start">'
        + "".join(f'<a class="chip" href="{base}?marca={e(s)}">{e(n)} <span class="n">{c}</span></a>' for n, s, c in sorted(v, key=lambda x: x[0].lower()))
        + "</div></section>" for L, v in sorted(by.items()))


def brands(cat):
    desc = f"Las {len(cat.brands)} marcas de belleza coreana, japonesa y china que comparamos en tiendas de Chile, de la A a la Z."
    if not cat.derm_brands:
        out = brand_letters(cat.brands, "/explorar", 2)
    else:  # con dermocosmética, dos partes con los mismos títulos de siempre: cada una con sus marcas, de la A a la Z
        out = (f'<section class="section"><div class="section-head"><h2>Belleza asiática</h2></div>{brand_letters(cat.brands, "/explorar", 3)}</section>'
               f'<section class="section"><div class="section-head"><div><h2>Dermocosmética</h2><p class="muted small">Marcas que se venden sobre todo en farmacias. Se comparan aparte.</p></div></div>{brand_letters(cat.derm_brands, "/dermocosmetica", 3)}</section>')
        desc += f" Y {len(cat.derm_brands)} marcas de dermocosmética."
    return page("Marcas · Yumori", f'<div class="container"><div class="page-head"><h1>Marcas</h1><p class="muted">{len(cat.brands)} marcas{f" de belleza asiática y {len(cat.derm_brands)} de dermocosmética" if cat.derm_brands else ""}</p></div>{out}</div>', current="/marcas",
                description=desc, canonical="/marcas")


def stores(cat):
    def badge(d):
        return '<span class="tag tag-off">Sin conexión</span>' if d in cat.stale else ""

    def off(d):
        return (f'<span class="muted small">Sin conexión desde el {fecha(cat.stale[d][:10])}: mostramos el último precio que vimos, '
                f'sin contarlo como mejor precio.</span>') if d in cat.stale else ""

    def ship(d):
        return f'<span class="muted small">{e(shipping_text(d))}</span>' if shipping_text(d) else ""

    # lo mismo que muestra Explorar al entrar (productos sueltos con stock): antes se contaban también packs y agotados
    # (Sokobox decía 1.421 y al entrar se veían 942)
    live = cat.counts(stock=True)["tienda"]
    cards = "".join(f'<a class="store-card" href="/explorar?tienda={e(d)}"><span class="store-card-head"><b>{e(store_name(d))}</b>{badge(d)}</span>'
                    f'<span class="muted">{fmt(live.get(d, 0))} productos de belleza asiática con stock</span>{ship(d)}{off(d)}</a>'
                    for d in sorted(cat.stores, key=lambda d: -live.get(d, 0)))
    intl = sorted(((d, n) for d, n in cat.intl_stores.items() if d in INTL_STORES), key=lambda x: -x[1])
    intl_cards = "".join(
        f'<a class="store-card store-card-intl" href="https://{e(d)}/" target="_blank" rel="noopener nofollow sponsored"'
        f' aria-label="Ir al sitio de {e(store_name(d))} (se abre en otra pestaña)">'
        f'<span class="store-card-head"><b>{e(store_name(d))}</b>{badge(d)}<span class="tag tag-est">Internacional</span></span>'
        f'<span class="muted">{fmt(n)} productos en Yumori · {fmt(cat.intl_matched.get(d, 0))} también en Chile</span>{off(d)}</a>'
        for d, n in intl)
    intl_section = f"""<section class="section"><div class="section-head"><div><h2>Tiendas internacionales</h2>
<p class="muted small">Envían a Chile. Sus precios se muestran en pesos, estimados con el dólar del día y 19% de IVA, sin envío. Cuando el mismo producto también lo vende una
tienda chilena, se compara directamente en su ficha. El enlace de cada tarjeta lleva directo al sitio de la tienda.</p></div></div>
<div class="store-list">{intl_cards}</div></section>""" if intl else ""
    derm_section = ""
    if cat.derm_stores:  # las tiendas con dermocosmética, aparte y en orden alfabético (sin ranking); cada una lleva a lo suyo en esa sección
        dlive = cat.counts(stock=True, section=DERM)["tienda"]
        dcards = "".join(f'<a class="store-card" href="/dermocosmetica?{urlencode({"tienda": d})}"><span class="store-card-head"><b>{e(store_name(d))}</b>{badge(d)}</span>'
                         f'<span class="muted">{fmt(dlive.get(d, 0))} productos de dermocosmética con stock</span>{ship(d)}{off(d)}</a>'
                         for d in sorted(cat.derm_stores, key=lambda d: store_name(d).lower()))
        derm_section = f"""<section class="section"><div class="section-head"><div><h2>Dermocosmética</h2>
<p class="muted small">Tiendas chilenas que venden marcas de farmacia, como Eucerin o La Roche-Posay. Se comparan aparte de la belleza asiática.</p></div></div>
<div class="store-list">{dcards}</div></section>"""
    body = f"""<div class="container"><div class="page-head"><h1>Tiendas</h1><p class="muted">Comparamos {len(cat.stores)} tiendas chilenas y {len(intl)} internacionales</p></div>
<p class="muted small">Las condiciones de despacho las revisamos en el sitio de cada tienda el {fecha(SHIP_REVIEWED)} y pueden cambiar. No se suman a los precios.</p>
<div class="store-list">{cards}</div>{intl_section}{derm_section}</div>"""
    return page("Tiendas · Yumori", body, current="/tiendas", canonical="/tiendas",
                description=f"Las {len(cat.stores)} tiendas de cosmética asiática, chilenas y del extranjero, cuyos precios compara Yumori.")


def favorites():
    body = """<div class="container"><div class="page-head"><h1>Favoritos</h1><p class="muted">Guardados en este navegador.</p></div>
<p>Si cambias de dirección del sitio, puedes trasladar tu lista con este archivo.</p>
<button type="button" id="fav-export">Exportar favoritos</button><p id="fav-transfer-status" role="status" aria-live="polite"></p>
<div class="grid" id="fav-grid"></div>
<div class="empty" id="fav-empty" hidden><p>Todavía no guardas ningún producto.</p><p><a class="link" href="/explorar">Explorar productos</a></p></div></div>"""
    return page("Favoritos · Yumori", body, current="/favoritos", robots="noindex, follow")  # la lista vive en el navegador de cada persona


LEGAL = {"/privacidad": ("Política de privacidad", legal.privacy), "/terminos": ("Términos y condiciones", legal.terms),
         "/cookies": ("Política de cookies", legal.cookies)}

# Cabeceras de seguridad. Las imágenes vienen de las tiendas (https); todo lo demás, del propio sitio.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


# ---------- rutas ----------

def robots_txt():
    return f"""User-agent: *
Disallow: /fragmento/
Disallow: /favoritos

Sitemap: {absolute('/sitemap.xml')}
"""


def sitemap(cat):
    """Las páginas indexables: inicio, listados, marcas, categorías, legales y cada producto (~7.000, bajo el límite de 50.000)."""
    paths = ["/", "/explorar", "/packs", "/marcas", "/tiendas", *LEGAL]
    live = live_event()
    if live and cat.search(stock=True, section="", event=live)[1]:  # solo mientras dura y tiene rebajas
        paths.append(f"/{live['slug']}")
    paths += [f"/explorar?{urlencode({'cat': g})}" for g in GROUPS]
    paths += [f"/explorar?{urlencode({'marca': b})}" for b in sorted(cat.brands) if b != "sin-marca"]
    if cat.section_counts[DERM]:  # sin productos la página es un aviso con noindex: no va al sitemap
        paths += ["/dermocosmetica"] + [f"/dermocosmetica?{urlencode({'cat': g})}" for g, n in cat.facets(True, section=DERM)["groups"].items() if n]
        paths += [f"/dermocosmetica?{urlencode({'marca': b})}" for b in sorted(cat.derm_brands) if b != "sin-marca"]
        paths += ["/dermocosmetica/packs"] * any(p.is_pack and p.section == DERM for p in cat.products)
    paths += [f"/p/{p.id}" for p in cat.products]
    day = f"<lastmod>{cat.last_update[:10]}</lastmod>" if cat.last_update else ""
    urls = "".join(f"<url><loc>{e(absolute(u))}</loc>{day if u.startswith('/p/') else ''}</url>" for u in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def route(path, qs, base=""):
    """-> (status, content-type, bytes[, cabeceras]). `base`: URL del sitio para las direcciones absolutas (canónicas, sitemap)."""
    REQ.base = SITE_URL or base
    html = lambda r: (r[0], "text/html; charset=utf-8", r[1].encode())
    if path.startswith("/static/"):
        f = (STATIC / path.removeprefix("/static/")).resolve()
        if f.is_file() and STATIC.resolve() in f.parents:
            return 200, mimetypes.guess_type(f.name)[0] or "application/octet-stream", f.read_bytes()
        return 404, "text/plain; charset=utf-8", b"No encontrado"
    cat = get_catalog()
    if path == "/api" or path.startswith("/api/"):
        return api.route(cat, path, qs, DB)
    if path == "/":
        return html(home(cat))
    if path == "/explorar":
        return html(explore(cat, qs))
    if path == "/packs":
        return html(explore(cat, qs, packs=True))
    slug, _, tail = path.strip("/").partition("/")
    if event_for(slug) and tail in ("", "packs"):  # /cyber, /black-friday... y su /packs
        return html(explore(cat, qs, packs=tail == "packs", event=event_for(slug)))
    if path == "/dermocosmetica":
        return html(explore(cat, qs, section=DERM))
    if path == "/dermocosmetica/packs":
        return html(explore(cat, qs, packs=True, section=DERM))
    if path.startswith("/p/"):
        r = product(cat, path[3:])
        if r:
            return html(r)
        new = cat.resolve(path[3:])  # id de antes de un cambio de matching (enlace o favorito guardado): redirige al actual
        if new:
            return 301, "text/plain; charset=utf-8", b"", {"Location": f"/p/{new}"}
    if path == "/marcas":
        return html(brands(cat))
    if path == "/tiendas":
        return html(stores(cat))
    if path == "/favoritos":
        return html(favorites())
    if path in LEGAL:
        return html(page(LEGAL[path][0] + " · Yumori", LEGAL[path][1](), canonical=path, description=f"{LEGAL[path][0]} de Yumori, comparador de precios de belleza asiática en Chile."))
    if path == "/robots.txt":
        return 200, "text/plain; charset=utf-8", robots_txt().encode()
    if path == "/sitemap.xml":
        return 200, "application/xml; charset=utf-8", sitemap(cat).encode()
    if path == "/fragmento/cards":
        ids = dict.fromkeys(filter(None, map(cat.resolve, qs.get("ids", [""])[0].split(",")[:100])))  # favoritos con id viejo -> el actual, sin repetir
        return 200, "text/html; charset=utf-8", "".join(card(cat.by_id[i]) for i in ids).encode()
    if path == "/fragmento/sugerencias":
        return 200, "text/html; charset=utf-8", suggestions(cat, qs.get("q", [""])[0]).encode()
    return 404, "text/html; charset=utf-8", layout("No encontrado · Yumori", robots="noindex", body='<div class="container"><div class="empty"><h1>No encontramos esa página</h1><p><a class="link" href="/">Volver al inicio</a></p></div></div>').encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        try:
            is_api = u.path == "/api" or u.path.startswith("/api/")
            if is_api and len(self.path) > 8192:
                status, ctype, body = api.error(414, "uri_too_long", "URL demasiado larga")
                extra = []
            else:
                try:
                    qs = parse_qs(u.query, keep_blank_values=is_api, max_num_fields=80 if is_api else None)
                except ValueError:
                    status, ctype, body = api.error(400, "invalid_parameters", "Demasiados parámetros")
                    extra = []
                else:
                    status, ctype, body, *extra = route(u.path, qs, base=f"http://{self.headers.get('Host') or '127.0.0.1'}")
        except Exception:
            traceback.print_exc()
            if u.path == "/api" or u.path.startswith("/api/"):
                status, ctype, body = api.error(500, "internal_error", "Error interno")
                extra = []
            else:
                status, ctype, body, extra = 500, "text/plain; charset=utf-8", b"Error interno", []
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            for k, val in {**SECURITY_HEADERS, **(extra[0] if extra else {})}.items():  # extra: cabeceras propias de la ruta (Location)
                self.send_header(k, val)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if legal.missing():
        print("AVISO: faltan datos del titular en legal.py (" + ", ".join(legal.missing()) + "). Completarlos antes de publicar el sitio.")
    host = os.environ.get("YUMORI_HOST", "127.0.0.1")  # por defecto solo este PC; el contenedor lo cambia (docs/operations/docker-ec2.md)
    print(f"Yumori en http://{host}:{port}  (Ctrl+C para salir)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
