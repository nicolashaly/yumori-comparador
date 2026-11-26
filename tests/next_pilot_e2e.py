"""Paridad HTTP del build Next con API real y SQLite temporal (solo stdlib)."""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener, urlopen
from urllib.parse import parse_qs
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server
from catalog import Catalog
from db import connect, save


class Document(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.links = []
        self.text = []
        self.times = []
        self.canonical = None
        self.elements = []
        self.stack = []
        self.prices = []
        self.products = []
        self.rows = {}
        self.facets = {}
        self.facet_counts = {}
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if "data-product-id" in attrs:
            context = {}
            for _, ancestor in self.stack:
                context.update(ancestor)
            self.products.append({**context, **attrs})
        if "data-price-amount" in attrs:
            context = {}
            for _, ancestor in self.stack:
                context.update(ancestor)
            self.prices.append({**context, **attrs})
        if "data-store-id" in attrs:
            self.rows[attrs["data-store-id"]] = {"attrs": attrs, "text": []}
        if "data-facet-name" in attrs:
            name, value = attrs["data-facet-name"], attrs["data-facet-value"]
            assert value not in self.facets.get(name, {}), ("Faceta duplicada", name, value)
            self.facets.setdefault(name, {})[value] = []
            self.facet_counts.setdefault(name, {})[value] = int(attrs["data-facet-count"])
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, attrs))
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "time":
            self.times.append(attrs.get("datetime"))
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")

    def handle_data(self, data):
        self.text.append(data)
        for tag, attrs in self.stack:
            if "data-store-id" in attrs:
                self.rows[attrs["data-store-id"]]["text"].append(data)
        facet = next((attrs for _, attrs in reversed(self.stack) if "data-facet-name" in attrs), None)
        if facet:
            self.facets[facet["data-facet-name"]][facet["data-facet-value"]].append(data)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    @property
    def visible(self):
        return " ".join(self.text)


def seed(path):
    db = connect(path)
    def item(ext, title, price=20000, **extra):
        return dict(ext_id=str(ext), sku=None, title=title, variant=None,
                    vendor="Cosrx", url=f"https://fixture.invalid/{ext}",
                    price=price, compare_at=None, available=1, **extra)
    title = "Advanced Snail Essence 100ml"
    for store, price in [("valid.cl", 20000), ("tie.cl", 20000),
                         ("stale.cl", 10000), ("gone.cl", 11000), ("suspect.cl", 50)]:
        save(db, store, [item(1, title, price)], seen_at="2026-10-01T00:00:00+00:00")
    save(db, "gone.cl", [item(2, "Other Cleanser 150ml", 15000)], seen_at="2026-10-02T00:00:00+00:00")
    save(db, "foreign.invalid", [item(3, title, 1732, currency="USD"),
                                 item(4, "Foreign Only Toner 250ml", 1732, currency="USD")])
    save(db, "valid.cl", [item(1, title), {**item(5, "Unavailable Cream 50ml"), "available": 0},
                         item(6, "Snail Routine Kit 100ml"),
                         {**item(7, "Cicaplast Balm 40ml"), "vendor": "La Roche-Posay"},
                         {**item(8, "Cicaplast Routine Kit 40ml"), "vendor": "La Roche-Posay"}],
         seen_at="2026-10-02T00:00:00+00:00")
    db.execute("INSERT INTO fx VALUES('2026-10-01', 958.42)")
    for store in ("valid.cl", "tie.cl", "gone.cl", "suspect.cl", "foreign.invalid"):
        db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", ("scraped:" + store, "2026-10-02T00:00:00+00:00"))
    db.execute("INSERT OR REPLACE INTO meta VALUES('scraped:stale.cl','2026-10-01T00:00:00+00:00')")
    db.execute("INSERT INTO meta VALUES('run:done','2026-10-02T00:00:00+00:00')")
    db.commit()
    cat = Catalog(db, sync=False)
    pid = next(p.id for p in cat.products if "Advanced Snail" in p.name)
    alias = "0123456789"
    db.execute("INSERT INTO product_alias VALUES(?,?,?)", (alias, pid, "2026-10-02T00:00:00+00:00"))
    db.commit()
    cat = Catalog(db, sync=False)
    # sync=False evita escrituras y omite cargar aliases; la fixture los carga
    # explícitamente desde su propia base, como el catálogo servido normalmente.
    cat.alias = dict(db.execute("SELECT old_id,new_id FROM product_alias"))
    db.close()
    return cat, pid, alias


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def get(url, *, headers=False, redirect=True):
    open_url = urlopen if redirect else build_opener(NoRedirect()).open
    try:
        with open_url(url, timeout=5) as response:
            result = response.status, response.read().decode(), response.geturl()
            return (*result, response.headers) if headers else result
    except HTTPError as error:
        result = error.code, error.read().decode(), error.geturl()
        return (*result, error.headers) if headers else result


