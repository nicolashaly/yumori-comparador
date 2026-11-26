import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import json
import urllib.error
from unittest import mock

from db import connect, done_today, save
from scrapers import http, jsonld, shopify, woocommerce
from scrapers.common import brand_from_title, gtin, short_title
from scrapers.fx import fx_from
from scrapers.http import Blocked

item = dict(ext_id="1", sku=None, title="Snail Essence", variant=None, vendor="COSRX",
            url="https://x.cl/products/snail", price=20000, compare_at=None, available=1)


def test_history():
    db = connect(":memory:")
    assert save(db, "x.cl", [item]) == (1, 1)  # primera vez: se registra
    assert save(db, "x.cl", [item]) == (1, 0)  # sin cambios: no se duplica
    assert save(db, "x.cl", [{**item, "price": 18000}]) == (1, 1)  # bajó de precio
    assert db.execute("SELECT count(*) FROM listing").fetchone()[0] == 1
    assert db.execute("SELECT price FROM price ORDER BY rowid").fetchall() == [(20000,), (18000,)]


def test_last_seen_marks_only_what_the_store_returned():
    db = connect(":memory:")
    save(db, "x.cl", [item, {**item, "ext_id": "2"}])
    db.execute("UPDATE listing SET last_seen='2026-01-01T00:00:00+00:00'")
    save(db, "x.cl", [item])  # el 2 ya no vino (la tienda lo borró o despublicó)
    seen = dict(db.execute("SELECT ext_id, last_seen FROM listing"))
    assert seen["2"] == "2026-01-01T00:00:00+00:00" and seen["1"] > seen["2"]


def test_currency_and_fx():
    db = connect(":memory:")
    save(db, "x.cl", [{**item, "ext_id": "2"}])
    save(db, "y.com", [{**item, "ext_id": "3", "currency": "USD", "price": 1732}])
    assert dict(db.execute("SELECT store, currency FROM listing")) == {"x.cl": "CLP", "y.com": "USD"}  # por defecto CLP
    assert fx_from({"serie": [{"fecha": "2026-09-21T03:00:00.000Z", "valor": 958.42}]}) == ("2026-09-21", 958.42)


def test_shopify_usd_official_store():
    def prod(title, price, was, ptype=""):
        return {"title": title, "handle": "h", "vendor": "COSRX official", "product_type": ptype, "images": [],
                "variants": [{"id": 1, "sku": "", "title": "Default Title", "price": price, "compare_at_price": was, "available": True}]}

    pages = iter([{"products": [prod("($80+ Free Gift) Full Fit Sheet Mask_CPNP", "6.99", "6.99"),
                                prod("Regalo", "0.00", None, "FREEGIFT_HIDDEN"),
                                prod("Ceramide Duo", "47.00", "59.00")]}, {"products": []}])
    with mock.patch.object(shopify, "get", lambda url, **kw: next(pages)), mock.patch.object(shopify.time, "sleep", lambda s: None):
        items = list(shopify.shopify("cosrx.com", "USD", vendor="COSRX"))
    assert [i["title"] for i in items] == ["Full Fit Sheet Mask", "Ceramide Duo"]  # sin promo, sin sufijo, sin regalo oculto
    assert items[0]["price"] == 699 and items[0]["compare_at"] is None  # centavos; "antes" igual al precio no cuenta
    assert items[1]["compare_at"] == 5900 and items[1]["vendor"] == "COSRX" and items[1]["currency"] == "USD"
    # en pesos igual: caso real de Moonbow/Arumi/Sokobox, que guardan un "antes" igual (o menor) al precio y se mostraba tachado
    pages = iter([{"products": [prod("Crema", "24900", "24900"), prod("Tónico", "15000", "12000"), prod("Sérum", "18000", "22000")]}, {"products": []}])
    with mock.patch.object(shopify, "get", lambda url, **kw: next(pages)), mock.patch.object(shopify.time, "sleep", lambda s: None):
        clp = list(shopify.shopify("tienda.cl"))
    assert [i["compare_at"] for i in clp] == [None, None, 22000]


def test_gtin_canonical_form_and_rejects():
    assert gtin("8809416470016") == "08809416470016"  # EAN-13 real de Unnie (COSRX Snail 92)
    assert gtin(8809416470016) == gtin("880941647001-6") == gtin(" 8809416470016 ")  # número, con guion o con espacios
    assert gtin("036000291452") == gtin("0036000291452") == "00036000291452"  # UPC-12 y su EAN-13 con 0 son el mismo código
    assert gtin("96385074") == "00000096385074" and gtin("10012345678902") == "10012345678902"  # EAN-8 y GTIN-14
    for bad in (None, "", "0", "00000000", "0000000000000", "8809416470015", "MCS0030", "2d9051434a004c808ea19e3d703a13b8", "123456",
                "88094164700160123", "880941647001A", "8.809416470016e12", 8.809416470016e12):
        assert gtin(bad) is None, bad


