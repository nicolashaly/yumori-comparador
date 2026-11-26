# Transición gradual a Next.js

Plan revisado y autorizado para comenzar el 2026-10-07. No es un rewrite: Python conserva extracción, normalización, matching, precios,
historial y SQLite. Next.js será presentación mediante un contrato de lectura pequeño; no duplicará `_match()` ni las reglas de precios.

## Fases y reversión
1. **Base verificable:** descubrir todas las pruebas, aislar sus bases y guardar una referencia de ids sobre una copia.
2. **Integridad:** bloqueos, transacciones, favoritos, lecturas parciales y matching, con regresiones y medición de ids.
3. **Contrato de lectura:** API interna Python; el HTML actual continúa funcionando.
4. **Piloto Next:** una ficha y un listado con paridad de ids, conteos, precios, estados y metadatos.
5. **Rutas restantes:** preservar `/p/<id>`, alias y `yumori:fav`. El cambio de origen requiere trasladar favoritos deliberadamente.
6. **Publicación:** runtime adecuado, HTTPS, origen fijo, límites, backups restaurables, permisos de tiendas y datos del operador.
7. **Retiro del renderer anterior:** solo después de confirmar estabilidad y paridad.

Cada fase termina con pruebas y un commit de checkpoint. Volver al renderer anterior debe seguir siendo posible. Revertir Git no revierte
SQLite: las migraciones deben ser compatibles y las copias recuperables. PostgreSQL y nuevas dependencias se justifican por un problema medido.

## Base de referencia
`python tests/run.py` descubre funciones `test_*` y clases `unittest.TestCase`, sin depender de las llamadas manuales de cada `__main__`.
Las suites se ejecutan en procesos separados y con una ruta SQLite temporal. El historial renderizado usa la misma conexión de fixture que
generó su catálogo; nunca listings de la base personal que casualmente tengan los mismos ids. Las pruebas directas de archivos históricos
no reciben este aislamiento: usar el runner, también para una suite (`python tests/run.py --file tests/test_catalog.py`).

`python -B tests/catalog_snapshot.py <copia.db>` genera JSON de ids, relación listing-producto y conteos. Abre SQLite con `mode=ro` y
`Catalog(sync=False)`: no migra ni escribe alias. Guardar resultados y copias solo en `data/` (no en Git).

Referencia local del 2026-10-07: 15.616 listings agrupados en 12.191 productos, 1.312 con ofertas en más de una tienda chilena.
La copia consistente se hizo con SQLite backup, no copiando el archivo mientras podía estar en uso.

## Checkpoint de integridad (2026-10-07)
- `save()` confirma listings, historial y metadatos juntos; una excepción revierte la tienda completa.
- Los adaptadores devuelven `ScrapeCompletion` al terminar: el runner conserva ofertas parciales sin afirmar cobertura completa.
- Las marcas internacionales separan visita (`*_observed`) de lectura completa; la visita permite rotar sin marcar desaparecidos.
- Ratings se detiene ante 403/429 en esa tienda. No cambia identidad ni reintenta el bloqueo.
- Favoritos se cargan en lotes de hasta 100 y solo se reemplazan después de una respuesta exitosa completa; errores ofrecen reintento.
- Matching conserva SPF y protege variantes y tiendas en uniones acumuladas. La caché serializa armados y reintenta alias no guardados.

Medición sobre la copia: 12.191 → 12.229 productos; 1.312 → 1.317 comparados entre tiendas chilenas. Cambian 1.193 relaciones
listing-id; **los 12.191 ids anteriores resuelven** tras sincronizar alias en la copia. La base personal no se migró en esta verificación.
Cuando un grupo incorrecto se divide, el enlace antiguo apunta al grupo mayor (desempate por id): conserva navegación, pero no puede
recuperar una preferencia de variante que el id antiguo nunca distinguió. Un reinicio del sitio aplicará las reglas y persistirá alias.

## Contrato de lectura (fase 3)
`api.py` incorpora listados/facets, fichas y observaciones históricas bajo `/api/v1`; contrato en [API de lectura](read-api.md).
Las rutas HTML permanecen y las reglas siguen en `Catalog`. No requiere Node, cambios de esquema ni nuevo scheduler. El siguiente
paso es un piloto Next.js contra este contrato, con paridad, antes de trasladar el resto de las rutas.
En la copia local se serializaron las 12.229 fichas sin errores; el listado por defecto devolvió los mismos ids y total (5.113)
que `Catalog.search(stock=True)`. Las pruebas usan fixtures separadas para errores, alias, monedas e historial; no se lanzó scraping.

