# API de lectura v1

Se sirve con `python server.py` en el mismo origen local que el sitio, bajo `/api/v1`. Solo GET, sin autenticación,
sin CORS permisivo, sin requests a tiendas y sin endpoints de escritura. `api.py` serializa el catálogo; no replica matching,
precios ni filtros. El piloto Next.js vive en `frontend/`; el renderer HTML anterior continúa funcionando.

El catálogo compartido sigue pudiendo persistir alias al reconstruirse (`get_catalog()`); "de lectura" describe el contrato HTTP,
no una promesa de que el proceso nunca escriba SQLite. El historial abre explícitamente SQLite en `mode=ro`, sin migraciones.
Mantener el servidor ligado a `127.0.0.1`: esta API no convierte `http.server` en un servidor público de producción.

## Rutas

| GET | Respuesta |
| --- | --- |
| `/api/v1/products` | `items`, `total`, `page`, `page_size`, `pages`, `facets` |
| `/api/v1/products/<id>` | `product`, `requested_id`, `canonical_id` |
| `/api/v1/products/<id>/history` | `stores`, `page`, `limit`, `requested_id`, `canonical_id` |
| `/api/v1/site` | `home`, `brands`, `stores`, `events`, `live_event`, `legal`, `shipping_reviewed`, `operator_missing_fields` |
| `/api/v1/favorites?ids=<id>,<id>` | `items`, `resolutions`, `missing_ids` |
| `/api/v1/suggestions?q=<texto>` | `query`, `items`, `sections` |
| `/api/v1/sitemap` | `products`: `{id, lastmod}` de los productos que alguna tienda chilena aún lista (`Product.listed_in_chile`, con o sin stock y aunque esté sin conexión); `lastmod` es el día local de su último cambio de precio, stock o precio tachado |

Todas las respuestas incluyen `version: 1`. Las exitosas incluyen `catalog_last_update` (fecha conservadora del catálogo,
no captura individual), `exchange_rate` con fecha y las condiciones de la estimación. Alias válidos devuelven 200 y el id
canónico: el consumidor puede reemplazar la URL. Los enlaces HTML viejos mantienen su redirección 301.

## Rutas restantes (fase 5)

`site` no acepta parámetros. `home` conserva los métodos del renderer: `top_spread()`, `drops()`, `deal_picks()` con semilla
horaria y `top_brands(10)`. Expone `product_count`, `store_count`, `section_counts`, `top_brands`, `spread`, `drops`, `deals`,
`deals_total`, `deal_days` y `deal_show_percent`. Las tarjetas son los mismos resúmenes del listado. `brands` separa
`asiatica` y `dermocosmetica` en arrays `{slug,name,count}`. `stores` agrega `international`; cada entrada tiene `domain`,
`name`, `count`, `url`, `stale_since` y `shipping`. Los conteos chilenos vienen de `Catalog.counts(stock=True, section=...)`,
por lo que coinciden con el listado de la tienda. Internacionales incluyen `matched_in_chile`. Directorios usan orden alfabético.
`stores.chile` (para `/tiendas`) une las dos listas chilenas: una entrada por tienda, sin `count` y con `counts` = `{asiatica?, dermocosmetica?}`,
solo con las secciones en que la tienda aparece. El orden alfabético lo da la API (`words()`), no el frontend.

`events` selecciona una edición por slug mediante `event_for()`, y `live_event` conserva el método existente;
contienen slug, nombre, inicio, fin, tema y previa opcional. No seleccionar fechas ni edición de un evento en TypeScript.
`legal` contiene `privacidad`, `terminos` y `cookies`, cada uno con `title`, `updated` y `blocks` de `{tag,text}`.
Los bloques se extraen de los documentos propios de `legal.py`; `tag` solo puede ser h1, h2, p, li, th o td.
El consumidor debe presentar texto escapado, nunca interpretarlo como HTML. Los campos del operador faltantes se identifican
en `operator_missing_fields`; no se inventan ni se esconden los requisitos pendientes de publicación.

