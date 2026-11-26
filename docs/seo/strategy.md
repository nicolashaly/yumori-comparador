# SEO

## Hecho (2026-10-02)
Todo sale de `server.py`: `head_meta()` arma el `<head>` y cada página le pasa lo suyo.
- **Meta description, canonical, Open Graph y `twitter:card`** en cada página. La descripción se recorta a ~158 caracteres (`clip()`) y `og:image` es la foto del producto.
- **URL absolutas:** salen de `YUMORI_URL` (**definirla al publicar**, ej. `https://yumori.cl`). Sin ella se usa el Host de la solicitud (`REQ.base`, por hilo), que en local es `http://127.0.0.1:8000`.
- **Títulos con intención de búsqueda:**
  - producto: "Marca Nombre [variante] Tamaño: precio en Chile · Yumori" (`full_name()`);
  - marca y categoría: "X: precios en Chile · Yumori".
- **Qué se indexa:** inicio, `/explorar` y `/packs` sin filtros, por marca, por categoría y su paginación, los productos, `/marcas`, `/tiendas` y las páginas legales.
  - Búsquedas, filtros, orden, marcas inexistentes y listados vacíos llevan `noindex, follow`: son combinaciones casi infinitas del mismo contenido, pero sus enlaces a productos sí se siguen.
  - `/favoritos` y el 404 también llevan `noindex`.
- **Dermocosmética** (2026-10-04): `/dermocosmetica` y `/dermocosmetica/packs` siguen la misma regla que `/explorar` y `/packs` (por marca, categoría y página son indexables; búsquedas, filtros, orden y vacío llevan `noindex, follow`). Sin productos no entran al sitemap.
- **`/robots.txt`** bloquea `/fragmento/` y `/favoritos`. **`/sitemap.xml`** tiene ~8.200 URL; el `lastmod` de los productos es la última revisión de precios.
- **JSON-LD** (`ld_json()`, escapa `<`; la CSP no lo bloquea porque no se ejecuta):
  - `WebSite` en el inicio;
  - `Product` y `BreadcrumbList` en cada producto;
  - `AggregateOffer` (CLP, mínimo, máximo, cantidad) **solo con tiendas chilenas con stock confirmado**: nunca la estimación del extranjero ni una oferta sin conexión o que ya no aparece en la tienda;
  - **sin `aggregateRating`, a propósito:** las notas son de las tiendas y Google no admite reseñas tomadas de otros sitios.
- **Nombres repetidos (`Product.variant`):** 1.050 productos, sobre todo tonos de maquillaje ("Ink Velvet" en 30 tonos), se llamaban igual en el sitio y para Google.
  - Si dos productos comparten marca, nombre, tamaño, mini y pack, cada uno muestra la variante de la tienda que da el nombre ("001 Good Brick"; "Default Title" se ignora).
  - Se ve en la card, las sugerencias, el subtítulo, el título y la descripción.
  - Quedan 16 repetidos: el mismo producto partido en dos grupos por el matching (ej. Dynasty Cream 100 ml). Es un tema de matching, no de SEO.
- `tests/test_compliance.py` permite `<link rel="canonical">` absoluto: es del propio sitio y no carga nada de terceros.

## Next.js (2026-10-17)
Producción sirve Next (Caddy → `api:3000`), así que el SEO se portó ahí con las mismas reglas que Python (`frontend/lib/seo.ts`).
- **Interruptor:** `YUMORI_URL` (ej. `https://yumori.cl`, en el `.env` de la EC2; `docker-compose.yml` lo pasa a `web`). Sin ella el sitio sigue siendo piloto: `noindex`, `robots.txt` con `Disallow: /` y sitemap vacío. Con ella: indexable, `metadataBase`, canónicas absolutas, `robots.txt` con `Sitemap:`.
- **Search Console:** `GOOGLE_SITE_VERIFICATION=<token>` agrega `<meta name="google-site-verification">`.
- **Producto:** título "Marca Nombre Tamaño: precio en Chile", descripción, canónica, Open Graph/Twitter con imagen, JSON-LD `Product` (AggregateOffer solo con tiendas chilenas con stock; sin `aggregateRating`) y `BreadcrumbList`. Inicio: `WebSite`.
- **Listados** (`listingMeta`): indexables solo con `marca`, `cat` y `pagina`; el resto lleva `noindex, follow` y canónica limpia. `/favoritos`: `noindex`.
- **Sitemap** (`app/sitemap.ts`): páginas, categorías, marcas, evento vigente y todos los productos, vía `/api/v1/sitemap` (solo ids). Las páginas legales entran cuando `LEGAL_VISIBLE` sea true.

