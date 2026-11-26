"""Contrato JSON de lectura v1. Las reglas de negocio permanecen en Catalog."""
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlencode

from catalog import PAGE_SIZE, INTL_STORES, DEAL_DAYS, DEAL_SHOW, DEAL_PCT, all_events, live_event, in_event, clp_estimate, event_for, local_day, store_name
from db import BY_BRAND
from describe import GROUPS, describe
from match import words
from shipping import SHIPPING, REVIEWED
import legal

PREFIX = "/api/v1"
SORTS = {"", "precio_asc", "precio_desc", "ahorro", "nombre", "descuento"}
PARAMS = {"q", "marca", "tienda", "orden", "cat", "tipo", "piel", "ing", "min", "max", "multi",
          "oferta", "sinstock", "pagina", "packs", "seccion", "evento"}


def response(status, data):
    return status, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")


def error(status, code, message):
    return response(status, {"version": 1, "error": {"code": code, "message": message}})


def safe_url(value):
    """El consumidor puede convertir URLs en enlaces; no entregar esquemas ejecutables."""
    try:
        if not value or any(ord(char) <= 32 for char in value):
            return None
        parsed = urlsplit(value or "")
        return value if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


def validate(qs, allowed, repeat=()):
    if set(qs) - allowed or sum(len(v) for v in qs.values()) > 80:
        raise ValueError("Parámetros desconocidos o demasiados valores")
    for key, values in qs.items():
        if not values or len(values) > (20 if key in repeat else 1) or any(len(v) > 200 for v in values):
            raise ValueError("Parámetros repetidos o demasiado largos")


def integer(value, default=None, maximum=1_000_000_000, minimum=0):
    if value == "":
        return default
    if not re.fullmatch(r"[0-9]{1,10}", value) or not minimum <= int(value) <= maximum:
        raise ValueError("Número fuera del rango permitido")
    return int(value)


def filters(qs):
    validate(qs, PARAMS, {"tienda", "tipo", "piel", "ing"})
    g = lambda key: qs.get(key, [""])[0].strip()
    for key in ("multi", "oferta", "sinstock", "packs"):
        if g(key) not in {"", "0", "1"}:
            raise ValueError("Los indicadores deben ser 0 o 1")
    section = g("seccion") or "asiatica"
    if section not in {"asiatica", "dermocosmetica", "todas"} or g("orden") not in SORTS:
        raise ValueError("Sección u orden desconocido")
    if g("cat") and g("cat") not in GROUPS:
        raise ValueError("Categoría desconocida")
    event = event_for(g("evento")) if g("evento") else None
    if g("evento") and not event:
        raise ValueError("Evento desconocido")
    packs = g("packs") == "1"
    f = dict(brand=g("marca"), stores=qs.get("tienda", []), pmin=integer(g("min")), pmax=integer(g("max")),
             stock=g("sinstock") != "1", multi=g("multi") == "1", packs=packs,
             group=g("cat") if not packs else "", kinds=qs.get("tipo", []), skins=qs.get("piel", []),
             actives=qs.get("ing", []), deals=g("oferta") == "1",
             section="" if section == "todas" or event else section, event=event)
    if f["pmin"] is not None and f["pmax"] is not None and f["pmin"] > f["pmax"]:
        raise ValueError("El precio mínimo supera al máximo")
    return g("q"), f, g("orden") or ("descuento" if event else ""), integer(g("pagina"), 1, 100000, 1)


def money(amount, currency):
    # Siempre unidades menores: CLP tiene 0 decimales; USD tiene 2.
    return {"amount": amount, "currency": currency, "decimals": 0 if currency == "CLP" else 2}


def shipping(store):
    data = SHIPPING.get(store)
    return {**data, "fuente": safe_url(data.get("fuente")), "reviewed": REVIEWED} if data else None


