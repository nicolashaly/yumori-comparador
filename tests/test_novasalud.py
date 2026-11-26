import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import scrapers.novasalud as ns
from scrapers.novasalud import clean_title, parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "novasalud_listing.html"  # 7 tarjetas reales: oferta, agotado, marca solo en la URL, sin marca, perfume


def page():
    return FIXTURE.read_text(encoding="utf-8")


def test_offer_card_has_price_compare_at_and_counter():
    items, dropped, counter = parse_listing(page())
    assert counter == (1, 36, 292) and dropped == 2  # el perfume de Agatha y el agua micelar sin marca
    a = items[0]
    assert (a["ext_id"], a["sku"], a["vendor"], a["currency"], a["available"], a["gtin"], a["card_price"]) == ("5949", "5949", "Eucerin", "CLP", 1, None, None)
    assert a["price"] == 17058 and a["compare_at"] == 26243  # finalPrice y oldPrice ("Precio normal")
    assert a["url"] == "https://www.novasalud.cl/dispositivos-medicos/eucerin-anti-pigment-15-ml-contorno-ojos"
    assert a["image"].startswith("https://") and a["images"].startswith("[")


def test_brand_comes_from_the_url_when_the_title_has_none_and_sold_out_is_kept_unavailable():
    b = parse_listing(page())[0][1]
    assert (b["title"], b["vendor"], b["available"], b["price"], b["compare_at"]) == ("Aqualia Thermal Crema Hidratante 50ml", "Vichy", 0, 25900, None)  # slug: vichy-50ml-...


def test_seo_filler_is_cut_after_the_size_but_a_size_after_the_dash_is_kept():
    assert clean_title("Cerave Control Cleanse 236ml - Limpiador Facial") == "Cerave Control Cleanse 236ml"
    assert clean_title("Eucerin Kids Protector Solar FPS50+ - 400ml") == "Eucerin Kids Protector Solar FPS50+ - 400ml"
    assert clean_title("Vichy Liftactiv Supreme Noche 50ml: Crema Antienvejecimiento") == "Vichy Liftactiv Supreme Noche 50ml"
    assert clean_title("Ceraderm Gel Hidrante de Rostro 140ml - Nova Salud") == "Ceraderm Gel Hidrante de Rostro 140ml"
    assert clean_title("DermoBoost Hydra Gel Hidratante 50ml - NovaSalud") == "DermoBoost Hydra Gel Hidratante 50ml"
    assert clean_title("Eucerin Anti-Pigment Crema Facial de Noche 50ml") == "Eucerin Anti-Pigment Crema Facial de Noche 50ml"


def test_only_dermo_brands_are_kept():
    items = parse_listing(page())[0]
    assert [i["vendor"] for i in items] == ["Eucerin", "Vichy", "CeraVe", "Eucerin", "CeraVe"]


def test_compare_at_only_when_greater_than_price():
    p = page().replace('data-price-amount="26243"', 'data-price-amount="17058"')
    assert parse_listing(p)[0][0]["compare_at"] is None


def test_run_paginates_with_p_only_waits_20s_and_stops_on_blocked():
    asked, slept = [], []

    def fake_get(url, tries=3, text=False):
        asked.append(url)
        if len(asked) == 4:
            raise ns.Blocked("HTTP 429")
        return page()  # "1-36 de 292": 9 páginas

    saved = (ns.get, ns.time.sleep, ns.log)
    ns.get, ns.time.sleep, ns.log = fake_get, slept.append, lambda m: None
    try:
        items = list(ns.novasalud("www.novasalud.cl"))
    finally:
        ns.get, ns.time.sleep, ns.log = saved
    assert asked == [ns.BASE + "/dispositivos-medicos", ns.BASE + "/dispositivos-medicos?p=2", ns.BASE + "/dispositivos-medicos?p=3", ns.BASE + "/dispositivos-medicos?p=4"]
    assert len(items) == 5 and slept == [20, 20, 20]  # las páginas repiten productos; la cuarta bloquea y se corta


if __name__ == "__main__":
    test_offer_card_has_price_compare_at_and_counter()
    test_brand_comes_from_the_url_when_the_title_has_none_and_sold_out_is_kept_unavailable()
    test_seo_filler_is_cut_after_the_size_but_a_size_after_the_dash_is_kept()
    test_only_dermo_brands_are_kept()
    test_compare_at_only_when_greater_than_price()
    test_run_paginates_with_p_only_waits_20s_and_stops_on_blocked()
    print("ok")