## Revisión del 2026-11-24
- Search Console: 310 páginas indexadas y 12.094 sin indexar (de ~1.800 indexadas el 2026-10-22 a ~310 desde el 2026-10-24). Avisos: "Google eligió otra canónica", noindex, 404, redirección, y Product sin `offers`/`review`/`aggregateRating` (crítico para fragmentos de producto). 15 clics en 28 días; GA: 127 usuarios del 20-oct al 16-nov.
- **Corregido:** el port a Next dejó a todos los listados por marca y categoría (~1.100 URL del sitemap) con el mismo título y descripción. `listingMeta` los nombra ahora ("COSRX: precios en Chile", "Eucerin (dermocosmética): …") y pone noindex a una marca o categoría inexistente. El aviso de cookies ya no enlaza `/cookies` mientras `LEGAL_VISIBLE` sea false (daba 404).
- **Product sin stock en Chile:** ya no se emite el JSON-LD `Product` (solo `BreadcrumbList`). Sin offers era un error crítico de Google, y un `OutOfStock` con el último precio mostraría un precio no confirmado.
- **Motivos de no indexación (Search Console, 2026-11-25):** 8.552 "Discovered – currently not indexed", 1.691 "Crawled – currently not indexed", 1.697 alternativas con canónica (filtros, `?rango=`, alias: esperado), 125 noindex (esperado), 25 "Google eligió otra canónica", 3 redirecciones y 1 404. El grueso es prioridad de rastreo (sitio nuevo, poca autoridad, respuestas de 0,7–1,8 s), no un error técnico.
- **Sitemap (2026-11-25):** solo productos que alguna tienda chilena aún lista (`Product.listed_in_chile`, con o sin stock y aunque esté sin conexión: ~7.300 de ~10.600), y `lastmod` por producto = día de su último cambio de precio, stock o precio tachado (`api.sitemap_products`). Se descartó "solo con stock": una tienda sin conexión marca todo sin stock, y el sitemap habría subido y bajado con cada bloqueo (p. ej. las 11 Shopify pausadas del 22-oct al 24-nov) y cada quiebre. Las fichas que salen siguen en el sitio, sin noindex. El sitemap de Python (`server.py`) no se cambió: producción sirve Next.
- **Error corregido:** el título de un listado por marca se arrastraba a otras visitas (`listingMeta` reasignaba sus parámetros); estuvo en producción unas horas del 2026-11-25 y se corrigió en el PR #31.
- **Abierto:** páginas legales ocultas con GA activo; sin `og:image` fuera de productos; listados vacíos siguen indexables.

## Pendiente
1. ~~Al publicar: definir `YUMORI_URL` y `GOOGLE_SITE_VERIFICATION`, registrar Search Console y enviar el sitemap~~: hecho (verificado en producción el 2026-11-24).
2. **URL limpias:** `/productos/<slug>`, `/marcas/<slug>`, `/categorias/<slug>` y `/tiendas/<slug>`. Hoy el producto es `/p/<id>`. Hay que redirigir con 301 y mantener el id, porque los favoritos dependen de él.
3. ~~Redirecciones de productos que cambien de id~~: hecho el 2026-10-04 (301 con `Catalog.resolve`, ver [matching](../database/matching.md#ids-estables-alias)).