def verify_csp(origin, document, headers):
    directives = dict((parts[0], parts[1:]) for directive in headers.get("Content-Security-Policy", "").split(";")
                      if (parts := directive.strip().split()))
    scripts = directives.get("script-src", directives.get("default-src", []))
    assert "'unsafe-eval'" not in scripts and "'unsafe-inline'" not in scripts, scripts
    nonces = [source[7:-1] for source in scripts if source.startswith("'nonce-") and source.endswith("'")]
    assert len(nonces) == 1, scripts
    external = []
    for tag, attrs in document.elements:
        if tag != "script" or attrs.get("type") == "application/ld+json":  # JSON-LD es dato inerte: no se ejecuta ni lo bloquea la CSP
            continue
        assert attrs.get("nonce") == nonces[0], attrs
        if attrs.get("src"):
            source = attrs["src"]
            assert source.startswith("/") and not source.startswith("//"), source
            external.append(source)
    assert external, "Faltan scripts de Next"
    for source in set(external):
        status, _, _, asset_headers = get(origin + source, headers=True)
        assert status == 200, source
        assert "javascript" in asset_headers.get("Content-Type", "").lower(), source


def verify_visual_assets(origin, document):
    original = ROOT / "static/style.css"
    assert original.read_bytes() == (ROOT / "frontend/app/original.css").read_bytes(), "El CSS original diverge de su copia Next"
    stylesheets = [attrs["href"] for tag, attrs in document.elements
                   if tag == "link" and attrs.get("rel") == "stylesheet"]
    assert stylesheets, "Falta hoja de estilos"
    css = "\n".join(get(origin + source)[1] for source in stylesheets)
    for selector in (".hero-title", ".explore", ".store-card", ".ev-logo", ".legal"):
        assert selector in css, ("CSS original no servido", selector)
    assets = set(re.findall(r'url\("(/static/[^"\)]+)"\)', original.read_text(encoding="utf-8")))
    assert len(assets) == 5, assets
    for asset in assets:
        expected = (ROOT / asset.lstrip("/")).read_bytes()
        assert expected == (ROOT / "frontend/public" / asset.lstrip("/")).read_bytes(), ("Asset copiado diverge", asset)
        with urlopen(origin + asset, timeout=5) as response:
            assert response.status == 200 and response.read() == expected, ("Asset servido diverge", asset)
    return len(assets) + 1


