"""Adaptador WooCommerce: API Store (wp-json/wc/store/v1)."""
import html
import time

from scrapers.common import brand_from_title, images_of, text_of
from scrapers.http import DELAY, get


def woocommerce(domain, extra="", delay=DELAY):
    """extra: filtros de la API que se agregan a la URL ("&category=1450", para tiendas con mucho más que cosmética). delay: pausa entre páginas."""
    # ponytail: un listing por producto; en productos variables se toma el precio base, no cada variación
    per_page, page = 100, 1
    while True:
        products = get(f"https://{domain}/wp-json/wc/store/v1/products?per_page={per_page}&page={page}{extra}")
        for p in products:
            pr = p["prices"]
            assert pr["currency_code"] == "CLP" and pr["currency_minor_unit"] == 0, pr
            price, regular = int(pr["price"]), int(pr["regular_price"])
            title = html.unescape(p["name"])
            yield dict(
                ext_id=str(p["id"]),
                sku=p["sku"] or None,
                title=title,
                variant=None,
                vendor=html.unescape(p["brands"][0]["name"]) if p.get("brands") else brand_from_title(title),
                url=p["permalink"],
                image=p["images"][0]["src"] if p["images"] else None,
                rating=float(p["average_rating"]) if int(p.get("review_count") or 0) else None,
                reviews=int(p.get("review_count") or 0) or None,
                price=price,
                compare_at=regular if regular > price else None,
                available=int(p["is_in_stock"]),
                description=text_of(" ".join(x for x in (p.get("short_description"), p.get("description")) if x)),  # el corto y el largo: la lista "incluye:" suele estar en el largo
                images=images_of(i["src"] for i in p["images"]),
            )
        if len(products) < per_page:
            return
        page += 1
        time.sleep(delay)
