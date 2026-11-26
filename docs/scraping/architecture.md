# Arquitectura del scraping

Ver también [ADR-003](../decisions/ADR-003-nunca-evadir-bloqueos.md) y la [operación diaria](../operations/daily-scraping.md).

## Piezas
- **`scrape.py`**: `STORES` (dominio → adaptador) y la corrida. YesStyle va al final a propósito: es la más lenta y puede cortarse, y no debe retrasar al resto.
  - `python scrape.py`: todas las tiendas. Al terminar escribe `meta['run:done']`.
  - `python scrape.py --diario`: igual, pero se omite si ya hubo una corrida completa ese día.
  - `python scrape.py <dominio>`: una sola tienda. No escribe `run:done`.
  - `python scrape.py --estado`: cómo fue la última lectura de cada tienda (estado, duración, productos, cambios, anomalías y error).
  - Cada tienda pasa por `scrape_store()`, que la lee, la guarda y deja una fila en `scrape_run`. Si falla, registra el error y la corrida sigue con las demás.
  - Al arrancar llama a `SetThreadExecutionState`, para que Windows no se suspenda por inactividad a media corrida.
- **`scrapers/http.py`**: `get()` con User-Agent honesto (`UA`) y pausa (`DELAY`). Ante 403 o 429 lanza `Blocked`, sin reintentos. También ante HTML donde se esperaba JSON (un desafío anti-bot con 200).
  - `TIMEOUT` es de 30 s por request.
  - `MAX_BYTES` es de 20 MB: una respuesta más grande se descarta (la más pesada normal, de YesStyle, ronda 1 MB).
  - Los demás errores se reintentan hasta 3 veces, con espera creciente.
  - `log()` escribe en `data/yumori.log`.
- **Adaptadores:** cada uno es un generador que entrega dicts con los mismos campos. Su `return ScrapeCompletion(partial, metadata)` declara cobertura incompleta y marcadores a guardar; `scrape.collect()` conserva ese return, que `list()` descartaba. Los marcadores se confirman con las ofertas en `db.save()`, nunca desde el adaptador. Los generadores antiguos que retornan `None` mantienen el contrato.
  - `scrapers/shopify.py`: `products.json`, con `currency` y `vendor` opcionales. Las tiendas oficiales en USD quitan las promos del título y omiten los regalos ocultos.
  - `scrapers/woocommerce.py`: la API `wp-json`. Guarda el resumen corto y el largo de la descripción.
  - `scrapers/jsonld.py`: datos schema.org en el HTML (`jsonld_nodes`, `jsonld_products`, `jsonld_gtin`; los usa también `ratings.py`). Tiendanube lee el listado `/productos/?page=N`. Jumpseller lee la ficha de cada producto vía su sitemap (`JUMPSELLER_DELAY` de 5 s).
  - `scrapers/yesstyle.py`: listados por marca, con parseo puro probado con `tests/fixtures/`.
  - `scrapers/stylevana.py`: listados por marca de la tienda `en_US` (USD), con parseo puro probado con `tests/fixtures/stylevana_cards.html`. Detalle y rutas en tiendas. Va justo antes de YesStyle.
  - `scrapers/sfcc.py`: Farmacias Ahumada (Salesforce Commerce Cloud). Parseo puro de los tiles `div.product-tile` con `html.parser` (`parse_listing(page)` -> ofertas, descartados por regla, ¿incompleta?), probado con `tests/fixtures/ahumada_tiles.html` y `tests/test_sfcc.py`. Lee una lista explícita de páginas `?sz=N` (nunca `start`, que veta su robots.txt) con 10 s de pausa. Detalle, reglas y filtro en tiendas.
    - **Campos de tarjeta:** además de los comunes entrega `card_price` (int o None) y `card_name` ("CMR Falabella"): el precio solo con tarjeta de la tienda. `price` es siempre el precio para todos. `db.save()` los guarda en `listing.card_price` y `listing.card_name` **sin COALESCE** (una oferta con tarjeta que termina queda en NULL) y no los lleva al historial `price`: son un dato actual y nunca cuentan como mejor precio.
  - `scrapers/fx.py`: el dólar observado, guardado cada corrida en `fx`.
