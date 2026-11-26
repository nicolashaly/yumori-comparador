import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import scrapers.vtex as vx
from scrapers.vtex import parse_product

FIXTURE = Path(__file__).parent / "fixtures" / "vtex_products.json"  # 2 productos reales de drsimi.cl (/api/catalog_system/pub/products/search), sin los campos que no se usan


def products():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_product_fields():
    (a,) = parse_product(products()[0])
    assert (a["ext_id"], a["sku"], a["vendor"], a["currency"], a["available"], a["variant"]) == ("444", "CH5769", "DERMO LISSE", "CLP", 1, None)
    assert a["title"] == "Loción pH5 con urea 10% 200 mL" and a["price"] == 9800 and a["compare_at"] is None
    assert a["gtin"] == "07804654810069"  # el EAN viene en la especificación EANCode (el del item está vacío), con un solo SKU
    assert a["url"] == "https://www.drsimi.cl/locion-ph-5-emulsion-hidratante-ph-5-con-urea-200-ml/p" and a["image"].startswith("https://")
    assert len(json.loads(a["images"])) == 2 and a["description"].startswith("Loción pH5 ha sido formulada")


def test_list_price_is_compare_at_only_when_greater():
    p = products()[0]
    p["items"][0]["sellers"][0]["commertialOffer"]["ListPrice"] = 12000
    assert parse_product(p)[0]["compare_at"] == 12000
    p["items"][0]["sellers"][0]["commertialOffer"]["ListPrice"] = 9800
    assert parse_product(p)[0]["compare_at"] is None


def test_sku_without_price_is_dropped_and_unavailable_is_kept_with_price():
    p = products()[0]
    p["items"][0]["sellers"][0]["commertialOffer"].update(Price=0)
    assert parse_product(p) == []
    p["items"][0]["sellers"][0]["commertialOffer"].update(Price=9800, IsAvailable=False)
    assert parse_product(p)[0]["available"] == 0


def test_several_skus_become_variants_and_the_spec_ean_is_not_guessed():
    p = products()[0]
    second = copy.deepcopy(p["items"][0])
    second.update(itemId="445", name="Loción pH5 con urea 10% 400 mL")
    p["items"].append(second)
    a, b = parse_product(p)
    assert (a["variant"], b["variant"], a["gtin"], b["gtin"]) == (None, "Loción pH5 con urea 10% 400 mL", None, None)
    # el SKU con ean propio sí lo usa
    p["items"][1]["ean"] = "7804654810069"
    assert parse_product(p)[1]["gtin"] == "07804654810069"


def test_wanted_filters_by_category():
    p = products()[0]
    assert parse_product(p, lambda x: any(i.startswith("/279/") for i in x["categoriesIds"]))
    assert parse_product(p, lambda x: any(i.startswith("/5/") for i in x["categoriesIds"])) == []


def fake_adapter(pages, **kw):
    """Corre vtex() con la API simulada: `pages` = lo que responde cada solicitud, en orden (una excepción se lanza)."""
    saved, urls = (vx.get, vx.time.sleep, vx.log), []

    def get(url, **k):
        urls.append(url)
        r = pages[len(urls) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    vx.get, vx.time.sleep, vx.log = get, (lambda s: None), (lambda m: None)
    try:
        return list(vx.vtex("x.cl", **kw)), urls
    finally:
        vx.get, vx.time.sleep, vx.log = saved


def test_adapter_pages_by_50_and_stops_on_a_short_page():
    base = products()[0]
    full = []
    for n in range(50):  # una página llena: 50 productos distintos
        p = copy.deepcopy(base)
        p["items"][0]["itemId"] = str(1000 + n)
        full.append(p)
    items, urls = fake_adapter([full, products()], categories=["279"])
    assert len(items) == 52 and len(urls) == 2  # 50 de la primera página + los 2 de la segunda (más corta que 50: no se pide una tercera)
    assert urls[0].endswith("fq=C:/279/&_from=0&_to=49") and urls[1].endswith("&_from=50&_to=99")


def test_adapter_drops_products_outside_the_requested_category():
    items, _ = fake_adapter([products()], categories=["5"])
    assert items == []  # el servidor ignoró el filtro: no se cuela nada


def test_blocked_stops_without_retrying():
    base = products()[0]
    full = [copy.deepcopy(base) for _ in range(50)]
    for n, p in enumerate(full):
        p["items"][0]["itemId"] = str(2000 + n)
    items, urls = fake_adapter([full, vx.Blocked("HTTP 429"), full], categories=["279"])
    assert len(items) == 50 and len(urls) == 2  # tras el 429 no se vuelve a pedir


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
