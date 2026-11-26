# Arquitectura: visión general

Yumori es un monolito pequeño en Python con solo la biblioteca estándar. Corre en el PC del usuario: no hay API JSON aparte, colas, CI ni despliegue. Ver [ADR-001](../decisions/ADR-001-stack-stdlib-sqlite.md).

## Flujo de datos
```text
Tarea programada (Windows) ─► scrape.py ─► scrapers/<plataforma>.py ─► db.save() ─► data/yumori.db (SQLite)
                                                                                         │
navegador ◄─ server.py (HTML en el servidor) ◄─ catalog.py (catálogo en memoria) ◄─ match.py + describe.py
```

1. **Extracción** (`scrapers/`): un adaptador por plataforma descarga y normaliza a un dict común: título, marca, precio, precio "antes", stock, URL, imágenes, descripción, SKU y moneda. La descarga está en `scrapers/http.py` (`get()`, `Blocked`, `log()`).
2. **Persistencia** (`db.py`): `connect()` crea la base y aplica las migraciones. `save()` inserta un precio solo si cambió.
3. **Matching** (`match.py`): agrupa listings de distintas tiendas en un producto. Ver [matching](../database/matching.md).
4. **Catálogo** (`catalog.py`): arma en memoria `Product`, `Offer` e `IntlOffer`. Calcula mejor precio, estados no confirmados (`stale`, `missing`), ofertas, filtros y conteos. Se reconstruye si cambió la base, con un mínimo de 60 s entre reconstrucciones.
5. **Atributos** (`describe.py`): categoría, tipo, tipo de piel, compuestos, contenido de packs y una descripción propia por plantillas.
6. **Sitio** (`server.py` + `static/`): renderiza HTML en el servidor y escapa todo con `html.escape`. Un solo script propio (`static/app.js`). Los textos legales están en `legal.py`.

## Módulos
| Archivo | Qué hace |
|---|---|
| `scrape.py` | Punto de entrada del scraping: `STORES` (dominio → adaptador) y la corrida (`--diario`, una tienda por argumento, `run:done`). |
| `scrapers/http.py` | `get()` con User-Agent honesto, `Blocked` ante 403/429 y `log()`. |
| `scrapers/common.py` | Normalización compartida: imágenes, texto, marca desde el título y título corto. |
| `scrapers/shopify.py`, `woocommerce.py`, `jsonld.py` (Tiendanube y Jumpseller), `yesstyle.py`, `fx.py` | Adaptadores por plataforma y dólar observado. |
| `ratings.py` | Valoraciones de Judge.me, un job semanal aparte. |
| `db.py` | Ruta de la base, esquema, migraciones, `save()`, `short_read()`, `done_today()` y la regla única de anomalías de precio (`anomaly()`). |
| `match.py` | Clave de producto, `is_pack()`, carga y agrupación. |
| `catalog.py` | Catálogo en memoria, búsqueda (`_match()` es la única regla de filtrado), conteos y ofertas. |
| `describe.py` | Atributos y descripción propia. |
| `server.py` | Rutas y HTML. |
| `legal.py` | Privacidad, términos y cookies. |
| `tests/` | Pruebas stdlib (`python tests/run.py`) y `fixtures/`. |

## Contratos entre capas
- **`Catalog` / `Product` → `server.py`:** un campo nuevo o cambiado se coordina entre los dueños de datos y de frontend en la misma entrega.
- **Adaptador → `db.save()`:** todos los adaptadores entregan los mismos campos. Las rarezas de cada tienda se resuelven en su adaptador, nunca en `match.py`.
- **`_match()` es la única regla de filtrado:** la usan `search()`, `counts()` y `Catalog.deals`. Así los números que muestra el sitio nunca contradicen la lista que se ve.
- **Secciones (dermocosmética):**
  - `Product.section` es `"asiatica"` o `"dermocosmetica"`, decidida por **marca** (`catalog.section_of`): una marca de `DERMO_BRANDS` es siempre dermocosmética; si no, es asiática cuando alguna tienda que no es farmacia ni de dermocosmética (`PHARMACY_STORES`: Ahumada, Dermotienda, EcoFarmacias, Novasalud y Farmaloop) vende la marca; Paris y DBS son tiendas generales y sus adaptadores solo leen marcas de la lista (y asiáticas, DBS); si solo la venden farmacias, es dermocosmética. Así SKIN1004 en Ahumada entra a la comparación asiática y suma un precio chileno.
  - `_match`, `search`, `counts`, `facets`, `suggest`, `top_brands`, `top_spread` y `drops` reciben `section`, **por defecto `"asiatica"`**: sin pasarlo dan lo mismo que antes de la sección (Explorar, banner de ofertas, `/tiendas`). `section="dermocosmetica"` pide la otra y `""` junta las dos.
  - `Catalog.brands`, `stores`, `intl_stores` e `intl_matched` son solo de la sección asiática; la otra tiene `derm_brands` y `derm_stores`. `section_counts` cuenta productos y packs por sección. `len(cat.products)` incluye las dos.
  - Un id de producto no depende de la sección.
- **Precio con tarjeta:** `Offer.card_price` y `Offer.card_name` (de `listing.card_price` y `card_name`, dato actual, sin historial). No cuentan nunca para `min_price`, el empate, `display_price`, `drop`, `deals` ni los filtros de precio. `Product.card_offers` lista las ofertas con stock cuyo precio con tarjeta es menor que su precio normal, de menor a mayor (a igualdad, tienda alfabética).

## El id de producto
El id es un hash de la clave de `match.py`. Si cambian las reglas de matching (`key_of` y sus listas), cambian los ids, y los usuarios pierden los favoritos guardados en su navegador. Antes y después de cualquier cambio de matching hay que medir con la base real cuántos ids cambian. Ver [ADR-002](../decisions/ADR-002-matching-por-texto.md).

## Rendimiento
- El catálogo tiene unos 9.500 productos y se arma en memoria en ~4 s.
- Una página tarda ~35 ms.
- Si crece mucho, primero se agregan índices y consultas, y después se evalúa cambiar de motor (Postgres al publicar).