- **Código de barras (`gtin`)**, medido el 2026-10-03 con 1 request por plataforma. Se normaliza con `scrapers.common.gtin()` (forma canónica de 14 dígitos, ver [el esquema](../database/schema.md)):
  - **Shopify:** `products.json` **no trae `barcode`** en las variantes (solo `/products/<handle>.js`, 1 request por producto). Las cuatro tiendas con Judge.me lo obtienen sin requests nuevos desde la página que `ratings.py` ya descarga (ver abajo). Algunas tiendas ponen el código como SKU: ¡Qué Coreana! (513 de 519). El adaptador usa el SKU si tiene 12+ dígitos y pasa el verificador. Con 8 dígitos no: los SKUs internos de Nooki (ej. `52102189`) pasan el verificador EAN-8 por azar (9 de 157). Las demás tiendas Shopify: 0 SKUs con forma de código.
  - **WooCommerce:** la Store API no trae ningún campo con GTIN (`sku` vacío o interno, `extensions` vacío). Sin código.
  - **Jumpseller (Unnie):** el JSON-LD pone el código en `productID` (ej. `8809416470016`; el `sku` es un hash). `item_from_jsonld` lo toma de `productID` y de `gtin13/gtin12/gtin8/gtin14/gtin`, en el producto o en la oferta.
  - **Tiendanube (KoryoBeauty):** el JSON-LD trae `sku` interno (`MCS0030`) y ningún campo `gtin`. Sin código.
  - **YesStyle:** las tarjetas del listado no traen código. Sin código.
  - **Farmacias Ahumada:** los tiles traen `data-pid` (id interno) y ningún código de barras, ni en la ficha. Sin código.
  - **Stylevana:** las tarjetas traen un SKU interno (`BSESCOS00006`), no un código de barras. Sin código (leer la ficha de cada producto pesa ~1 MB).
  - **Judge.me (Sokobox, Rakuen, Arumi, Moonbow), medido el 2026-10-04 con 1 página por forma:** `ratings.py` toma el GTIN del JSON-LD del producto principal (`parse_gtins()`), nunca de un regex sobre `"barcode"` (la página trae los de los recomendados). Forma por tienda:
    - **Sokobox:** `Product` con `gtin13` (y `gtin8` igual) a nivel de producto y `offers` en lista, cada una con `sku` y `?variant=<id>`. El código es el de la variante cuyo `sku` es el del `Product` (verificado con `/products/<handle>.js`: la variante "10 Unidades" no tiene código). Las demás variantes quedan sin código. 10 de 10 en la prueba.
    - **Rakuen y Arumi:** `Product` con `gtin` y una `offers` con `?variant=<id>` (producto de una variante), o `ProductGroup` con un `Product` por variante en `hasVariant`, cada uno con su `gtin` y su `?variant=`. Cada código va al listing con ese `ext_id`. Las variantes sin `gtin` quedan sin código. Rakuen publica a veces un `gtin` inventado de 14 dígitos que no pasa el verificador (ej. `17336219801206`, calcado de su id de variante): `gtin()` lo descarta. Prueba: Rakuen 9 de 10, Arumi 7 de 10 (1 URL daba 404).
    - **Moonbow:** el JSON-LD no trae ningún código. Sin código (0 de 10).
    - **Asignación:** por id de variante (`ext_id` en Shopify). Un código sin variante identificable solo se asigna si la URL tiene un único listing. Con varias variantes y sin forma de relacionarlas (varias ofertas sin `sku` coincidente) no se asigna nada. Nunca se pisa un código existente con NULL (`db.save()` ya usa `COALESCE`).