def offer(o, cat, international=False):
    status = ("stale" if o.stale else "missing" if o.gone else "suspect" if o.suspect
              else "available" if o.available else "out_of_stock")
    labels = {"stale": "Sin conexión", "missing": "Sin actualizar" if o.store in BY_BRAND else "No aparece en la tienda",
              "suspect": "Precio por confirmar", "available": "Disponible", "out_of_stock": "Sin stock"}
    amount = o.cents if international else o.price
    data = dict(store=o.store, store_name=store_name(o.store), url=safe_url(o.url),
                price=money(amount, "USD" if international else "CLP"), available=bool(o.available),
                status=status, status_label=labels[status], stale_since=o.stale, missing_since=o.gone, suspect_reason=o.suspect)
    if international:
        data["estimate"] = money(clp_estimate(amount, cat.usd_clp), "CLP") if cat.usd_clp else None
    else:
        # Tarjetas condicionadas se muestran aparte en la ficha, nunca en best_store_ids.
        data.update(rating=o.rating, reviews=o.reviews, drop_percent=o.drop,
                    shipping=shipping(o.store),
                    reference_price=money(o.ref, "CLP") if o.ref is not None else None, price_since_day=o.since)
    return data


def summary(p):
    # Las etiquetas de presentación son las mismas del renderer que se migra.
    from server import price_bits
    prefix, _, stores_label = price_bits(p)
    stock = p.in_stock
    best = [o.store for o in stock if o.price == stock[0].price] if stock else []
    rating = p.rating
    return dict(id=p.id, path=f"/p/{p.id}", name=p.name, brand=p.brand, brand_slug=p.brand_slug, size=p.size,
                card_prefix=prefix, card_store_label=stores_label,
                card_meta=" · ".join(x for x in (("Pack mini" if p.small_format else "Pack") if p.is_pack else "", p.variant, p.size, "Miniatura" if p.mini else "", stores_label) if x),
                has_deal=p.drop >= DEAL_PCT,
                variant=p.variant, section=p.section, is_pack=p.is_pack, mini=p.mini,
                image=safe_url(p.image), image_alternatives=[u for u in map(safe_url, p.alts) if u],
                display_price=money(p.display_price, "CLP") if p.display_price is not None else None,
                display_is_estimate=p.display_is_estimate, domestic=p.domestic,
                display_price_confirmed=bool(stock) if p.domestic else bool(p.intl_in_stock),
                available=bool(stock or p.intl_in_stock), domestic_store_count=len(p.offers),
                international_store_count=len(p.intl), best_store_ids=sorted(best, key=lambda s: (words(store_name(s)), s)),
                drop_percent=p.drop, drop_reference_price=money(p.drop_ref, "CLP") if p.drop_ref is not None else None,
                rating={"value": rating.rating, "reviews": rating.reviews, "store": rating.store} if rating else None)


def metadata(cat):
    return dict(version=1, catalog_last_update=cat.last_update,
                exchange_rate={"usd_clp": cat.usd_clp, "date": cat.fx_date},
                estimate_includes_vat=True, estimate_includes_shipping=False)


def detail(p, cat):
    from server import same_size

    data = summary(p)
    # Destinos del CTA original. Solo best_store_ids identifica precios ganadores;
    # una oferta agotada/no confirmada conserva el enlace, sin recibir esa etiqueta.
    primary = (p.in_stock or p.offers)[0] if p.offers else p.best_intl
    data["primary_offer_store_ids"] = data["best_store_ids"] or ([primary.store] if primary else [])
    data.update(images=[u for u in map(safe_url, p.images) if u], kind=p.kind, category=p.group,
                category_label=GROUPS.get(p.group, ""), skin=p.skin, actives=p.actives,
                matched_by=p.matched_by,
                description=describe(p.name, p.brand, p.size, p.text, p.is_pack, items=p.contents, small=p.small_format),
                description_disclaimer="Resumen informativo. Revisa los ingredientes y las indicaciones completas en la tienda de origen.",
                domestic_offers=[offer(o, cat) for o in p.offers], international_offers=[offer(o, cat, True) for o in p.intl],
                card_offers=[dict(store=o.store, store_name=store_name(o.store), card_name=o.card_name,
                                  price=money(o.card_price, "CLP"), normal_price=money(o.price, "CLP"), url=safe_url(o.url)) for o in p.card_offers],
                contents=[dict(name=n, size=s, product_id=pid) for n, s, pid in p.content_rows],
                includes=[dict(product_id=pid, quantity=n, pack_size=p.pack_sizes.get(pid)) for pid, n in p.includes],
                included_in=[dict(product_id=pid, quantity=n) for pid, n in p.included_in], small_format=p.small_format,
                related=[summary(other) for other in cat.related(p)], shipping_reviewed=REVIEWED,
                price_spread_warning=bool(p.domestic and p.spread >= 0.4))
    for key in ("contents", "includes", "included_in"):
        for row in data[key]:
            linked = cat.by_id.get(row["product_id"])
            row["product"] = summary(linked) if linked else None
    # El mismo aviso de tamaños del renderer original; el cliente no compara formatos.
    linked_ids = [pid for _, _, pid in p.content_rows if pid] if p.content_rows else [pid for pid, _ in p.includes]
    data["pack_size_warning"] = bool(p.is_pack and (p.small_format or any(
        linked.size and p.pack_sizes.get(pid) and not same_size(p.pack_sizes[pid], linked.size)
        for pid in linked_ids if (linked := cat.by_id.get(pid)) is not None)))
    data["search_elsewhere"] = []
    if p.section == "dermocosmetica" and not p.is_pack:
        # Importación diferida: server importa api, y conserva el directorio existente.
        from server import SEARCH_ELSEWHERE
        query = f"{p.brand or ''} {p.name}".strip()
        data["search_elsewhere"] = [dict(name=name, url=safe_url(url + urlencode({param: query})))
                                   for name, url, param in SEARCH_ELSEWHERE]
    return data