Favoritos permite un solo `ids`, separado por comas, de hasta 100 ids hexadecimales de diez caracteres. Vacío devuelve
una lista vacía. Resuelve alias mediante `Catalog.resolve()`, conserva orden solicitado y deduplica productos canónicos.
`resolutions` mapea cada id solicitado al actual o null; `missing_ids` enumera los no encontrados. Un error HTTP no autoriza
al cliente a borrar favoritos. Esta ruta no guarda preferencias en el servidor; mantener la clave local `yumori:fav`.
El valor `ids` permite hasta 1099 caracteres, excepción acotada al límite general de 200.

Sugerencias conserva la búsqueda del sitio: recorta texto a 100 caracteres, primero hasta seis resultados asiáticos y luego
completa con dermocosmética. `sections` contiene `{section,total,path}` para secciones con resultados, con el total de
`Catalog.search(stock=True)`. Sin coincidencias entrega arrays vacíos. Solo acepta un parámetro `q`.

La ficha añade `related` por `Catalog.related()`, `shipping_reviewed` y un resumen `product` en enlaces `contents`, `includes`
e `included_in` (null si no hay coincidencia). Cada oferta chilena añade `shipping` o null: condiciones publicadas
`desde`, `gratis`, `donde`, `nota` opcional, `fuente` validada y fecha `reviewed`. Nunca se suman al precio.
Los resúmenes incluyen `drop_reference_price`, referencia exacta de `Product.drop_ref` para la baja mostrada.
La ficha añade `price_spread_warning` (diferencia de al menos 40% en un producto chileno) y `search_elsewhere`:
enlaces `{name,url}` al buscador de tiendas no leídas, solo para dermocosmética individual, generados con el directorio
del renderer Python y su consulta original. Nunca representan ofertas ni precios verificados.

El listado agrega `section_product_count` y `related_counts` (`packs`, `other_section`) para avisos de rutas relacionadas.
Packs usa búsqueda, marca, stock y sección/evento; la otra sección usa solo búsqueda y stock, como los avisos del renderer.
No refleja una réplica cliente de los filtros: los conteos se calculan siempre con `Catalog.search()` en Python.

## Listados y filtros

Usan `Catalog.search()` y `Catalog.counts()`, igual que Explorar. El tamaño de página es `catalog.PAGE_SIZE`, sin opción de
descargar el catálogo completo. Los conteos de facets retiran su propio filtro y conservan los demás, igual que el sitio.

| Parámetro | Significado |
| --- | --- |
| `q`, `marca` | búsqueda y slug de marca |
| `tienda` (repetible) | dominio de tienda chilena; mantiene la limitación del filtro actual |
| `cat` | categoría reconocida; se ignora en packs, igual que HTML |
| `tipo`, `piel`, `ing` (repetibles) | tipo, piel e ingrediente |
| `min`, `max` | enteros CLP no negativos; mínimo no puede superar máximo |
| `sinstock=1` | incluir productos sin stock; por defecto se ocultan |
| `multi=1`, `oferta=1` | múltiples tiendas y rebajas contra nuestro historial |
| `packs=1` | packs; por defecto solo individuales |
| `seccion` | `asiatica` (defecto), `dermocosmetica` o `todas` |
| `evento` | slug de evento conocido; junta ambas secciones, como HTML |
| `orden` | `precio_asc`, `precio_desc`, `ahorro`, `nombre`, `descuento` o defecto |
| `pagina` | entero 1–100000; fuera de resultados devuelve lista vacía |

Ejemplos: `/api/v1/products?q=anua&orden=precio_asc`, `/api/v1/products?seccion=dermocosmetica&tienda=www.farmaciasahumada.cl`.
Parámetros desconocidos, repetidos en campos simples, valores largos o rangos inválidos devuelven 400.

## Precios y honestidad

Un precio es `{amount: entero, currency: "CLP"|"USD", decimals: 0|2}`. `amount` representa unidades menores: 19990 CLP son
$19.990; 1999 USD son US$19,99. Nunca mezclar dólares y pesos al ordenar/comparar en el cliente.