def verify(origin, api_origin, pid, alias):
    checks = 0
    site = json.loads(get(api_origin + "/api/v1/site")[1])
    for query in ("", "sinstock=1", "q=snail", "orden=precio_asc", "tienda=valid.cl&tienda=tie.cl", "q=no-result-fixture", "pagina=2"):
        status, body, _ = get(api_origin + "/api/v1/products?" + query + "&packs=0&seccion=asiatica")
        assert status == 200
        data = json.loads(body)
        status, html, _, headers = get(origin + "/explorar?" + query, headers=True)
        assert status == 200, (query, status)
        doc = Document(html)
        ids = [attrs["data-product-id"] for _, attrs in doc.elements if "data-product-id" in attrs]
        assert ids == [p["id"] for p in data["items"]], (query, ids, data["items"])
        assert any(attrs.get("data-total") == str(data["total"]) for _, attrs in doc.elements), query
        for key in ("cat", "tipo", "piel", "ing", "tienda"):
            actual = {value: int("".join(label).replace(".", ""))
                      for value, label in doc.facets.get(key, {}).items()}
            assert actual == doc.facet_counts.get(key, {}), (query, key, "Conteo visible", actual)
            if key == "cat":
                expected = {category["slug"]: data["category_counts"].get(category["slug"], 0)
                            for category in site["categories"]}
            else:
                counts = dict(data["facets"].get(key, {}))
                if key == "tienda":
                    for store in site["stores"]["asiatica"]:
                        counts.setdefault(store["domain"], 0)
                options = sorted(counts.items(), key=lambda option: -option[1])
                if key in {"tipo", "ing"}:
                    options = options[:16 if key == "tipo" else 12]
                expected = dict(options)
                for value in parse_qs(query).get(key, []):
                    expected.setdefault(value, counts.get(value, 0))
                inputs = {attrs["value"]: attrs for tag, attrs in doc.elements
                          if tag == "input" and attrs.get("type") == "checkbox" and attrs.get("name") == key}
                assert set(inputs) == set(expected), (query, key, "Checkboxes", inputs, expected)
                assert {value for value, attrs in inputs.items() if "checked" in attrs} == set(parse_qs(query).get(key, [])), (query, key, "Selección", inputs)
            assert actual == expected, (query, key, actual, expected)
        for product in data["items"]:
            amount = product["display_price"]["amount"] if product["display_price"] else ""
            assert any(attrs.get("data-product-id") == product["id"] and attrs.get("data-price-amount") == str(amount)
                       and attrs.get("data-currency") == product["display_price"]["currency"]
                       for attrs in doc.prices), product
        if not query:
            verify_csp(origin, doc, headers)
            checks += verify_visual_assets(origin, doc)
        checks += 1
    data = json.loads(get(api_origin + f"/api/v1/products/{pid}")[1])
    status, html, _, headers = get(origin + f"/p/{pid}", headers=True)
    assert status == 200
    doc = Document(html)
    verify_csp(origin, doc, headers)
    assert doc.canonical and doc.canonical.endswith(f"/p/{pid}"), doc.canonical
    assert data["catalog_last_update"] in doc.times, doc.times
    for offer in data["product"]["domestic_offers"] + data["product"]["international_offers"]:
        assert offer["status_label"] in doc.visible, offer
        assert any(attrs.get("data-store-id") == offer["store"] and attrs.get("data-offer-status") == offer["status"]
                   and attrs.get("data-price-amount") == str(offer["price"]["amount"])
                   and attrs.get("data-currency") == offer["price"]["currency"]
                   for attrs in doc.prices), offer
        best_label = "Mejor precio confirmado" in " ".join(doc.rows[offer["store"]]["text"])
        assert best_label == (offer["store"] in data["product"]["best_store_ids"]), offer
    assert data["product"]["best_store_ids"] == ["tie.cl", "valid.cl"]
    history = json.loads(get(api_origin + f"/api/v1/products/{pid}/history?limite=100")[1])
    for store in history["stores"]:
        for observation in store["observations"]:
            assert any(a.get("data-history-store") == store["store"]
                       and a.get("data-captured-at") == observation["captured_at"]
                       and a.get("data-price-amount") == str(observation["price"]["amount"])
                       and a.get("data-currency") == "CLP" for a in doc.prices), (store, observation)
    status, _, _, headers = get(origin + f"/p/{alias}", headers=True, redirect=False)
    assert status == 308 and headers.get("Location") == f"/p/{pid}", (status, headers)
    status, _, final = get(origin + f"/p/{alias}")
    assert status == 200 and final.endswith(f"/p/{pid}"), final
    assert get(origin + "/p/fffffffffe")[0] == 404
    status, html, _ = get(origin + "/explorar?pagina=0")
    assert status == 200 and "inválidos" in Document(html).visible.lower(), (status, html[:500])
    # Listados por marca: título propio (no el genérico compartido) e indexable; una marca inexistente, noindex.
    brand = site["brands"]["asiatica"][0]
    robots = lambda doc: next((a.get("content") for t, a in doc.elements if t == "meta" and a.get("name") == "robots"), "")
    html = get(origin + f"/explorar?marca={brand['slug']}")[1]
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert title.startswith(f"{brand['name']}: precios en Chile") and "noindex" not in robots(Document(html)), title
    assert "noindex" in robots(Document(get(origin + "/explorar?marca=no-existe-fixture")[1]))
    # El título de una marca no se arrastra a las visitas siguientes (pasó en producción el 2026-11-25).
    html = get(origin + "/explorar?marca=no-existe-fixture")[1] + get(origin + "/explorar")[1]
    assert brand["name"] not in "".join(re.findall(r"<title>(.*?)</title>", html)), re.findall(r"<title>(.*?)</title>", html)
    html = get(origin + f"/explorar?marca={brand['slug']}&pagina=1e3")[1]
    assert "1e3" not in re.search(r"<title>(.*?)</title>", html).group(1) and "noindex" in robots(Document(html))
    # JSON-LD: Product solo con stock confirmado en Chile (sin offers sería un error crítico para Google).
    lds = lambda html: [json.loads(m)["@type"] for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
    assert lds(get(origin + f"/p/{pid}")[1]) == ["Product", "BreadcrumbList"]
    listing = json.loads(get(api_origin + "/api/v1/products?sinstock=1&packs=0&seccion=asiatica&q=unavailable")[1])
    out = next(p for p in listing["items"] if "Unavailable Cream" in p["name"])
    assert lds(get(origin + f"/p/{out['id']}")[1]) == ["BreadcrumbList"], out
    # Sitemap: los productos de la API (los que una tienda chilena aún lista), cada uno con su lastmod.
    expected = {f"{origin}/p/{p['id']}": p["lastmod"] for p in json.loads(get(api_origin + "/api/v1/sitemap")[1])["products"]}
    xml = get(origin + "/sitemap.xml")[1]
    found = dict(re.findall(r"<loc>([^<]*/p/[0-9a-f]{10})</loc>\s*<lastmod>([^<]*)</lastmod>", xml))
    assert expected and {u: d[:10] for u, d in found.items()} == expected, (expected, found)
    return checks + 12 + verify_remaining(origin, api_origin, pid, alias)


def verify_remaining(origin, api_origin, pid, alias):
    """Cada listado deriva sus IDs de Catalog; el frontend solo presenta."""
    checks = 0
    for path in ("/", "/explorar", f"/p/{pid}", "/packs", "/dermocosmetica"):
        assert get(api_origin + path)[0] == 200, ("renderer Python", path)
        checks += 1
    site = json.loads(get(api_origin + "/api/v1/site")[1])
    listings = [("/dermocosmetica", "seccion=dermocosmetica&packs=0"),
                        ("/packs", "packs=1&seccion=asiatica"),
                        ("/dermocosmetica/packs", "packs=1&seccion=dermocosmetica")]
    for event in sorted({e["slug"] for e in site["events"]}):
        for packs in (0, 1):
            listings.append((f"/{event}" + ("/packs" if packs else ""), f"evento={event}&seccion=todas&packs={packs}"))
    for path, query in listings:
        api_status, body, _ = get(api_origin + "/api/v1/products?" + query)
        assert api_status == 200, (path, api_status, body)
        expected = json.loads(body)
        status, html, _ = get(origin + path)
        assert status == 200, (path, status)
        document = Document(html)
        assert [p["data-product-id"] for p in document.products] == [p["id"] for p in expected["items"]], path
        assert any(a.get("data-total") == str(expected["total"]) for _, a in document.elements), path
        checks += 1
    status, html, _ = get(origin + "/")
    assert status == 200
    document = Document(html)
    expected_ids = [p["id"] for key in ("deals", "spread", "drops") for p in site["home"][key]]
    assert [p["data-product-id"] for p in document.products] == expected_ids
    checks += 1
    for path, source, marker, key, sections in [
            ("/marcas", "brands", "data-brand-slug", "slug", ("asiatica", "dermocosmetica")),
            ("/tiendas", "stores", "data-store-domain", "domain", ("chile", "international"))]:
        status, html, _ = get(origin + path)
        assert status == 200, (path, status)
        document = Document(html)
        assert [a[marker] for _, a in document.elements if marker in a] == [row[key] for section in sections for row in site[source][section]], path
        checks += 1
    for endpoint, query in [("favorites", f"ids={alias},{pid},fffffffffe"), ("suggestions", "q=snail")]:
        status, body, _ = get(origin + "/api/" + endpoint + "?" + query)
        expected = json.loads(get(api_origin + "/api/v1/" + endpoint + "?" + query)[1])
        assert status == 200, (endpoint, status)
        assert json.loads(body) == expected, endpoint
        checks += 1
    for endpoint, query in [("favorites", "ids=invalid"), ("suggestions", "unknown=1")]:
        assert get(origin + "/api/" + endpoint + "?" + query)[0] == 400, endpoint
        checks += 1
    for endpoint, query in [("favorites", f"ids={pid}"), ("suggestions", "q=snail")]:
        status, _, _, headers = get(origin + "/api/" + endpoint + "?" + query, headers=True)
        assert status == 200 and "no-store" in headers.get("Cache-Control", ""), endpoint
        checks += 1
    status, html, _ = get(origin + "/favoritos")
    assert status == 200 and "favoritos" in Document(html).visible.lower()
    return checks + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"), help="Ruta del ejecutable Node")
    parser.add_argument("--serve", action="store_true", help="Mantener la fixture para revisión manual hasta Ctrl+C")
    args = parser.parse_args()
    next_cli = ROOT / "frontend/node_modules/next/dist/bin/next"
    if not args.node or not next_cli.exists() or not (ROOT / "frontend/.next/BUILD_ID").exists():
        parser.error("Se necesita Node, dependencias de frontend y npm run build completado")
    temporary_root = ROOT / "data"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yumori-next-", dir=temporary_root) as tmp, ExitStack() as stack:
        path = Path(tmp) / "fixture.db"
        cat, pid, alias = seed(path)
        stack.enter_context(patch.object(server, "DB", path))
        stack.enter_context(patch.object(server, "get_catalog", lambda: cat))
        api_server = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=api_server.serve_forever, daemon=True).start()
        stack.callback(api_server.server_close)
        stack.callback(api_server.shutdown)
        api_origin = f"http://127.0.0.1:{api_server.server_port}"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        log = stack.enter_context(open(Path(tmp) / "next.log", "w+", encoding="utf-8"))
        # args.node es la ruta de Node que pasa quien corre esta prueba por la línea de comandos; se pasa como lista, sin shell.
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
        process = subprocess.Popen([args.node, str(next_cli), "start", "--hostname", "127.0.0.1", "--port", str(port)],
                                   cwd=ROOT / "frontend", env={**os.environ, "YUMORI_API_ORIGIN": api_origin, "YUMORI_URL": origin},
                                   stdout=log, stderr=subprocess.STDOUT)
        def stop():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        stack.callback(stop)
        last_response = None
        for _ in range(120):
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError(log.read())
            try:
                last_response = get(origin + "/explorar")
                if last_response[0] == 200:
                    break
            except (URLError, TimeoutError):
                pass
            time.sleep(.25)
        else:
            log.seek(0)
            raise RuntimeError(f"Next no arrancó en 30 segundos. Respuesta: {last_response and last_response[:2]}\n{log.read()}")
        if args.serve:
            print(f"Fixture temporal: {origin} | Renderer Python: {api_origin} | Producto: {origin}/p/{pid} | Alias: {alias}", flush=True)
            print("Ctrl+C detiene ambos servidores y elimina SQLite temporal.", flush=True)
            try:
                while process.poll() is None:
                    time.sleep(.25)
            except KeyboardInterrupt:
                return 0
            raise RuntimeError("Next se detuvo durante la revisión")
        count = verify(origin, api_origin, pid, alias)
        api_server.shutdown()
        api_server.server_close()
        status, html, _ = get(origin + "/explorar")
        assert status == 200 and "Sin conexión" in Document(html).visible
        for endpoint, query in [("favorites", f"ids={pid}"), ("suggestions", "q=snail")]:
            assert get(origin + "/api/" + endpoint + "?" + query)[0] == 503, endpoint
        print(f"OK: {count + 3} comprobaciones HTTP; API fixture temporal, sin base personal ni scraping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
