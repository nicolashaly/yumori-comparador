import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

from pathlib import Path

from scrapers.yesstyle import brand_pages, brand_url, parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "yesstyle_cards.html"  # 3 tarjetas reales de una página de marca


def test_parse_listing():
    items = parse_listing(FIXTURE.read_text(encoding="utf-8"))
    assert len(items) == 3
    a = items[0]
    assert (a["vendor"], a["currency"], a["available"]) == ("Anua", "USD", 1)
    assert a["price"] == 2214 and a["compare_at"] == 2331  # centavos de USD
    assert a["title"].endswith("Serum 30ml") and a["title"].startswith("Anua Azelaic") and a["url"].startswith("https://www.yesstyle.com/en/anua-")
    assert a["image"].startswith("https://")


def test_other_currency_is_skipped():
    card = '<a class="itemContainer" href="/en/x-cream-50ml/info.html/pid.1"><b>€ 10,00</b></a>'
    assert parse_listing(card) == []


def test_brand_pages():
    xml = ("<loc>https://www.yesstyle.com/en/beauty-of-joseon/list.html/bpt.299_bid.320196</loc>"
           "<loc>https://www.yesstyle.com/en/anua/list.html/bpt.299_bid.325602</loc><loc>https://otro.com/x</loc>")
    pages = brand_pages(xml)
    assert pages["beautyofjoseon"] == ("beauty-of-joseon", "bpt.299_bid.320196") and len(pages) == 2
    assert brand_url("anua", "bpt.299_bid.325602", 2) == "https://www.yesstyle.com/en/anua/list.html/bpt.299_bid.325602?pn=2"


if __name__ == "__main__":
    test_parse_listing()
    test_other_currency_is_skipped()
    test_brand_pages()
    print("ok")