class LegalBlocks(HTMLParser):
    """Texto y formato propio con una lista cerrada de nodos, nunca HTML ejecutable."""
    BLOCKS = {"h1", "h2", "p", "li", "th", "td"}
    INLINE = {"strong", "em", "code", "a"}
    OMIT = {"script", "style", "iframe", "object", "svg", "math", "template"}

    def __init__(self, html):
        super().__init__()
        self.blocks = []
        self.tag = None
        self.parts = []
        self.inline = []
        self.stack = []
        self.omitted = []
        self.feed(html)
        self.close()
        self.finish_block()

    @staticmethod
    def safe_href(value):
        if value in {"/privacidad", "/terminos", "/cookies"}:
            return value
        own_email = legal.email()
        if (own_email and re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", own_email)
                and value == "mailto:" + own_email):
            return value
        return safe_url(value)

    def finish_block(self):
        if self.tag:
            self.blocks.append({"tag": self.tag, "text": " ".join("".join(self.parts).split()),
                                "inline": self.inline})
        self.tag, self.parts, self.inline, self.stack = None, [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.OMIT:
            self.omitted.append(tag)
        if self.omitted:
            return
        if tag in self.BLOCKS:
            self.finish_block()
            self.tag = tag
        elif self.tag and tag in self.INLINE:
            node = {"tag": tag, "children": []}
            if tag == "a":
                href = self.safe_href(dict(attrs).get("href"))
                if href:
                    node["href"] = href
                else:
                    node["tag"] = "span"
            parent = self.stack[-1][1]["children"] if self.stack else self.inline
            parent.append(node)
            self.stack.append((tag, node))

    def handle_data(self, data):
        if self.tag and not self.omitted:
            self.parts.append(data)
            parent = self.stack[-1][1]["children"] if self.stack else self.inline
            parent.append({"text": re.sub(r"\s+", " ", data)})

    def handle_endtag(self, tag):
        if self.omitted:
            if tag in self.omitted:
                self.omitted = self.omitted[:self.omitted.index(tag)]
            return
        if tag == self.tag:
            self.finish_block()
        elif tag in self.INLINE:
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    self.stack = self.stack[:index]
                    break


def site(cat):
    def brands(source):
        return [dict(slug=slug, name=value[0], count=value[1])
                for slug, value in sorted(source.items(), key=lambda x: words(x[1][0]))]

    def stores(domains, section):
        counts = cat.counts(stock=True, section=section)["tienda"]
        return [dict(domain=d, name=store_name(d), count=counts.get(d, 0), stale_since=cat.stale.get(d),
                     shipping=shipping(d), url=safe_url("https://" + d + "/"))
                for d in sorted(domains, key=lambda d: words(store_name(d)))]

    intl = [dict(domain=d, name=store_name(d), count=n, matched_in_chile=cat.intl_matched.get(d, 0),
                 stale_since=cat.stale.get(d), shipping=None, url=safe_url("https://" + d + "/"))
            for d, n in sorted(cat.intl_stores.items(), key=lambda x: words(store_name(x[0]))) if d in INTL_STORES]
    asia, derm = stores(cat.stores, "asiatica"), stores(cat.derm_stores, "dermocosmetica")
    chile = {}  # una entrada por tienda chilena, con el conteo de cada sección en la que vende (para /tiendas)
    for section, rows in (("asiatica", asia), ("dermocosmetica", derm)):
        for row in rows:
            chile.setdefault(row["domain"], {k: v for k, v in row.items() if k != "count"} | {"counts": {}})["counts"][section] = row["count"]
    chile = sorted(chile.values(), key=lambda s: words(s["name"]))
    shops = set(cat.stores) | set(cat.derm_stores) | {s["domain"] for s in intl}
    documents = {slug: dict(title=title, updated=legal.UPDATED, blocks=LegalBlocks(render()).blocks)
                 for slug, title, render in [("privacidad", "Política de privacidad", legal.privacy),
                                            ("terminos", "Términos y condiciones", legal.terms),
                                            ("cookies", "Política de cookies", legal.cookies)]}
    live = live_event()
    live_total = cat.search(stock=True, section="", event=live)[1] if live else 0
    live_stores = {o.store for p in cat.products if not p.is_pack and p.event_drop(live) for o in p.offers if in_event(o, live)} if live_total else set()
    return {**metadata(cat), "categories": [dict(slug=slug, name=name, count=cat.facets(True)["groups"].get(slug, 0)) for slug, name in GROUPS.items()],
            "home": dict(product_count=len(cat.products), store_count=len(shops),
                live_event_summary=dict(product_count=live_total, store_count=len(live_stores)) if live_total else None,
                section_counts=dict(cat.section_counts), top_brands=[dict(slug=s, name=n, count=c) for s, n, c in cat.top_brands(10)],
                spread=[summary(p) for p in cat.top_spread()], drops=[summary(p) for p in cat.drops()],
                deals=[summary(p) for p in cat.deal_picks(seed=datetime.now().strftime("%Y-%m-%d %H"))],
                deals_total=cat.search(stock=True, deals=True)[1], deal_days=DEAL_DAYS, deal_show_percent=DEAL_SHOW),
            "brands": {"asiatica": brands(cat.brands), "dermocosmetica": brands(cat.derm_brands)},
            "stores": {"asiatica": asia, "dermocosmetica": derm, "chile": chile, "international": intl}, "events": [event_for(slug) for slug in dict.fromkeys(ev["slug"] for ev in all_events())], "live_event": live_event(),
            "shipping_reviewed": REVIEWED, "legal": documents, "operator_missing_fields": legal.missing()}


def history(p, db_path, page, limit):
    # Solo lectura, sin db.connect() (migraciones) ni sincronización de alias.
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")  # totales y observaciones comparten snapshot durante un scraping concurrente
        out = []
        for o in p.offers:
            total = db.execute("SELECT COUNT(*) FROM price WHERE listing_id=?", (o.listing_id,)).fetchone()[0]
            rows = db.execute("SELECT ts, price, available FROM price WHERE listing_id=? ORDER BY ts, rowid LIMIT ? OFFSET ?",
                              (o.listing_id, limit, (page - 1) * limit)).fetchall()
            out.append(dict(store=o.store, total=total, observations=[dict(captured_at=t, price=money(v, "CLP"),
                                                                       available=bool(a)) for t, v, a in rows]))
    return out


def sitemap_products(cat, db_path):
    """Productos del sitemap: los que alguna tienda chilena aún lista (Product.listed_in_chile), con `lastmod`, el día de su último
    cambio observado de precio, stock o precio tachado (save() solo agrega una fila de precio cuando algo de eso cambia)."""
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        last = dict(db.execute("SELECT listing_id, MAX(ts) FROM price GROUP BY listing_id"))
    out = []
    for p in cat.products:
        if p.listed_in_chile:
            ts = max((last.get(o.listing_id) or "" for o in [*p.offers, *p.intl]), default="")
            out.append({"id": p.id, "lastmod": local_day(ts) if ts else None})
    return out


def route(cat, path, qs, db_path):
    """Mismo tuple de transporte que server.route; no requests externos ni escrituras."""
    try:
        if path == PREFIX + "/site":
            validate(qs, set())
            return response(200, site(cat))
        if path == PREFIX + "/sitemap":
            validate(qs, set())
            return response(200, {**metadata(cat), "products": sitemap_products(cat, db_path)})
        if path == PREFIX + "/favorites":
            if set(qs) - {"ids"} or len(qs.get("ids", [])) > 1:
                raise ValueError("Parámetros desconocidos o repetidos")
            raw = qs.get("ids", [""])[0]
            ids = raw.split(",") if raw else []
            if len(ids) > 100 or any(not re.fullmatch(r"[0-9a-f]{10}", pid) for pid in ids):
                raise ValueError("Se permiten hasta 100 identificadores de producto válidos")
            resolutions = {pid: cat.resolve(pid) for pid in ids}
            canonical = dict.fromkeys(pid for pid in resolutions.values() if pid)
            return response(200, {**metadata(cat), "items": [summary(cat.by_id[pid]) for pid in canonical],
                                  "resolutions": resolutions, "missing_ids": [pid for pid, value in resolutions.items() if not value]})
        if path == PREFIX + "/suggestions":
            validate(qs, {"q"})
            q = qs.get("q", [""])[0].strip()[:100]
            items = cat.suggest(q)
            if len(items) < 6:
                items += cat.suggest(q, n=6 - len(items), section="dermocosmetica")
            sections = [dict(section=section, total=cat.search(q, stock=True, section=section)[1], path=base)
                        for section, base in [("asiatica", "/explorar"), ("dermocosmetica", "/dermocosmetica")]] if items else []
            return response(200, {**metadata(cat), "query": q, "items": [summary(p) for p in items],
                                  "sections": [row for row in sections if row["total"]]})
        if path == PREFIX + "/products":
            q, f, sort, page = filters(qs)
            items, total = cat.search(q, sort=sort, page=page, **f)
            facets = cat.counts(q, **f)
            other = "asiatica" if f["section"] == "dermocosmetica" else "dermocosmetica"
            other_total = cat.search(q, stock=f["stock"], section=other)[1] if q and not f["packs"] and not f["event"] and f["section"] else 0
            packs_total = (cat.search(q, f["brand"], stock=f["stock"], packs=True, section=f["section"], event=f["event"])[1]
                           if not f["packs"] and (q or f["brand"] or f["event"]) else 0)
            return response(200, {**metadata(cat), "items": [summary(p) for p in items], "total": total,
                                  "page": page, "page_size": PAGE_SIZE, "pages": max(1, -(-total // PAGE_SIZE)),
                                  "facets": {k: dict(sorted(v.items())) for k, v in facets.items()},
                                  "category_counts": dict(cat.counts(q, brand=f["brand"], stock=f["stock"], section=f["section"], event=f["event"])["cat"]),
                                  "related_counts": {"packs": packs_total, "other_section": other_total},
                                  "section_product_count": cat.section_counts.get(f["section"], len(cat.products))})
        if path.startswith(PREFIX + "/products/"):
            pid, _, tail = path[len(PREFIX + "/products/"):].partition("/")
            if not re.fullmatch(r"[0-9a-f]{10}", pid) or tail not in {"", "history"} or path.endswith("/"):
                return error(404, "not_found", "Producto o ruta no encontrado")
            validate(qs, {"pagina", "limite"} if tail else set())
            page = integer(qs.get("pagina", [""])[0], 1, 100000, 1)
            limit = integer(qs.get("limite", [""])[0], 100, 1000, 1)
            resolved = cat.resolve(pid)
            if resolved is None:
                return error(404, "not_found", "Producto no encontrado")
            p = cat.by_id[resolved]
            base = {**metadata(cat), "requested_id": pid, "canonical_id": resolved}
            if tail:
                return response(200, {**base, "stores": history(p, db_path, page, limit), "page": page, "limit": limit})
            return response(200, {**base, "product": detail(p, cat)})
        return error(404, "not_found", "Ruta de API no encontrada")
    except ValueError as ex:
        return error(400, "invalid_parameters", str(ex))