- `display_price` está en CLP; `display_is_estimate` distingue estimación extranjera. La estimación incluye IVA y excluye envío.
- `display_price_confirmed` indica disponibilidad confirmada del origen que respalda el precio mostrado; una estimación sigue siendo estimación.
- `best_store_ids` contiene todas las tiendas chilenas empatadas con stock confirmado, en orden alfabético. Vacío si no hay.
- `domestic_offers` y `international_offers` están separados; cada oferta tiene `available`, `status`, `status_label`, fechas
  de no confirmación y motivo de anomalía. No recomendar ofertas `stale`, `missing`, `suspect` o `out_of_stock`.
- `card_offers` contiene precios condicionados y nombre de tarjeta, separados del mejor precio. No afectan filtros ni rebajas.
- Cada precio condicionado expone `normal_price` para mostrar el precio ordinario de esa oferta sin tacharlo.
- `rating` conserva tienda y cantidad de reseñas; la selección de la tarjeta usa el mínimo vigente del catálogo. No es una valoración propia.
- `card_prefix`, `card_store_label`, `card_meta` y `has_deal` conservan los textos y umbral visual de las tarjetas originales.
- `category_counts` entrega los conteos de categorías con búsqueda, marca y disponibilidad, como los chips del renderer Python.
- La ficha añade `category_label`, `pack_size_warning` y `primary_offer_store_ids`, calculados en Python para preservar el breadcrumb,
  el aviso de tamaños y los enlaces superiores. `primary_offer_store_ids` puede incluir ofertas sin stock confirmado o extranjeras;
  no equivale a `best_store_ids` ni certifica disponibilidad. Los enlaces deben mostrar el estado de la oferta.
- `description` usa `describe.py` y lleva disclaimer. Los packs exponen contenido, enlaces y tamaños propios del pack, distintos del tamaño suelto.
- URLs externas se entregan solo con esquema HTTP/HTTPS y sin credenciales; texto JSON es dato, nunca HTML a insertar sin escapar.
- Los bloques legales conservan `text` y añaden `inline`, nodos de texto, `strong`, `em`, `code` y enlaces con destinos validados.
  El consumidor renderiza una lista cerrada de elementos React; nunca inserta esos datos como HTML crudo.

## Historial y límites

El historial es por tienda chilena y oferta elegida por el catálogo, como la ficha actual. No mezcla variantes de una tienda
ni crea historial extranjero. Expone observaciones de cambio (precio o stock), no una fila por día ni precios interpolados.
`captured_at` conserva el timestamp guardado; los datos actuales lo guardan en UTC. `price_since_day` de la ficha sigue siendo
el día local calculado por el catálogo actual; no es un timestamp UTC y su timezone aún depende del equipo.

`pagina` y `limite` paginan cada tienda de forma independiente, en orden cronológico; `limite` defecto 100, máximo 1000.
Cada tienda devuelve su `total`. La conexión es de solo lectura; el listado no incluye todo el historial.

HTTP limita la URL a 8192 caracteres y 80 campos. Cada valor tiene máximo 200 caracteres; listas repetibles, máximo 20 valores.
Errores usan `{version: 1, error: {code, message}}`: 400 validación, 404 ruta/producto, 414 URL larga y 500 genérico sin traceback.
Se heredan cabeceras de seguridad y `Cache-Control: no-cache` del servidor. No registrar aquí secretos ni generar un origen público
desde datos del consumidor. Antes de publicar faltan el runtime de producción, control de acceso y límites de solicitudes del despliegue.

## Compatibilidad y reversión

La versión v1 es un contrato inicial para el piloto. Los consumidores ignoran campos nuevos; cambios incompatibles requieren otra versión.
Revertir el checkpoint de esta fase retira las rutas JSON sin migración de esquema ni cambios de ids, scraping o HTML.
Pruebas de paridad deben verificar ids, conteos, estados, empates, monedas, alias, tamaños de packs y errores, con fixtures aisladas.
