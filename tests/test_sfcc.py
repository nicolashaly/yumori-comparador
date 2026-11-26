import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import scrapers.sfcc as sf
from db import connect, save
from scrapers.sfcc import norm_brand, parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "ahumada_tiles.html"  # 3 tiles reales: normal con "Precio normal", CMR y sin stock


def tiles():
    return FIXTURE.read_text(encoding="utf-8")


def test_normal_tile_has_sale_price_and_compare_at():
    items, dropped, more = parse_listing(tiles())
    assert len(items) == 3 and not dropped and not more
    a = items[0]
    assert (a["ext_id"], a["sku"], a["vendor"], a["currency"], a["available"], a["gtin"]) == ("65749", "65749", "Ceraderm", "CLP", 1, None)
    assert a["title"] == "Gel Hidratante Rostro 140 g"  # la marca en medio se quita (strip_brand); vendor la conserva
    assert a["price"] == 22390 and a["compare_at"] == 33499 and a["card_price"] is None  # no confunde el precio por litro ($239.279 x Lt)
    assert a["url"] == "https://www.farmaciasahumada.cl/gel-ceraderm-hidratante-rostro-140-g-65749.html"
    assert a["image"].startswith("https://") and a["images"].startswith("[")


def test_cmr_tile_price_for_everyone_is_the_price_and_card_price_goes_apart():
    b = parse_listing(tiles())[0][1]
    assert b["price"] == 17509 and b["card_price"] == 13132 and b["card_name"] == "CMR Falabella" and b["compare_at"] is None


def test_out_of_stock_tile_is_kept_unavailable():
    c = parse_listing(tiles())[0][2]
    assert c["available"] == 0 and c["price"] == 31509 and c["vendor"] == "Isispharma"


def test_compare_at_only_when_greater_than_price():
    page = tiles().replace('content="33499"', 'content="22390"')
    assert parse_listing(page)[0][0]["compare_at"] is None


def test_show_more_button_marks_the_page_incomplete():
    assert parse_listing(tiles() + '<div class="show-more w-100">')[2]


def test_brands_are_normalized():
    assert [norm_brand(b) for b in ("La Roche Posay", "La Roche-Posay", "Cerave", "Isdin", "ISDIN", " Vichy ", "Skin1004", "Apivita", None)] == [
        "La Roche-Posay", "La Roche-Posay", "CeraVe", "ISDIN", "ISDIN", "Vichy", "SKIN1004", "Apivita", None]


def test_non_cosmetics_are_dropped_by_rule_and_counted():
    page = tiles()
    ok = page.replace("Gel Ceraderm Hidratante Rostro 140 g</a>", "Gel Ceraderm Hidratante Rostro 140 g 3x2</a>")
    assert parse_listing(ok)[1] == {"pack 3x2": ["Gel Ceraderm Hidratante Rostro 140 g 3x2"]}
    for name in ("Ducray Anacaps 30 cápsulas", "Algo 500 mg x 20 comprimidos", "Xerac Ac 6,25 % X 35 Ml Solución", "Sol. Oral Hierro 2% 100 ml Solución"):
        d = parse_listing(page.replace("Gel Ceraderm Hidratante Rostro 140 g</a>", name + "</a>"))[1]
        assert list(d) == ["medicamento/suplemento"], name
    for name in ("Isdin Serum Isdinceutics Instant Flash x 1 ampolla 2 mL", "Booster Eucerin Vitamina C 8Ml", "Shampoo Elizavecca Colágeno 500ml",
                 "Set Cetaphil 3 x 100 mL", "Crema 30 g"):
        assert not parse_listing(page.replace("Gel Ceraderm Hidratante Rostro 140 g</a>", name + "</a>"))[1], name


def test_category_whitelist():
    page = tiles()
    other = page.replace("Dermocosm&eacute;tica,Tipos de Piel", "Vitaminas y Suplementos,Tipos de Piel")
    assert other != page and list(parse_listing(other)[1]) == ["categoría Vitaminas y Suplementos"]
    assert not parse_listing(page.replace("Dermocosm&eacute;tica,Tipos de Piel", "Promociones,Tipos de Piel"))[1]
    assert not parse_listing(page.replace("Dermocosm&eacute;tica,Tipos de Piel", "Belleza,Tipos de Piel"))[1]


def test_card_price_is_overwritten_by_null_when_the_offer_ends():
    db = connect(str(Path(tempfile.mkdtemp()) / "t.db"))
    item = parse_listing(tiles())[0][1]
    save(db, "x.cl", [item])
    assert db.execute("SELECT card_price, card_name FROM listing").fetchone() == (13132, "CMR Falabella")
    save(db, "x.cl", [dict(item, card_price=None, card_name=None)])
    assert db.execute("SELECT card_price, card_name FROM listing").fetchone() == (None, None)
    assert db.execute("SELECT count(*) FROM price").fetchone()[0] == 1  # la tarjeta no entra al historial


def test_run_stops_on_blocked_keeping_what_was_read_and_dedupes():
    asked = []

    def fake_get(url, tries=3, text=False):
        asked.append(url)
        if len(asked) == 3:
            raise sf.Blocked("HTTP 429")
        return tiles()

    saved = (sf.get, sf.time.sleep, sf.log)
    sf.get, sf.time.sleep, sf.log = fake_get, lambda s: None, lambda m: None
    try:
        items = list(sf.sfcc("www.farmaciasahumada.cl"))
    finally:
        sf.get, sf.time.sleep, sf.log = saved
    assert len(asked) == 3 and len(items) == 3  # la segunda página repite los mismos productos; la tercera bloquea y se corta
    assert all("start=" not in u and "?sz=" in u for u in asked)


def test_brand_in_the_middle_of_the_title_is_removed():
    # caso real: 411 de 749 títulos de Ahumada traen la marca en medio, y el sitio la antepone ("Eucerin Serum Eucerin Hyaluron...")
    from scrapers.sfcc import strip_brand
    assert strip_brand("Serum Eucerin Hyaluron Filler Epigenetic 30 mL", "Eucerin") == "Serum Hyaluron Filler Epigenetic 30 mL"
    assert strip_brand("Mascarilla Centella Watergel Skin1004", "SKIN1004") == "Mascarilla Centella Watergel"
    assert strip_brand("Agua Thermal La Roche Posay Pieles Sensibles 150Gr", "La Roche-Posay") == "Agua Thermal Pieles Sensibles 150Gr"
    assert strip_brand("Eucerin Aquaphor Pomo 55 mL", "Eucerin") == "Eucerin Aquaphor Pomo 55 mL"  # al inicio lo resuelve catalog.clean()
    assert strip_brand("Crema Hidratante 453 grs", "") == "Crema Hidratante 453 grs"
    assert strip_brand("Eau Thermale Avène Loción Micelar 400 ml", "Avène") == "Eau Thermale Loción Micelar 400 ml"  # con tilde


if __name__ == "__main__":
    test_brand_in_the_middle_of_the_title_is_removed()
    test_normal_tile_has_sale_price_and_compare_at()
    test_cmr_tile_price_for_everyone_is_the_price_and_card_price_goes_apart()
    test_out_of_stock_tile_is_kept_unavailable()
    test_compare_at_only_when_greater_than_price()
    test_show_more_button_marks_the_page_incomplete()
    test_brands_are_normalized()
    test_non_cosmetics_are_dropped_by_rule_and_counted()
    test_category_whitelist()
    test_card_price_is_overwritten_by_null_when_the_offer_ends()
    test_run_stops_on_blocked_keeping_what_was_read_and_dedupes()
    print("ok")
