import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import scrapers.dbs as dbs
from scrapers.dbs import parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "dbs_tiles.html"  # encabezado "22 artículos" y las 3 primeras tarjetas reales de /marcas/anua


def page():
    return FIXTURE.read_text(encoding="utf-8")


def test_tile_fields():
    items, claimed = parse_listing(page())
    assert len(items) == 3 and claimed == 22  # la página anuncia más de las que trae este fragmento: así se detecta una marca que trae menos de lo anunciado
    a = items[0]
    assert (a["ext_id"], a["title"], a["vendor"], a["currency"], a["available"], a["gtin"]) == ("103407", "Set Summer Glow", "ANUA", "CLP", 1, None)
    assert a["price"] == 59982 and a["compare_at"] == 99970 and a["description"] == "Set de Cuidado Facial"
    assert a["url"] == "https://dbs.cl/bdl-nx-6" and a["image"].startswith("https://dbs.cl/media/") and "&amp;" not in a["image"]


def test_compare_at_only_when_greater_than_price():
    items, _ = parse_listing(page().replace('data-price-amount="99970"', 'data-price-amount="59982"'))
    assert items[0]["compare_at"] is None and items[1]["compare_at"] == 39990


def test_tile_without_add_to_cart_form_is_unavailable():
    items, _ = parse_listing(page().replace('data-role="tocart-form"', 'data-role="x"', 1))
    assert [i["available"] for i in items] == [0, 1, 1]


def test_page_without_tiles_or_header():
    assert parse_listing("<html><body>nada</body></html>") == ([], None)


def test_adapter_reads_every_brand_once_and_dedups_products():
    saved = (dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS)
    urls, logs = [], []
    dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS = (lambda url, **k: urls.append(url) or page()), (lambda s: None), logs.append, ["anua", "cosrx"]
    try:
        items = list(dbs.dbs("dbs.cl"))
    finally:
        dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS = saved
    assert urls == ["https://dbs.cl/marcas/anua", "https://dbs.cl/marcas/cosrx"] and not any("?" in u for u in urls)  # su robots.txt veta cualquier parámetro
    assert len(items) == 3  # la segunda marca trae los mismos ids: no se repiten
    assert any("anuncian más" in m for m in logs)


def run_adapter(pages):
    """Corre el adaptador con una página por marca (dict slug -> html) y devuelve (items, logs, completion)."""
    saved = (dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS)
    logs = []
    dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS = (lambda url, **k: pages[url.rsplit("/", 1)[1]]), (lambda s: None), logs.append, list(pages)
    try:
        gen, items = dbs.dbs("dbs.cl"), []
        while True:
            try:
                items.append(next(gen))
            except StopIteration as stop:
                return items, logs, stop.value
    finally:
        dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS = saved


def test_empty_brand_is_a_full_read():
    empty = '<h1>Elizavecca</h1><div class="message info empty"><div>No podemos encontrar productos que coincida con la selección.</div></div>'
    items, logs, done = run_adapter({"anua": page(), "elizavecca": empty})
    assert len(items) == 3 and not any("None" in m for m in logs) and any("elizavecca: 0 productos (DBS muestra la marca vacía)" in m for m in logs)
    assert not any("sin leer" in m for m in logs)


def test_page_without_tiles_nor_empty_notice_counts_as_unread():
    items, logs, done = run_adapter({"anua": page(), "cosrx": "<html><body>otro diseño</body></html>"})
    assert len(items) == 3 and done.partial  # no se infiere que COSRX se vació en DBS
    assert any("cambió el HTML" in m for m in logs) and any("marcas sin leer: cosrx" in m for m in logs)


def test_blocked_stops_and_keeps_what_was_read():
    saved = (dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS)
    calls = []

    def fake(url, **k):
        calls.append(url)
        if len(calls) == 2:
            raise dbs.Blocked("HTTP 429")
        return page()

    dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS = fake, (lambda s: None), (lambda m: None), ["anua", "cosrx", "tocobo"]
    try:
        items = list(dbs.dbs("dbs.cl"))
    finally:
        dbs.get, dbs.time.sleep, dbs.log, dbs.BRANDS = saved
    assert len(items) == 3 and len(calls) == 2  # tras el 429 no se pide la tercera


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
