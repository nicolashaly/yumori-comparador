import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import scrapers.paris as pa
from scrapers.dermo import brand_in, brand_of
from scrapers.paris import parse_page, product_data

FIXTURE = Path(__file__).parent / "fixtures" / "paris_flight.html"  # 6 productos reales recortados, repartidos en dos push() del flujo de Next


def page():
    return FIXTURE.read_text(encoding="utf-8")


def test_flight_chunks_are_joined_and_product_data_found():
    d = product_data(page())
    assert d["total"] == 1156 and len(d["products"]) == 6


def test_offer_price_is_the_price_and_regular_is_compare_at():
    a = parse_page(page())[0][0]
    assert (a["ext_id"], a["vendor"], a["price"], a["compare_at"], a["available"], a["currency"], a["gtin"]) == ("MKX5B1I05Q", "Eucerin", 32020, 42690, 1, "CLP", None)
    assert a["url"] == "https://www.paris.cl/eucerin-anti-pigment-crema-facial-de-dia-fps-30-50ml-MKX5B1I05Q.html"
    assert a["card_price"] is None and a["image"].startswith("https://") and a["images"].startswith("[")


def test_no_offer_means_no_compare_at_and_brand_in_the_middle_is_removed():
    b = parse_page(page())[0][1]
    assert b["price"] == 25290 and b["compare_at"] is None
    assert b["title"] == "Shampoo Anti-Caspa Cabellos Grasos 390 ml"  # "Vichy" en medio y al final; vendor la conserva
    assert b["vendor"] == "Vichy"


def test_only_dermo_brands_are_kept_and_the_rest_counted():
    items, total, other = parse_page(page())
    assert other == 1 and total == 1156  # Dr. Althea (vendido por Sokobox en el marketplace): Paris no es farmacia, caería en la sección asiática
    assert [i["vendor"] for i in items] == ["Eucerin", "Vichy", "La Roche-Posay", "Avène", "Eucerin"]  # "La Roche Posay" y "Avéne" (acento agudo) se normalizan


def test_compare_at_only_when_greater_than_price():
    p = page().replace("42690", "32020")
    assert parse_page(p)[0][0]["compare_at"] is None


def test_page_without_product_data_fails_instead_of_returning_nothing():
    try:
        parse_page("<html><body>nada</body></html>")
    except ValueError:
        return
    raise AssertionError("una página sin productData debe contar como fallida")


def test_brand_helpers():
    assert [brand_of(b) for b in ("La Roche Posay", "Avéne", "Cerave", "ISDIN", "Dr. Althea", None)] == ["La Roche-Posay", "Avène", "CeraVe", "ISDIN", None, None]
    assert brand_in("la-roche-posay-balsamo-cicaplast-baume-b5") == "La Roche-Posay"  # slug
    assert brand_in("Eau Thermale Avene Cicalfate 40ml") == "Avène"
    assert brand_in("Aqualia Thermal Crema Hidratante 50ml") is None and brand_in("Desodorante svrnivea") is None


def test_run_dedupes_stops_on_blocked_and_keeps_what_was_read():
    asked = []

    def fake_get(url, tries=3, text=False):
        asked.append(url)
        if len(asked) == 3:
            raise pa.Blocked("HTTP 429")
        return page()

    saved = (pa.get, pa.time.sleep, pa.log)
    pa.get, pa.time.sleep, pa.log = fake_get, lambda s: None, lambda m: None
    try:
        items = list(pa.paris("www.paris.cl"))
    finally:
        pa.get, pa.time.sleep, pa.log = saved
    assert len(asked) == 3 and len(items) == 5  # la segunda página repite los mismos productos; la tercera bloquea y se corta
    assert all("?" not in u for u in asked)  # ni ?page= ni ?sortby=: el servidor los ignora


if __name__ == "__main__":
    test_flight_chunks_are_joined_and_product_data_found()
    test_offer_price_is_the_price_and_regular_is_compare_at()
    test_no_offer_means_no_compare_at_and_brand_in_the_middle_is_removed()
    test_only_dermo_brands_are_kept_and_the_rest_counted()
    test_compare_at_only_when_greater_than_price()
    test_page_without_product_data_fails_instead_of_returning_nothing()
    test_brand_helpers()
    test_run_dedupes_stops_on_blocked_and_keeps_what_was_read()
    print("ok")
