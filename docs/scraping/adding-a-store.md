# Agregar una tienda

1. **Revisar el robots.txt** y anotar en tiendas qué permite y qué bloquea. Si bloquea lo que necesitamos, no se scrapea.
2. **Identificar la plataforma**: Shopify (`/products.json`), WooCommerce (`/wp-json/wc/store/products`), Tiendanube, Jumpseller u otra. Usar el JSON de la plataforma si existe y, si no, los datos schema.org (JSON-LD) del HTML.
3. **Si la plataforma ya tiene adaptador**, basta con sumar la tienda a `STORES` en `scrape.py`. Mantener YesStyle al final.
4. **Si es una plataforma nueva**, escribir `scrapers/<plataforma>.py`:
   - un generador que entregue los mismos campos que los demás adaptadores (título, marca, precio, "antes" solo si es mayor que el precio, stock, URL, imágenes, descripción, SKU y moneda);
   - que reutilice `get()` de `scrapers/http.py` y las funciones de `scrapers/common.py`, y `scrapers/jsonld.py` si la tienda usa schema.org;
   - con pausas prudentes, y que ante `Blocked` corte la tienda guardando lo ya leído;
   - con las rarezas de la tienda resueltas ahí, no en `match.py`.
5. **Prueba con fixture** en `tests/test_scrape.py` (guardar un fragmento real en `tests/fixtures/`). Nunca contra la tienda en vivo.
6. **Corrida real de una sola tienda**: `python scrape.py <dominio>`. Revisar `data/yumori.log` y que cruce con otras tiendas: `python match.py <palabras>`.
7. **Agregar su nombre visible** en `STORE_NAMES` (`catalog.py`).
8. **Documentar** en tiendas: plataforma, catálogo y cualquier rareza.