## Piloto Next (fase 4)
`frontend/` incorpora Next.js 16, React 19 y TypeScript para `/explorar` y `/p/<id>`. Renderiza la API v1 desde el servidor,
sin caché, sin CORS adicional y sin replicar filtros o reglas de precios. Alias redirigen al id canónico; conteos, estados,
monedas, precios condicionados, tamaños de packs y metadatos conservan el contrato Python. Un fallo muestra un aviso sin
reutilizar precios anteriores. React escapa textos y los enlaces validan HTTP/HTTPS sin credenciales. Una CSP con nonce por
respuesta permite scripts de Next sin añadir `unsafe-inline` ni `unsafe-eval` para scripts.

La presentación adopta los colores del sitio actual con CSS pequeño; Tailwind, shadcn, Motion y Lucide quedan diferidos
hasta necesitarlos en rutas posteriores. No agrega dependencias Python ni cambia esquema. El renderer anterior sigue operativo.
El piloto usa otro origen local: no traslada favoritos ni cambia `yumori:fav`; historial y rutas restantes quedan para fase 5.

Instalación, comandos y reversión en [frontend](../../frontend/README.md). La verificación HTTP usa SQLite temporal y compara
IDs, total, precios, estados, alias y metadatos contra la API real. Véase [pruebas del piloto](next-pilot-testing.md).
No se usó la base personal ni se lanzó scraping. La verificación HTTP no certifica accesibilidad ni ejecución en navegador.

## Rutas restantes y favoritos (fase 5)
Next incorpora inicio, `/packs`, `/dermocosmetica` y sus packs, eventos conocidos y sus packs, `/marcas`, `/tiendas`,
`/favoritos` y las tres páginas legales. Conserva `/p/<id>` y redirecciones de alias. Los listados respetan la sección
de su ruta igual que Python: productos sueltos y packs permanecen separados. Los avisos de packs y resultados de la otra
sección usan conteos entregados por Python. La API v1 añade `/site`, `/favorites` y `/suggestions`; no duplica reglas en Next.

La ficha muestra historial paginado de observaciones, hora de Chile (America/Santiago), precios CLP/USD separados,
despacho informativo, referencias de rebajas del historial, relacionados, contenido de packs y precios con tarjeta aparte.
Las páginas legales consumen bloques de texto propios, sin insertar HTML. Los textos de privacidad describen las solicitudes
de identificadores para mostrar favoritos y su exportación local.

Los favoritos conservan `yumori:fav`. La carga valida respuestas completas en lotes de hasta 100, deduplica alias y solo
retira faltantes después de terminar todos los lotes. Si hay error o la lista cambia durante la carga, no sobrescribe cambios.
El nuevo origen no recibe automáticamente el almacenamiento del anterior: se traslada deliberadamente mediante exportación
JSON desde `/favoritos` en Python e importación en Next. La importación suma a los favoritos existentes y resuelve todos los
ids antes de guardar; el origen conserva su lista. No se modifica SQLite ni se ejecuta scraping.

`robots.txt` bloquea indexación y el sitemap permanece vacío en este piloto. La fase 6 requiere seleccionar un host persistente
para Python/SQLite, adaptar el runtime HTTP, configurar la API remota por HTTPS y el origen público fijo, probar restauración
de backups, límites de acceso y completar permisos de tiendas y datos del operador antes de publicar. La CSP continúa usando
nonce por respuesta y no se relaja para habilitar herramientas. Para revertir la presentación, abrir el renderer Python,
que sigue operativo; cada origen mantiene sus favoritos y puede conservarlos en el archivo exportado.

## Diseño original en Next (cierre visual de fase 5)

El piloto reemplaza la presentación simplificada por la estructura y estilos del renderer original: hero con Fraunces y sakura,
cabecera con menús, tarjetas, filtros laterales y drawer móvil, galería y filas de ofertas, directorios y páginas legales.
`frontend/app/original.css` conserva el CSS Python sin cambios; las fuentes y fondos se sirven desde el origen Next.
La prueba HTTP verifica igualdad de esos archivos y los conteos visibles de los filtros. Los textos de tarjetas, categorías y
avisos de packs provienen de Python; Next no calcula reglas de precios ni de catálogo.

Se conserva el historial paginado y el traslado deliberado de favoritos. La revisión de navegador compara ambos renderers con
una misma base temporal y comprueba inicio, listado y ficha en escritorio/móvil, sugerencias con teclado, drawer y favoritos.
Es una comprobación de las vistas y fixtures revisadas, no una certificación de igualdad de todos los píxeles ni de accesibilidad completa.
La siguiente fase es la 6, publicación; todavía no se ha desplegado el sitio ni retirado el renderer Python.