def test_jsonld_gtin_from_schema_org_fields_and_jumpseller_productid():
    base = {"@type": "Product", "name": "X", "offers": {"price": "1000"}}
    code = lambda **kw: jsonld.item_from_jsonld({**base, **kw})["gtin"]
    assert code(productID="8809416470016", sku="2d9051434a004c808ea19e3d703a13b8") == "08809416470016"  # Jumpseller
    assert code(gtin13="8809416470016") == code(gtin="8809416470016") == "08809416470016"
    assert jsonld.item_from_jsonld({**base, "offers": {"price": "1000", "gtin12": "036000291452"}})["gtin"] == "00036000291452"  # en la oferta
    assert code(sku="MCS0030") is None and code(productID="12345") is None  # Tiendanube / un id interno
    assert code(gtin13="1234567890123", productID="8809416470016") == "08809416470016"  # el inválido no tapa al válido


def test_save_keeps_gtin_when_a_later_read_lacks_it():
    db = connect(":memory:")
    save(db, "x.cl", [{**item, "gtin": "08809416470016"}])
    save(db, "x.cl", [item])  # sin gtin (la tienda dejó de publicarlo o la lectura no lo trae): se conserva
    assert db.execute("SELECT gtin FROM listing").fetchall() == [("08809416470016",)]
    import sqlite3, tempfile
    path = str(Path(tempfile.mkdtemp()) / "old.db")  # base creada antes de la columna: connect() la agrega sin perder filas
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE listing(id INTEGER PRIMARY KEY, store TEXT NOT NULL, ext_id TEXT NOT NULL, UNIQUE(store, ext_id))")
    old.execute("INSERT INTO listing(store, ext_id) VALUES('x.cl', '1')")
    old.commit(); old.close()
    migrated = connect(path)
    assert migrated.execute("SELECT store, gtin FROM listing").fetchall() == [("x.cl", None)]
    migrated.close()


def test_shopify_gtin_comes_from_a_barcode_like_sku_only():
    def prod(sku):
        return {"title": "T", "handle": "h", "vendor": "V", "images": [],
                "variants": [{"id": 1, "sku": sku, "title": "Default Title", "price": "1000", "compare_at_price": None, "available": True}]}

    # products.json no trae barcode: un SKU que es un EAN-13 válido sí; un SKU interno de 8 dígitos (Nooki) o con letras, no
    pages = iter([{"products": [prod("8809657122484"), prod("52102189"), prod("PND33"), prod(""), prod("880987545484")]}, {"products": []}])
    with mock.patch.object(shopify, "get", lambda url, **kw: next(pages)), mock.patch.object(shopify.time, "sleep", lambda s: None):
        got = [i["gtin"] for i in shopify.shopify("tienda.cl")]
    assert got == ["08809657122484", None, None, None, None]  # el último es un EAN-12 con un dígito mal (verificador inválido)


def test_brand_from_title_suffix():
    assert brand_from_title("Heartleaf 88 Soothing Serum – JMsolution") == "JMsolution"
    assert brand_from_title("Vitamin C Boosting Serum 30mL – Dr. Althea") == "Dr. Althea"
    assert brand_from_title("Serum Calmante – 30 ml") is None  # un tamaño no es una marca
    assert brand_from_title("Crema – hidratante intensiva para piel muy seca de noche") is None  # una frase larga tampoco
    assert brand_from_title("Sin sufijo de marca") is None


KORYO = """<html><head>
<script type="application/ld+json">{"@type": "Organization", "name": "Tienda"}</script>
<script type="application/ld+json">{"@context": "https://schema.org", "@type": "Product", "name": "rom&amp;nd - Juicy Lasting Tint", "sku": "JLT-0713",
 "brand": {"@type": "Brand", "name": "rom&amp;nd"}, "description": "<p>Tinte de larga duraci\u00f3n</p>", "image": "https://cdn/x.webp",
 "offers": {"@type": "Offer", "url": "https://k.cl/productos/romand-juicy/", "priceCurrency": "CLP", "price": "15900", "availability": "https://schema.org/InStock"}}</script>
<script type="application/ld+json">{"@type": "Product", "name": "Rodillo de hielo facial", "sku": "MHF0001",
 "offers": {"@type": "Offer", "url": "https://k.cl/productos/rodillo/", "price": "5375", "availability": "https://schema.org/OutOfStock"}}</script>
<script type="application/ld+json">{"@type": "Product", "name": "Sin precio", "offers": {"@type": "Offer"}}</script>
</head></html>"""

