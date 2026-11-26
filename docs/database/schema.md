# Esquema de la base

SQLite en `data/yumori.db`, fuera de git: cada PC tiene su propia base y su propio historial. El esquema y las migraciones viven en `db.py` (`SCHEMA` y `connect()`).

## Tablas
- **`listing`**: una fila por variante y tienda.
  - `id`, `store`, `ext_id`, `sku`, `title`, `variant`, `vendor`, `url` y `currency` (`CLP` o `USD`).
  - `image` (la principal) e `images`: hasta 4 URLs (`MAX_IMAGES`).
  - `description`: texto plano, máx. 3.000 caracteres.
  - `rating` y `reviews`.
  - `gtin` (desde el 2026-10-03): el código de barras en su **forma canónica de 14 dígitos** (EAN-13, UPC-12, EAN-8 y GTIN-14 con ceros a la izquierda; un UPC-12 y su EAN-13 con un 0 delante quedan iguales y se comparan por igualdad). `NULL` si la tienda no lo publica. Lo normaliza `scrapers.common.gtin()` (solo 8, 12, 13 o 14 dígitos con dígito verificador GS1 válido; descarta ceros, SKUs y ids internos). `save()` lo conserva con `COALESCE` si una lectura posterior no lo trae. Sin índice: con ~9.000 listings un cruce por `gtin` no lo necesita; agregarlo si se vuelve consulta frecuente. Lo usa `match.merge_gtin` como segundo criterio de matching (ver [matching](matching.md)).
  - `last_seen`: la hora de la última lectura que devolvió este listing.
  - `pid` (desde el 2026-10-04): el último id de producto con que el catálogo mostró este listing. Lo escribe `db.sync_aliases` al armar el catálogo (`save()` no lo toca). Sirve para detectar ids que cambian.
- **`product_alias`** (desde el 2026-10-04): `old_id` (clave), `new_id` y `ts`. Un id de producto que cambió apunta al que lo reemplaza; `Catalog.resolve` lo sigue. Sin ciclos ni cadenas largas (se aplanan). Ver [matching](matching.md#ids-estables-alias).
- **`price`**: historial desde el 2026-09-21. `listing_id`, `ts` (UTC ISO), `price` (entero: CLP o centavos de USD), `compare_at` (precio "antes", solo si es mayor que el precio) y `available`.
  - **Se inserta una fila solo si cambió el precio, el "antes" o el stock.** Por eso una fila nueva no siempre es un cambio de precio, y el historial que se muestra quita los precios repetidos seguidos.
- **`meta`**: clave → valor.
  - `scraped:<tienda>`: la última lectura con `total > 0`.
  - `run:done`: el inicio de la última corrida completa (`scrape.py` sin argumentos).
  - `yesstyle:<marca>` y `stylevana:<marca>`: la última lectura completa de esa marca. Lo usan las tiendas leídas por marca (`db.BY_BRAND`) para su rotación y para `catalog.missing()`.
  - `stylevana404:<marca>`: marca sin página en Stylevana. No se vuelve a pedir en 30 días.
- **`fx`**: `date` y `usd_clp`, el dólar observado por día (`mindicador.cl`).
- **`brand_text`** (desde el 2026-10-04): descripciones de los sitios oficiales de las marcas, solo texto y nunca precio (`source`, `ext_id`, `vendor`, `title`, `description`, `url`, `seen`). La llena `scrapers/brand_text.py` una vez por semana (`meta['brandtext:done']`); la usa `catalog.official_text` para describe.py.
- **`scrape_run`** (desde el 2026-10-03): una fila por tienda en cada corrida, con `run` (inicio de la corrida), `store`, `started`, `seconds` y `status` (`ok`, `parcial`, `vacía` o `error`), además de `items`, `changed`, `anomalies` y `error`. `python scrape.py --estado` muestra la última de cada tienda.

## Anomalías de precio
Hay una sola regla, `db.anomaly(precio, referencia, moneda)`, que usan tanto `save()` como `catalog.py`:
- **Fuera de rango:** en CLP, menos de $100 o más de $500.000; en USD, menos de US$0,50 o más de US$2.000. Ningún precio real en CLP llega a $200.000 (medido el 2026-10-03). Caso real: Vierose publicó 13 productos a $1.000.000 como relleno para "no disponible".
- **Salto brusco frente a la referencia:** una baja de más de 80% (`MAX_DROP`) o una subida de más de 300% (`MAX_RISE`). Una referencia fuera de rango no cuenta, así que corregir el relleno no es una "baja de 98%".
- **El precio 0** (regalo o muestra) no es una anomalía: se excluye aparte.
- **Qué pasa con una anomalía:**
  - `save()` guarda el precio igual, lo cuenta en `scrape_run` y anota los primeros en el registro.
  - El catálogo marca la oferta como "Precio por confirmar" (`Offer.suspect`), que no cuenta como stock, mejor precio ni oferta.

## Reglas
- **Guardado atómico:** `save(..., metadata=())` guarda listings, observaciones y marcadores de marca en una transacción. Cualquier excepción revierte todo; el registro posterior de un error no confirma escrituras parciales.
- **Migraciones:** siempre aditivas e idempotentes (`ALTER TABLE` al abrir), seguras con la base existente y sin borrar datos. Antes de algo riesgoso, copiar `data/yumori.db`.
- **Precios:** en la moneda original. La conversión a CLP se hace al mostrar, con el dólar del día. Si se guardara convertido, el historial mostraría cambios del dólar como cambios de precio.
- **Concurrencia:** `timeout=60` y transacciones cortas. `scrape.py`, `ratings.py` y el sitio leen y escriben a la vez. Un `commit` cada 50 productos en `ratings.py` llegó a bloquear la base más de 60 s y hizo fallar 5 tiendas con "database is locked".
- **Los precios 0** (regalos y muestras) no entran en la comparación.

## Estados que se derivan de los datos
- **"Sin conexión"** (`Catalog.stale`): la última lectura confirmada de la tienda es anterior al inicio de la última corrida completa (`run:done`).
- **"No aparece en la tienda"** (`catalog.missing()`): el `last_seen` del listing es anterior a la última lectura de su tienda. En las tiendas de `db.BY_BRAND` (YesStyle y Stylevana) se mira por marca y el texto es "Sin actualizar".
- **Lecturas cortadas:** el adaptador declara `ScrapeCompletion.partial`; `short_read()` conserva además la defensa del 80%, salvo que el adaptador declare `ScrapeCompletion.complete` (comprobó que leyó todo, como Novasalud contra su contador): así una tienda que se achica de verdad no queda parcial para siempre. Fuera de tiendas por marca, `last_seen` no avanza en lecturas incompletas, aunque se actualicen los precios observados. Por marca, solo un marcador de cobertura completa permite inferir faltantes; una visita parcial se registra por separado.

Ver [arquitectura del scraping](../scraping/architecture.md#estados-no-confirmados).
