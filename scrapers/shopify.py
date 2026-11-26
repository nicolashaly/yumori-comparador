"""Adaptador Shopify: products.json."""
import re
import time

from scrapers.common import gtin, images_of, text_of
from scrapers.http import DELAY, get


def shopify(domain, currency="CLP", vendor=None):
    """currency="USD" guarda centavos de dólar. vendor fuerza la marca en tiendas oficiales de una sola marca ("COSRX official" -> "COSRX")."""
    page = 1
    mult = 100 if currency == "USD" else 1
    while True:
        products = get(f"https://{domain}/products.json?limit=250&page={page}", sign=True)["products"]
        if not products:
            return
        for p in products:
            if p.get("product_type") == "FREEGIFT_HIDDEN":  # regalos ocultos de tiendas oficiales
                continue
            title = re.sub(r"^\s*\([^)]*Free Gift\s*\)\s*|_CPNP\b", "", p["title"], flags=re.I).strip()  # "($80+ Free Gift) X_CPNP" -> "X"
            for v in p["variants"]:
                price = round(float(v["price"]) * mult)
                was = round(float(v["compare_at_price"]) * mult) if v["compare_at_price"] else None
                yield dict(
                    ext_id=str(v["id"]),
                    sku=v["sku"] or None,
                    # products.json NO trae `barcode` (solo /products/<handle>.js, 1 request por producto). Algunas tiendas ponen el código
                    # de barras como SKU (¡Qué Coreana!: 513 de 519). Se exigen 12+ dígitos: un SKU interno de 8 dígitos (Nooki) pasa el
                    # verificador EAN-8 por azar (9 de 157) y no es un código.
                    gtin=gtin(v["sku"]) if len(v["sku"] or "") >= 12 else None,
                    title=title,
                    variant=None if v["title"] == "Default Title" else v["title"],
                    vendor=vendor or p["vendor"],
                    url=f"https://{domain}/products/{p['handle']}",
                    image=p["images"][0]["src"] if p["images"] else None,
                    price=price,
                    compare_at=was if was and was > price else None,  # un "antes" igual o menor al precio no es descuento (se veía "$24.900 tachado $24.900")
                    available=int(bool(v["available"])),
                    currency=currency,
                    description=text_of(p.get("body_html")),
                    images=images_of(i["src"] for i in p["images"]),
                )
        page += 1
        time.sleep(DELAY)
