"""Normalización compartida por los adaptadores."""
import html
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScrapeCompletion:
    """Valor de retorno del generador; los yield siguen siendo dicts de ofertas.

    partial: no se cubrió toda la ventana. metadata: pares para guardar junto
    a los precios, nunca desde el adaptador. *_observed rota visitas; el prefijo
    original por marca acredita únicamente listados completos.
    complete: el adaptador comprobó que leyó todo (p. ej. contra el contador de
    la tienda), así que una tienda que se achica de verdad no queda parcial por
    la regla del 80% de db.short_read().
    """
    partial: bool = False
    metadata: tuple = ()
    complete: bool = False


MAX_IMAGES = 4  # la principal + hasta 3 más: a veces la primera es la portada de la marca y no se ve el producto


def images_of(urls):
    """Lista de URLs -> JSON con hasta MAX_IMAGES distintas (o None si no hay)."""
    seen = []
    for u in urls:
        if u and u not in seen:
            seen.append(u)
    return json.dumps(seen[:MAX_IMAGES]) if seen else None


def text_of(fragment, limit=3000):
    """HTML de una descripción -> texto plano corto (sirve para saber qué contiene un pack)."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))
    return " ".join(text.split())[:limit] or None


def gtin(value):
    """Código de barras (EAN-13, UPC-12, EAN-8 o GTIN-14) -> forma canónica de 14 dígitos con ceros a la izquierda, o None.
    Con la forma canónica un UPC-12 y su EAN-13 con un 0 delante son el mismo código y se comparan por igualdad.
    Se rechaza lo que no tenga 8/12/13/14 dígitos, sea todo ceros o no pase el dígito verificador GS1 (SKUs e ids internos)."""
    s = re.sub(r"[ -]", "", str(value or ""))
    if not s.isascii() or not s.isdigit() or len(s) not in (8, 12, 13, 14) or not int(s):
        return None
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(s[:-1])))
    return s.zfill(14) if (10 - total % 10) % 10 == int(s[-1]) else None


def brand_from_title(title):
    """Tiendas cuya API no trae marca (Vierose) la ponen al final del título: "Heartleaf 88 Serum – JMsolution" -> "JMsolution"."""
    m = re.search(r"\s[–—-]\s+([^–—-]{2,32})$", title)
    brand = m.group(1).strip() if m else ""
    return brand if brand and not brand[0].isdigit() and len(brand.split()) <= 3 else None  # "– 30 ml" o frases largas no son marcas


def short_title(name, brand):
    """Unnie: "Nombre (Marca) - 50 ml Descripción en español" -> "Nombre 50 ml" (para que crucen con otras tiendas)."""
    if brand and f"({brand})" in name:
        head, tail = name.split(f"({brand})", 1)
        size = re.search(r"[0-9]+(?:[.,][0-9]+)?\s?(?:ml|g|gr)\b", tail, re.I)
        return " ".join(f"{head.strip()} {size.group(0) if size else ''}".split())
    return name