UNNIE = """<script type="application/ld+json">{"@type": "Product", "name": "Good Night White Sleeping Mask (Mizon) - 50 ml Crema aclarante nocturna",
 "brand": {"@type": "Brand", "name": "Mizon"}, "image": ["https://cdn/a.jpg", "https://cdn/b.jpg"],
 "offers": {"@type": "Offer", "price": 9990.0, "priceCurrency": "CLP", "availability": "https://schema.org/OutOfStock"},
 "aggregateRating": {"@type": "AggregateRating", "ratingValue": "5.0", "reviewCount": "3"}}</script>"""


def test_jsonld_products_to_items():
    prods = jsonld.jsonld_products(KORYO)
    items = [i for i in map(jsonld.item_from_jsonld, prods) if i]
    assert len(prods) == 3 and len(items) == 2  # el sin precio se descarta
    a, b = items
    assert (a["title"], a["vendor"], a["price"], a["available"], a["url"]) == ("Juicy Lasting Tint", "rom&nd", 15900, 1, "https://k.cl/productos/romand-juicy/")
    assert a["description"] == "Tinte de larga duración" and a["image"] == "https://cdn/x.webp"
    assert (b["title"], b["vendor"], b["available"]) == ("Rodillo de hielo facial", None, 0)


def test_unnie_title_size_brand_and_rating():
    p = jsonld.jsonld_products(UNNIE)[0]
    item = jsonld.item_from_jsonld(p, "https://unniebeauty.cl/good-night-white-sleeping-mask-mizon-50ml")
    assert short_title(p["name"], item["vendor"]) == "Good Night White Sleeping Mask 50 ml"
    assert (item["vendor"], item["price"], item["available"], item["rating"], item["reviews"]) == ("Mizon", 9990, 0, 5.0, 3)
    assert item["image"] == "https://cdn/a.jpg" and json.loads(item["images"]) == ["https://cdn/a.jpg", "https://cdn/b.jpg"]  # conserva las imágenes extra


def test_woocommerce_keeps_short_and_long_description():
    prod = {"id": 1, "sku": "", "name": "Kit", "brands": [], "permalink": "https://k.cl/p/", "images": [], "average_rating": "0", "review_count": 0,
            "prices": {"currency_code": "CLP", "currency_minor_unit": 0, "price": "1000", "regular_price": "1000"}, "is_in_stock": True,
            "short_description": "<p>Resumen corto</p>", "description": "<p>El set incluye: A 20ml B 30ml</p>"}
    with mock.patch.object(woocommerce, "get", lambda url, **kw: [prod]):
        item = next(woocommerce.woocommerce("k.cl"))
    assert item["description"] == "Resumen corto El set incluye: A 20ml B 30ml"  # antes solo se guardaba el corto y se perdía la lista


def test_429_is_not_retried():
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "60"}, None)

    with mock.patch.object(http.urllib.request, "urlopen", fake_urlopen):
        try:
            http.get("https://x.cl/")
            assert False, "debía lanzar Blocked"
        except Blocked as e:
            assert "429" in str(e) and "60" in str(e)
    assert len(calls) == 1  # un solo intento: insistir ante un 429 empeora el bloqueo


def test_html_where_json_is_expected_is_a_block_and_not_retried():
    calls = []

    class Page:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n): return b"\n<!DOCTYPE html><title>One moment, please...</title>"

    def fake_urlopen(req, timeout):
        calls.append(1)
        return Page()

    with mock.patch.object(http.urllib.request, "urlopen", fake_urlopen):
        try:
            http.get("https://x.cl/wp-json/wc/store/v1/products")
            assert False, "debía lanzar Blocked"
        except Blocked as e:
            assert "HTML" in str(e)
        assert http.get("https://x.cl/", text=True).lstrip().startswith("<!DOCTYPE")  # con text=True el HTML es lo esperado
    assert len(calls) == 2  # uno por llamada: el bloqueo no se reintenta


