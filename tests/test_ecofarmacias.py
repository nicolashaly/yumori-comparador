import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import scrapers.ecofarmacias as eco
import scrapers.woocommerce as woo

FIXTURE = Path(__file__).parent / "fixtures" / "ecofarmacias_products.json"  # 10 productos reales de la Store API (Dermocosmética y Protectores Solares)


def run():
    """Lo que entrega ecofarmacias() con la API simulada (una sola página por categoría, la misma en las dos)."""
    data, saved = json.loads(FIXTURE.read_text(encoding="utf-8")), (woo.get, eco.time.sleep, eco.log)
    urls = []
    woo.get, eco.time.sleep, eco.log = (lambda url: urls.append(url) or data), (lambda s: None), (lambda m: None)
    try:
        return {i["ext_id"]: i for i in eco.ecofarmacias("x")}, urls
    finally:
        woo.get, eco.time.sleep, eco.log = saved


def test_only_the_two_dermo_categories_are_requested():
    _, urls = run()
    assert [u.rsplit("&", 1)[1] for u in urls] == ["category=1450", "category=112"]


def test_short_dated_duplicates_and_medicines_are_dropped():
    items, _ = run()
    assert len(items) == 6  # 10 de la API: 2 con "DESCUENTO" (SKU con ",1"), 2 papilomas/adapaleno y 2 productos repetidos en las dos categorías
    assert not any("DESCUENTO" in i["title"] or "Adapaleno" in i["title"] or "Papilomas" in i["title"] for i in items.values())


def test_brand_comes_from_the_title_and_is_removed_from_the_middle():
    items, _ = run()
    assert items["129408"]["vendor"] == "ISDIN" and items["129408"]["title"] == "FotoUltra Active Unify Color SPF 50+ (Aclara y Unifica) 50 Ml"
    assert items["55671"]["vendor"] == "La Roche-Posay" and items["363269"]["vendor"] == "Avène"  # "Roche Posay" y "Avene" sin acento


def test_ean_is_read_from_the_sku_and_price_fields():
    a = run()[0]["253215"]
    assert (a["gtin"], a["currency"], a["price"], a["compare_at"], a["available"]) == ("04005900516961", "CLP", 29290, 32900, 0)
    assert run()[0]["395220"]["available"] == 1 and run()[0]["395220"]["compare_at"] is None  # sin "antes" cuando el precio normal es igual


def test_clean_flags_a_comma_sku_even_without_the_word_in_the_title():
    items, dropped = eco.clean([dict(ext_id="1", sku="3337875597272,1", title="Cerave Crema Ojos 14 ml", vendor=None, price=1)])
    assert not items and "remate" in dropped


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
