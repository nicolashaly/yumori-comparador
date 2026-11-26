import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import scrapers.nextdata as nd

FIX = Path(__file__).parent / "fixtures"  # productos reales recortados de Falabella (marca) y Farmaloop (categoría), del 2026-10-04
TODAY = date(2026, 10, 4)


def fal():
    return (FIX / "falabella_brand.html").read_text(encoding="utf-8")


def farma():
    return (FIX / "farmaloop_category.html").read_text(encoding="utf-8")


def edit(page, fn):
    """Cambia el JSON embebido de la página de prueba."""
    m = nd.NEXT_DATA.search(page)
    d = json.loads(m.group(1))
    fn(d["props"]["pageProps"])
    return page[:m.start(1)] + json.dumps(d, ensure_ascii=False) + page[m.end(1):]


def test_falabella_keeps_only_falabella_regular_products():
    items, dropped, pages = nd.parse_falabella(fal())
    assert pages == 4  # 166 productos de a 48
    assert len(items) == 4 and {i["currency"] for i in items} == {"CLP"}
    assert dropped == {"pack": ["Pack Rutina Diaria Hidratante 250grs + Limpiadora 237ml", "Pack Cuidado Básico Piel Sensible"],
                       "vendedor de terceros": ["Duo Sensibio H2O agua micelar para Piel sensible"]}


def test_falabella_prices_brand_and_title():
    items = {i["vendor"]: i for i in nd.parse_falabella(fal())[0]}
    e = items["Eucerin"]  # EUCERIN en mayúsculas -> Eucerin
    assert (e["price"], e["compare_at"], e["card_price"], e["available"], e["gtin"]) == (23990, None, None, 1, None)
    assert e["url"].startswith("https://www.falabella.com/falabella-cl/product/") and e["images"].startswith("[")
    a = items["Apivita"]  # internetPrice + normalPrice tachado
    assert (a["price"], a["compare_at"]) == (60790, 75900)
    assert items["La Roche-Posay"]["title"] == "Hyalu B5 Serum Suractivado 30 ml"  # la marca al final del título se quita
    assert items["Uriage"]["title"] == "Desodorante Power 3 50ml"  # Falabella corta el título con un "de" colgando


def test_falabella_compare_at_only_when_greater_and_event_price_counts():
    def flat(pp):
        for r in pp["results"]:
            if r["prices"][0]["type"] == "internetPrice" and len(r["prices"]) == 2:
                r["prices"][1]["price"] = [r["prices"][0]["price"][0]]
            elif len(r["prices"]) == 1:
                r["prices"][0]["type"] = "eventPrice"
    items = {i["vendor"]: i for i in nd.parse_falabella(edit(fal(), flat))[0]}
    assert items["Apivita"]["compare_at"] is None and items["Eucerin"]["price"] == 23990


def test_falabella_page_without_products_or_template():
    assert nd.parse_falabella(edit(fal(), lambda pp: pp.update(results=None)))[0] == []
    try:
        nd.parse_falabella("<html>otra plantilla</html>")
        raise AssertionError("debía fallar")
    except ValueError:
        pass


def test_falabella_run_paginates_stops_on_blocked_and_dedupes():
    asked = []

    def fake_get(url, tries=3, text=False):
        asked.append(url)
        if len(asked) == 6:
            raise nd.Blocked("HTTP 403")
        return fal()  # siempre trae 166 productos (4 páginas) y los mismos ids

    saved = (nd.get, nd.time.sleep, nd.log)
    nd.get, nd.time.sleep, nd.log = fake_get, lambda s: None, lambda m: None
    try:
        items = list(nd.falabella("www.falabella.com"))
    finally:
        nd.get, nd.time.sleep, nd.log = saved
    assert asked[:4] == [nd.FALABELLA + "EUCERIN", nd.FALABELLA + "EUCERIN?page=2", nd.FALABELLA + "EUCERIN?page=3", nd.FALABELLA + "EUCERIN?page=4"]
    assert asked[4] == nd.FALABELLA + "LA%20ROCHE%20POSAY" and len(asked) == 6 and len(items) == 4  # la 6.ª bloquea y se corta


def test_farmaloop_lot_price_ignores_lots_close_to_expiry():
    items, dropped = nd.parse_farmaloop(farma(), TODAY)
    by = {i["sku"]: i for i in items}
    a = by["18291"]  # tres lotes a 9.500 que vencen en 2028: precio del lote, normal 13.990
    assert (a["price"], a["compare_at"], a["available"], a["currency"], a["gtin"]) == (9500, 13990, 1, "CLP", "04005800223136")
    assert a["url"].startswith("https://www.farmaloop.cl/products/") and a["url"].endswith("/") and a["image"].startswith("https://")
    # Avène: único lote vence el 2027-01-01 (3 meses): no es el mismo producto que en otra tienda, no se ofrece
    assert "159381" not in by and dropped["vence en menos de 6 meses"] == ["Avene Emulsión Hidratante Antirojeces Día SPF30 40 ml."]
    assert "159381" in {i["sku"] for i in nd.parse_farmaloop(farma(), date(2026, 4, 1))[0]}  # con otra fecha de hoy sí cuenta


def test_farmaloop_drops_medicines_and_prescriptions_and_keeps_out_of_stock():
    items, dropped = nd.parse_farmaloop(farma(), TODAY)
    assert dropped["receta"] == ["Tricoxane 2% Con Válvula"]
    assert dropped["medicamento"] == ["Medicasp Ketoconazol 1% Shampoo Anticaspa 130ml"]
    d = {i["sku"]: i for i in items}["159565"]  # Ducray sin stock: se guarda con el precio normal y no disponible
    assert (d["available"], d["price"], d["compare_at"], d["vendor"], d["title"]) == (0, 18190, None, "Ducray", "Ducray Kelual DS Shampoo Antirecidivas 100ml")  # la marca al inicio la quita catalog.clean()


def test_farmaloop_brand_from_name_or_laboratory_and_title_without_brand():
    by = {i["sku"]: i for i in nd.parse_farmaloop(farma(), TODAY)[0]}
    assert by["18291"]["vendor"] == "Eucerin" and by["18291"]["title"] == "Aquaphor Ungüento Reparador 55 ml"  # "– Eucerin" al final
    assert by["138455"]["vendor"] == "Eucerin" and by["138455"]["title"] == "Eucerin Aquaphor Spray Corporal Reparador 150ml"  # al inicio: catalog.clean()
    assert by["159477"]["vendor"] is None  # CeraVe no aparece ni en el nombre ni en el laboratorio: sin marca, no se inventa


def test_farmaloop_run_reads_seven_pages_and_dedupes():
    asked = []

    def fake_get(url, tries=3, text=False):
        asked.append(url)
        return farma()

    saved = (nd.get, nd.time.sleep, nd.log)
    nd.get, nd.time.sleep, nd.log = fake_get, lambda s: None, lambda m: None
    try:
        items = list(nd.farmaloop("www.farmaloop.cl"))
    finally:
        nd.get, nd.time.sleep, nd.log = saved
    assert len(asked) == 7 and len({i["ext_id"] for i in items}) == len(items)
    assert all("/productos" not in u and "?" not in u for u in asked)  # nunca una ficha ni un parámetro de página


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
