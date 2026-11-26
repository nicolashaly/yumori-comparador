import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

from scrapers.stylevana import brand_url, parse_listing, slug_of

FIXTURE = Path(__file__).parent / "fixtures" / "stylevana_cards.html"  # encabezado y 3 tarjetas reales de la página de marca de COSRX


def test_parse_listing():
    items, total = parse_listing(FIXTURE.read_text(encoding="utf-8"))
    assert total == 251 and len(items) == 3
    a = items[0]
    assert (a["ext_id"], a["vendor"], a["currency"], a["available"], a["sku"]) == ("10777", "COSRX", "USD", 1, "BSESCOS00006")
    assert a["title"] == "COSRX Advanced Snail 96 Mucin Power Essence 100ml"
    assert a["price"] == 1750 and a["compare_at"] == 2500  # centavos de USD
    assert a["url"] == "https://www.stylevana.com/en_US/cosrx-advanced-snail-96-mucin-power-essence-100ml10777.html"
    assert a["image"].startswith("https://") and a["image"].endswith(".png")
    assert items[1]["title"].endswith("(2ea) Set") and items[1]["price"] == 3499  # float: 34.99 * 100 no debe dar 3498


def test_vendor_given_by_the_caller_wins_over_the_page_title():
    assert {i["vendor"] for i in parse_listing(FIXTURE.read_text(encoding="utf-8"), "Cosrx")[0]} == {"Cosrx"}


def test_compare_at_only_when_greater_and_free_items_skipped():
    page = FIXTURE.read_text(encoding="utf-8")
    same = page.replace('data-price-amount="25"\n        data-price-type="rrpPrice"', 'data-price-amount="17.5"\n        data-price-type="rrpPrice"')
    assert same != page and parse_listing(same)[0][0]["compare_at"] is None
    free = page.replace('data-price-amount="17.5"', 'data-price-amount="0"')
    assert [i["ext_id"] for i in parse_listing(free)[0]].count("10777") == 0


def test_n_units_title_becomes_a_set():
    page = FIXTURE.read_text(encoding="utf-8").replace("Essence - 100ml", "Essence Twin Pack 100ml*2ea")
    assert parse_listing(page)[0][0]["title"] == "COSRX Advanced Snail 96 Mucin Power Essence Twin Pack 100ml (2ea) Set"


def test_run_reads_whole_brands_within_budget_and_skips_missing_ones():
    import tempfile
    import urllib.error

    import scrapers.stylevana as sv
    from db import connect, save
    from scrape import collect

    db = connect(str(Path(tempfile.mkdtemp()) / "t.db"))
    save(db, "x.cl", [dict(ext_id=str(i), sku=None, title="t", variant=None, vendor=v, url="u", price=1000, compare_at=None, available=1)
                      for v, n in (("Big", 5), ("Gone", 4), ("Small", 3), ("Tiny", 2)) for i in range(n) for i in [f"{v}{i}"]])
    pages = {"big": 4, "small": 1, "tiny": 1}  # marca -> páginas que tiene Stylevana
    asked = []

    def fake_get(url, tries=3, text=False):
        slug = url.split("/brands/")[1].split(".html")[0]
        pn = int(url.rsplit("p=", 1)[1])
        asked.append((slug, pn))
        if slug not in pages:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        card = ''.join('data-container="product-grid" data-product-id="%s" data-name="B - n%s" data-price-amount="5" data-price-type="finalPrice"'
                       % (f"{len(slug)}{pn}{i:02}", f"{slug}{pn}{i}") for i in range(36))
        return ('data-ui-id="page-title-wrapper" >%s<' % slug) + card + 'of <span class="toolbar-number">%d</span> results' % (pages[slug] * 36)

    saved = (sv.DB, sv.get, sv.time.sleep, sv.STYLEVANA_MAX_REQUESTS, sv.log)
    sv.DB, sv.get, sv.time.sleep, sv.STYLEVANA_MAX_REQUESTS, sv.log = db.execute("PRAGMA database_list").fetchone()[2], fake_get, lambda s: None, 6, lambda m: None
    try:
        items, completion = collect(sv.stylevana("www.stylevana.com"))
    finally:
        sv.DB, sv.get, sv.time.sleep, sv.STYLEVANA_MAX_REQUESTS, sv.log = saved
    # Big: 4 páginas (cabe en 6); Gone: 404 (1 solicitud); Small: 1 página -> 6 solicitudes, Tiny queda fuera del tope
    assert asked == [("big", 1), ("big", 2), ("big", 3), ("big", 4), ("gone", 1), ("small", 1)]
    assert len(items) == 180 and completion.partial
    meta = dict(db.execute("SELECT key, value FROM meta"))
    assert not any(k.startswith("stylevana") for k in meta)
    save(db, "www.stylevana.com", items, metadata=completion.metadata)
    meta = dict(db.execute("SELECT key, value FROM meta"))
    assert {"stylevana:big", "stylevana:small", "stylevana404:gone"} <= set(meta) and "stylevana:tiny" not in meta
    db.close()


def test_urls_and_slugs():
    assert brand_url("cosrx", 2) == "https://www.stylevana.com/en_US/brands/cosrx.html?product_list_limit=36&p=2"
    assert [slug_of(v) for v in ("Beauty of Joseon", "Rom&nd", "Dr. Althea", "AMPLEN")] == ["beauty-of-joseon", "romand", "dr-althea", "ample-n"]


if __name__ == "__main__":
    test_parse_listing()
    test_vendor_given_by_the_caller_wins_over_the_page_title()
    test_compare_at_only_when_greater_and_free_items_skipped()
    test_n_units_title_becomes_a_set()
    test_run_reads_whole_brands_within_budget_and_skips_missing_ones()
    test_urls_and_slugs()
    print("ok")