def test_done_today_only_counts_a_complete_run_from_today():
    from datetime import datetime, timedelta, timezone
    db = connect(":memory:")
    assert not done_today(db)  # base nueva: nunca corrió
    now = datetime.now(timezone.utc)
    db.execute("INSERT OR REPLACE INTO meta VALUES('run:done', ?)", ((now - timedelta(days=1)).isoformat(timespec="seconds"),))
    assert not done_today(db)  # la de ayer no cuenta
    db.execute("INSERT OR REPLACE INTO meta VALUES('run:done', ?)", (now.isoformat(timespec="seconds"),))
    assert done_today(db)


def test_paused_stores_are_known_and_not_retired():
    import scrape
    from db import PAUSED, RETIRED
    assert PAUSED <= set(scrape.STORES)  # un dominio mal escrito no pausaría nada
    assert not PAUSED & RETIRED  # una retirada no se muestra; una en pausa sí, como "Sin conexión"


def test_price_anomalies():
    from db import anomaly
    assert anomaly(1000000) == "fuera de rango"  # caso real: Vierose publicó productos a $1.000.000 como relleno de "no disponible"
    assert anomaly(5) == "fuera de rango" and anomaly(0) is None  # $5 no es un precio; $0 es un regalo y se excluye aparte
    assert anomaly(23990, 1000000) is None  # corregir el relleno no es una "baja de 98%"
    assert anomaly(1200, 20000) == "bajó 94%" and anomaly(90000, 20000) == "subió 350%"
    assert anomaly(14000, 20000) is None and anomaly(1732, None, "USD") is None  # una oferta de 30% y US$17,32 son normales
    db, bad = connect(":memory:"), []
    save(db, "x.cl", [item], anomalies=bad)
    save(db, "x.cl", [{**item, "price": 1200}], anomalies=bad)
    save(db, "x.cl", [{**item, "price": 1200}], anomalies=bad)  # sin cambio: no se vuelve a anotar
    assert bad == [("Snail Essence", "bajó 94%")]
    assert db.execute("SELECT price FROM price ORDER BY rowid").fetchall() == [(20000,), (1200,)]  # se guarda igual: el catálogo decide


def test_each_store_leaves_a_scrape_run_row():
    import scrape
    db = connect(":memory:")

    def broken(domain):
        raise TimeoutError("timed out")
        yield

    with mock.patch.dict(scrape.STORES, {"ok.cl": lambda d: iter([item, {**item, "ext_id": "2", "price": 1000000}]), "mala.cl": broken}),             mock.patch.object(scrape, "log", lambda msg: None):
        scrape.scrape_store(db, "ok.cl", "2026-10-03T07:00:00+00:00")
        scrape.scrape_store(db, "mala.cl", "2026-10-03T07:00:00+00:00")  # una tienda que falla no detiene la corrida
    rows = db.execute("SELECT store, status, items, changed, anomalies, error FROM scrape_run ORDER BY store").fetchall()
    assert rows == [("mala.cl", "error", None, None, 0, "timed out"), ("ok.cl", "ok", 2, 2, 1, None)], rows
    assert db.execute("SELECT key FROM meta").fetchall() == [("scraped:ok.cl",)]  # la que falló no cuenta como leída


def test_oversized_response_is_rejected():
    class Big:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n): return b"x" * n  # devuelve todo lo que se le pida: más de MAX_BYTES

    with mock.patch.object(http.urllib.request, "urlopen", lambda req, timeout: Big()), mock.patch.object(http.time, "sleep", lambda s: None):
        try:
            http.get("https://x.cl/", text=True)
            assert False, "debía rechazar la respuesta"
        except ValueError as e:
            assert "MB" in str(e)


if __name__ == "__main__":
    test_price_anomalies()
    test_each_store_leaves_a_scrape_run_row()
    test_oversized_response_is_rejected()
    test_done_today_only_counts_a_complete_run_from_today()
    test_gtin_canonical_form_and_rejects()
    test_jsonld_gtin_from_schema_org_fields_and_jumpseller_productid()
    test_save_keeps_gtin_when_a_later_read_lacks_it()
    test_shopify_gtin_comes_from_a_barcode_like_sku_only()
    test_history()
    test_last_seen_marks_only_what_the_store_returned()
    test_currency_and_fx()
    test_brand_from_title_suffix()
    test_jsonld_products_to_items()
    test_unnie_title_size_brand_and_rating()
    test_woocommerce_keeps_short_and_long_description()
    test_429_is_not_retried()
    test_html_where_json_is_expected_is_a_block_and_not_retried()
    test_shopify_usd_official_store()
    print("ok")