- **`db.save()`**: inserta precios solo si cambiaron y anota `last_seen`.
- **`ratings.py`**: Judge.me (Sokobox, Rakuen, Arumi y Moonbow). Además de la nota guarda el GTIN de la misma página. `--limit N` lee solo las primeras N URL de cada tienda (pruebas). Hace 1 request por producto, con su propia pausa de 5 s, y tarda ~5 horas, así que corre aparte, los domingos. Ante 403/429 corta esa tienda y continúa con otra; otros errores conservan una pausa. WooCommerce trae las valoraciones en su propia API. Loox (Nooki, Bom Beauty) y Okendo (Coreana Chile) siguen pendientes.

## Reglas (no negociables)
- Antes de agregar una tienda, revisar su robots.txt. Usar primero el JSON de la plataforma, y el HTML solo si no hay otra opción.
- User-Agent honesto. Ante 403 o 429 se deja de pedir: sin reintentos, sin cambiar de identidad y sin evadir Cloudflare ni captchas.
- Solo stdlib (`urllib`, `json`, `html.parser`). Una librería de HTML se justifica primero.
- Las rarezas de cada tienda se resuelven en su adaptador, nunca en `match.py`.
- Las pruebas usan fixtures, nunca tiendas en vivo.

## YesStyle (lecciones)
- **Qué permite su robots.txt:** bloquea su API de producto (`/rest/product/v1/full-detail-product*`), `/*/product-grid/`, las URL con coma (`/*,*`) y las búsquedas (`/*?q*`). Se permiten los listados por marca (`/en/<marca>/list.html/bpt.299_bid.<id>`, con los ids en `brand_sitemap.xml`) con paginación `?pn=`. Es Next.js renderizado en el servidor y no mostró captcha.
- **Cloudflare corta tras ~6 solicitudes por corrida:** el límite es por cantidad, no por ritmo. Con 20 s y con 45 s de pausa el corte llegó igual: del 2026-09-21 al 2026-10-05 el 429 llegó a diario en la 7.ª solicitud (sitemap + 5 marcas). **Desde el 2026-10-06 se para antes:** 4 marcas por corrida (`YESSTYLE_MAX_BRANDS`) con 90 s de pausa (`YESSTYLE_DELAY`), para no llegar nunca al bloqueo. Le da a nuestro tráfico un `cf-bot-score` bajo (22).
- **Rotación de marcas:**
  - Se leen las 40 marcas con más productos del catálogo (`YESSTYLE_TOP`), 1 página por marca (los 100 más vendidos, `YESSTYLE_MAX_PAGES`).
  - Cada corrida parte por las marcas visitadas hace más tiempo (`meta['yesstyle_observed:<marca>']`, con fallback al marcador antiguo). `yesstyle:<marca>` solo avanza si la lectura prueba cobertura completa. Stylevana usa la misma separación (`stylevana_observed`/`stylevana`) y rota dentro de su presupuesto existente. Alcanzar un límite de páginas o solicitudes no significa haber terminado una marca.
  - Las 40 quedaron cubiertas el 2026-10-02, y desde entonces se re-leen por antigüedad.
- **Títulos:** el tamaño y el nombre completo salen del slug de la URL, porque la tarjeta viene recortada. Los títulos se capitalizan y los tamaños quedan en minúscula ("30ml").
- **Precios:** sus precios en USD se mueven 1-2% de una semana a otra. Es real, no un error.

## Estados no confirmados
Ver [ADR-004](../decisions/ADR-004-honestidad-de-datos.md).
- **"Sin conexión"**: la tienda no se pudo leer en la última corrida completa (por ejemplo, `kbelleza.cl`, cuyo dominio no existe desde el 2026-09-23). Sus ofertas siguen visibles con su último precio, pero no cuentan como stock ni como mejor precio.
- **"No aparece en la tienda"**: la tienda respondió sin ese producto. En las tiendas que se leen por marca (`db.BY_BRAND`: YesStyle y Stylevana) dice "Sin actualizar", y solo se marca si su marca se leyó completa.
- **Lectura cortada:** bloqueo, páginas fallidas, cobertura limitada o señal explícita del adaptador dejan estado `parcial`, incluso si se obtuvo más del 80% del catálogo anterior. No se infieren faltantes fuera de marcas confirmadas completas. La defensa adicional `short_read()` está en [el esquema](../database/schema.md).
