# Funciones del sitio

Se levanta con `python server.py` (http://127.0.0.1:8000) o con la configuración `yumori` de `.claude/launch.json`. El servidor no recarga solo el código Python: hay que reiniciarlo tras editarlo. Los cambios en `static/` se ven al recargar.

## Páginas
- `/`: inicio, con el buscador, el banner de ofertas y "Mayor diferencia entre tiendas".
- `/explorar`: grilla con filtros.
- `/packs`: el mismo explorador, solo para packs.
- `/dermocosmetica` y `/dermocosmetica/packs`: el mismo explorador para la sección de dermocosmética (ver más abajo).
- `/p/<id>`: un producto.
- `/marcas` y `/tiendas`. En `/tiendas` (Next, desde el 2026-11-25), una tarjeta por tienda chilena con una franja por sección en la que vende (rosa: belleza asiática; verde: dermocosmética), cada una con su conteo con stock y su enlace, y los botones "Ver catálogo" (la sección con más productos) e "Ir a la tienda". Las internacionales van aparte, con el mismo formato: una franja lila ("N productos en Yumori · M también en Chile") y solo "Ir a la tienda", porque Explorar no filtra por tienda extranjera.
- `/favoritos`.
- `/privacidad`, `/terminos` y `/cookies`.
- Fragmentos: `/fragmento/cards` y `/fragmento/sugerencias`. Para buscadores: `/robots.txt` y `/sitemap.xml` (ver [SEO](../seo/strategy.md)).

## Diseño
- **Filosofía de UI de MangaDex** (simple, poco ruido, buscador protagonista, responsive de verdad), con identidad propia: pastel claro, blanco y beige, rosa, lavanda, durazno y verde salvia como acento.
- **Design system en `static/style.css`:** variables de color, spacing en base 4 px, radios, sombras y tipografía. Los contrastes pasan 4,5:1. El pastel es solo acento y el botón primario usa un tono más oscuro.
- **Animaciones** de 150-300 ms, siempre con `prefers-reduced-motion`.
- **No es una tienda:** no hay carrito, y el botón primario es "Ver en [tienda]".
- **Navbar:**
  - "Categorías" y "Marcas" abren menús con chips. "Marcas" muestra las 5 marcas con más productos y "Mostrar todas".
  - "Tiendas" es un enlace simple, sin ranking ni destacadas, para no mostrar preferencia.
  - "Packs" y "Dermocosmética" son enlaces simples. En móvil todo va en el menú de la hamburguesa.
  - Si algún día hay publicidad, irá marcada y nunca dentro de esos menús.
  - Con 6 enlaces, la base del buscador de la barra es 14rem (con 22rem partía la barra en dos filas entre 940 y 1100 px).
- **Inicio (rediseñado el 2026-10-04, pedido del usuario):** ya no habla solo de belleza asiática.
  - Etiquetas de color (K-beauty, J-beauty y Dermocosmética, esta última solo si hay productos), título "Tu skincare favorito, *al mejor precio*" y una descripción con los números reales: productos, y tiendas chilenas, farmacias y del extranjero.
  - Destellos y flores propios (`server.HERO_DECO`, `aria-hidden`) alrededor del título.
  - **Tipografía del título: Fraunces**, alojada en `static/fonts/` (dos archivos woff2 de ~20 KB con el subconjunto latin, licencia SIL OFL en `OFL.txt`, bajados de Fontsource con permiso del usuario). Variable `--font-display`. Al ser del propio sitio, la CSP la permite y no hay recursos de terceros. `font-display: swap`: si tarda, se ve primero una serif del sistema.
  - Ojo: insertar CSS buscando `:root` cayó dentro del comentario del inicio de `style.css` y dejó el sitio sin estilos. Buscar `
:root {`.
- **Fondo de cerezos:** 3 SVG propios en `static/`, en una capa fija con opacidad 0,4. Un comentario XML no puede contener `--`: eso rompió el SVG una vez sin dar error.
- **CSS Grid:** los hijos que deben encogerse llevan `min-width: 0` (bug real de cards cortadas en móvil, 2026-09-22).

## Cards y producto
- **La card agrupa un producto:** muestra "desde $X" y "en N tiendas". Si solo lo vende una tienda internacional, dice "Estimado $X · Solo en el extranjero".
- **Clics en la card (2026-10-04, pedido del usuario):** toda la tarjeta lleva al producto (el `::after` de `.card-link` la cubre) y la **marca es un enlace aparte**, encima, a todos sus productos en su sección (`/explorar`, `/packs` o `/dermocosmetica`, con `?marca=`). Un enlace no puede ir dentro de otro, por eso el de la marca va fuera de `.card-link` con `z-index` mayor. El corazón de favoritos también va encima. Sin marca ("sin-marca"), es texto.
- **Valoración en la card:** solo "★ 4,9", la de la tienda con más reseñas, y solo si esa tienda tiene 5 o más reseñas (`MIN_REVIEWS`). La página de producto muestra todas las notas, por tienda y con su cantidad. Nunca se muestra el texto de las reseñas ni un "0".
- **Página de producto:**
  - precios por tienda, stock e historial (sin precios repetidos seguidos);
  - galería de hasta 4 imágenes, priorizando las de la tienda más barata;
  - la sección "Desde el extranjero".
- **Empate en el precio más bajo:** dice "Mismo precio en N tiendas", con un botón por tienda en orden alfabético.
- **Diferencia de más de 40% entre tiendas:** aviso para confirmar que sea el mismo tamaño y versión.
- **Descripción propia** (`describe.py`):
  - No copia ni parafrasea a las tiendas: extrae datos (tipo, beneficios, compuestos, SPF, tipo de piel) y redacta con plantillas.
  - Una negación no cuenta. Un beneficio necesita 2 o más menciones o aparecer en el nombre. Sin datos no se muestra nada.
  - Proteger del sol solo se afirma con SPF en el texto, si el producto es un protector solar o si el nombre lo dice, y nunca en limpiadores.
  - Lleva el aviso de que es un resumen elaborado por Yumori, con enlace a la tienda.
  - **Maquillaje (2026-10-04, auditoría pedida por el usuario):** con la misma regla de 2 menciones, `traits()` agrega el acabado ("Tiene un acabado mate", satinado, aterciopelado, glossy, luminoso, natural, con destellos) y lo que dicen las tiendas: larga duración, resistencia al agua, alta pigmentación, cobertura, fórmula vegana y producción sin pruebas en animales.
    - Salvaguardas: si la página nombra más acabados de los que sostiene, no se elige ninguno; los packs no reciben rasgos; duración, agua, pigmentación y cobertura solo en maquillaje; la resistencia al agua nunca en limpiadores.
    - **El nombre del tono no cuenta** (`shade_of()`, `prepare()`): "Honey Lemon" decía "destaca miel" (6 productos con ese falso positivo).
  - **Texto de los sitios oficiales de las marcas (2026-10-04, opción 1 aprobada por el usuario):** `scrapers/brand_text.py` lee una vez por semana `/products.json` de Unleashia (unleashiaworld.com), TirTir (tirtir.global), Mixsoon (mixsoon.us), Tocobo (tocobo.us), Missha (misshaus.com) y Centellian24 (centellian24.com), y guarda solo el texto en la tabla `brand_text`: no son ofertas ni tocan el matching de precios ni los ids.
    - `catalog.official_text` suma ese texto a `Product.text` (lo que lee describe.py) solo si calza UN producto oficial: misma marca y formato (mini o no), mismo tamaño si los dos lo dicen, y las palabras de un nombre contenidas en el otro (al menos 2 en común). Packs nunca. Se excluyen los regalos y promos con texto de relleno (`GIFT`).
    - Medido: 399 productos reciben el texto oficial y **86 pasan a tener descripción** (de 2.874 a 2.788 sin descripción); ~150 ganan tipos de piel o ingredientes (también en los filtros). Ids idénticos y ningún tipo o categoría cambió. Revisión manual de 30 cruces: todos correctos (tonos y versiones "Jumbo" o con fecha corta calzan con su producto oficial).
    - El aviso de la descripción dice "a partir de lo que informan las tiendas y el sitio oficial de la marca" cuando corresponde (`Product.brand_site`).
    - Descartadas (ver tiendas): Rom&nd, Lily by Red y Elizavecca (`Disallow: /`), Apivita (403), y THE SAEM, Banila Co, Numbuzin y Frudia (sitio solo en coreano). Pendiente: dermocosmética con sitio en Chile (La Roche-Posay y Vichy por GTIN, luego Avène, Eucerin y Uriage) y Peripera y Colorgram (sus sitios no respondieron).
  - **Cobertura medida (2026-10-04):** de 10.897 productos, 2.874 (26%) quedan sin descripción, antes 3.505 (32%). De esos, ~2.055 son productos cuya tienda no entrega ninguna descripción (YesStyle, Stylevana, Ahumada, Paris, Novasalud, Farmaloop y parte de Moonbow): sin eso no hay nada que resumir sin inventar. Volver a leer las fichas no conviene (Ahumada la tiene vacía, Paris las veta en robots, Stylevana pesa ~1 MB por ficha). **No se baja la regla a 1 mención:** ganaría 549 productos, pero afirmaría con muy poca base.
- **"Precio por confirmar":** se muestra cuando el precio de una tienda parece un error de carga (fuera de rango o con un salto brusco, según `db.anomaly`). Se ve con su aviso, pero no cuenta como mejor precio. Ver [esquema](../database/schema.md#anomalías-de-precio).
- **Productos internacionales:** se incluyen aunque ninguna tienda chilena los venda. Ver [ADR-005](../decisions/ADR-005-productos-internacionales.md).

## "También te podría interesar" (2026-10-04, pedido del usuario)
- Al final de cada producto, hasta 8 tarjetas de `Catalog.related()`: mismo tipo de producto (si no se sabe, misma categoría), misma sección, packs con packs y solo con stock.
- **Orden por afinidad:** ingredientes destacados en común (valen doble), tipos de piel en común y misma marca; después, en cuántas tiendas está.
- **Variedad:** a lo más 2 por marca, y nunca otra versión del mismo producto (`catalog.same_line`: misma marca y al menos 50% de las palabras del nombre en común, que cubre otro tamaño, su miniatura, otro tono o el nombre mal escrito).
- Sin tipo ni categoría no se muestra nada: no se recomienda al azar (11% de los productos).
- Medido: 1-2 ms por producto y las 10.897 páginas sin errores.

## Explorar
- **Filtros:** marca, tienda, precio, categoría, tipo, tipo de piel, ingrediente, "en 2+ tiendas", "Solo con descuento" e "Incluir productos sin stock" (por defecto se ocultan los agotados).
- **Los números de cada filtro** se calculan con los demás filtros aplicados (`Catalog.counts`), para que coincidan con la lista.
- **Órdenes:** relevancia, precio, mayor diferencia, nombre y mayor descuento.
- **Categorías:** ~45 tipos agrupados en Facial, Maquillaje, Cabello, Cuerpo y manos, y Accesorios.

## Dermocosmética (2026-10-04)
Sección aparte para marcas no asiáticas que se venden mucho en farmacias chilenas (Eucerin, La Roche-Posay, Vichy, CeraVe, ISDIN...). Los datos están en [el contrato](../architecture/overview.md#contratos-entre-capas); lo visual es esto.
- **Qué entra:** se decide por marca (`DERMO_BRANDS` en `catalog.py`, armada desde la lista de `scrapers/dermo.py`). El sitio asiático de siempre no cambia: `search`/`counts` sin `section` solo devuelven productos asiáticos. Una marca asiática vendida en una farmacia (SKIN1004 en Ahumada) sigue en la comparación asiática.
- **`/dermocosmetica`:** `explore(cat, qs, section="dermocosmetica")`, el mismo explorador que `/explorar`. Lista, filtros, categorías, marcas y tiendas usan esa sección, así que los números cuadran con la lista. Lleva título y descripción propios (con las 3 marcas con más productos) y la misma regla SEO que `/explorar` (canónica, `noindex, follow` con búsqueda, filtros u orden, y en el sitemap).
- **Sin productos** (aún no se lee ninguna farmacia): `derm_empty()` muestra "Estamos sumando farmacias a Yumori" con `noindex`, sin explorador, y la sección no entra al sitemap. El enlace de la barra se mantiene; el acceso del inicio se oculta.
- **Packs de dermocosmética:** `/dermocosmetica/packs`, igual que `/packs`: los packs no se mezclan con los productos sueltos y cada pack se compara solo con el mismo pack. Se llega desde "También hay N packs que coinciden". No van dentro del explorador porque `Catalog._match` ya separa productos y packs, y mezclarlos rompería los números de los filtros.
- **Buscador:** cada búsqueda mira una sola sección. Si la otra también tiene resultados se avisa: con resultados, una línea chica "También hay N productos de dermocosmética que coinciden · Ver en Dermocosmética"; sin resultados, un botón destacado en el estado vacío. En `/dermocosmetica` el buscador de la barra busca dentro de esa sección (`search_action`).
- **Inicio:** sigue siendo asiático (el contador "N productos" usa `section_counts["asiatica"]`). Solo hay una línea discreta al final, "¿Buscas dermocosmética de farmacia? Ver dermocosmética", y solo si la sección tiene productos.
- **`/marcas` y `/tiendas`:** con productos de dermocosmética, una segunda parte "Dermocosmética" (`derm_brands`, `derm_stores`), de la A a la Z y en orden alfabético, sin ranking. Sin ellos, las dos páginas quedan como antes.
- **"Búscalo también en"** (2026-10-04): en cada producto suelto de dermocosmética, enlaces al buscador de Cruz Verde, Falabella y Salcobrand con la marca y el nombre (`server.SEARCH_ELSEWHERE`). Son tiendas que no leemos (JavaScript, bloqueo o términos que prohíben extraer): no mostramos su precio ni lo comparamos, solo el enlace (`rel="noopener nofollow"`, sin "sponsored"). El formato de Salcobrand se verificó en su formulario; los de Cruz Verde y Falabella son los conocidos, pendientes de un clic de prueba.
- **Página de producto:** una marca de dermocosmética lleva la ruta "Inicio / Dermocosmética / [Categoría] / Marca", también en el JSON-LD.
- **Precio con tarjeta** (ej. "CMR Falabella"), `Product.card_offers`: bloque "Con tarjeta de la tienda" bajo "Precios por tienda", solo si hay alguna oferta con stock y con precio de tarjeta menor que el normal.
  - Una fila por oferta, con el formato de las filas de precios: tienda, etiqueta "Con [tarjeta]", precio con tarjeta, "Precio normal: $X" (texto, sin tachado) y "Ver en [tienda]" (la tarjeta y "se abre en otra pestaña" van para lector de pantalla).
  - Nota: "Precio exclusivo con [tarjeta]; no lo paga cualquier cliente, por eso no cuenta como mejor precio." (en plural si las tarjetas son distintas).
  - El precio destacado de arriba, el empate y el "Mejor precio" siguen siendo los normales.
  - **No va en "Precios por tienda"** (duplicaría el bloque que está justo debajo y mezclaría un precio condicionado con los que paga cualquiera) **ni en las cards:** casi todo Ahumada tiene precio CMR, así que una etiqueta en cada card sería ruido y destacaría a una sola tienda.

## Ofertas detectadas (2026-10-03)
Ver [ADR-006](../decisions/ADR-006-ofertas-contra-historial-propio.md).
- **Franja de ofertas en el inicio (desde el 2026-10-04, pedido del usuario; antes era una diapositiva por tienda):** 24 tarjetas de productos (`Catalog.deal_picks`) cuyo mejor precio bajó al menos `DEAL_SHOW` (20%), con stock y sin packs.
  - **Sin favoritismo:** se agrupan por la tienda que tiene ese precio y se intercalan en orden alfabético (una por tienda por vuelta), así Sokobox con cientos de rebajas no tapa a las demás. A lo más 2 por marca y sin otras versiones del mismo producto (`same_line`).
  - **Rota cada hora:** el orden dentro de cada tienda sale de un sorteo con la hora como semilla (mismo resultado durante toda esa hora).
  - **Con mouse** (`(hover: hover) and (pointer: fine)`) avanza sola una tarjeta cada 5 s, con flechas y pausa; se detiene con el mouse encima o el foco dentro, y no avanza sola con `prefers-reduced-motion`. **En celular y tablet** no se mueve sola: se desliza con el dedo (`scroll-snap`) y se asoma la tarjeta siguiente como pista. Sin JS, se desliza igual.
  - Lleva la nota "No es publicidad".
- **"Ver las N ofertas"** lleva a Explorar con `oferta=1&orden=descuento`, y N es exactamente el total que se ve ahí (lo verifica una prueba). `Catalog.deals` (resumen por tienda) se mantiene para los conteos.
- **Etiqueta "−N%"** en las cards y en las sugerencias.
- **Precio "antes" tachado** al lado del precio, en las cards y en las sugerencias, solo cuando hay etiqueta "−N%" (`server.was`, `Product.drop_ref`, `Offer.ref`). Es la misma referencia del descuento (el precio más alto que vimos en esa tienda en los últimos 14 días), **nunca el precio tachado que publica la tienda**. Con varias tiendas, es el de la tienda con el mejor precio que más bajó (pedido del usuario, 2026-10-04).

## Eventos de ofertas: Cyber, Black Friday, CyberDay (2026-10-04, pedido del usuario)
- **Calendario, `catalog.EVENTS`:** cada evento tiene `slug` (su dirección: `/cyber`, `/black-friday`, `/cyberday`, cada una con `/packs`), `name`, fechas (hora de Chile, ambos días incluidos) y `theme` (su logo).
  - **Black Friday se calcula solo cada año** (`black_friday()`): el viernes siguiente al cuarto jueves de noviembre, hasta el lunes (Cyber Monday). En 2026, del 27 al 30 de noviembre.
  - **CyberDay (junio) y el Cyber de octubre los fija cada año la Cámara de Comercio de Santiago:** hay que anotarlos en `EVENTS` cuando se anuncian. Hoy está el Cyber del 5 al 7 de octubre de 2026 (fechas que anuncia ¡Qué Coreana!).
  - **Previa (`early`, opcional):** muchas tiendas adelantan sus rebajas. Desde ese día se activa la sección y se cuentan las bajas, pero las fechas que se muestran siguen siendo las del evento y la página aclara desde cuándo contamos. El Cyber de 2026 tiene previa desde el 1 de octubre (Arumi bajó 58 productos el 1-oct y Sokobox 835 el 2-oct; pedido del usuario).
  - **Para agregar un evento:** una línea en `EVENTS`. Si es de un tipo nuevo, un ícono en `server.EVENT_ICONS` y sus colores (`.ev-<theme>`) en `style.css`.
- **Qué entra:** el mejor precio de hoy es una baja de al menos `DEAL_PCT` (10%) que **empezó durante el evento** (`catalog.in_event`, `Product.event_drop`). Se mide igual que las ofertas ([ADR-006](../decisions/ADR-006-ofertas-contra-historial-propio.md)). "Empezó" es el día del precio actual en nuestro historial: `Offer.since`, de `catalog.price_since`.
  - Las tiendas no marcan sus productos como "Cyber" en lo que leemos (revisado en las etiquetas de 6 tiendas Shopify): por eso no se usa lo que diga cada tienda.
  - Una rebaja que ya venía de antes no cuenta (ej. la de Sokobox, que empezó el 2 de octubre de 2026).
- **Página:** el mismo explorador (filtros, conteos y orden), con la belleza asiática y la dermocosmética juntas, ordenado por mayor descuento.
  - Los packs rebajados se avisan en un recuadro destacado (`server.packs_callout`, el mismo que en Explorar "N packs también coinciden con tu búsqueda").
  - `catalog.event_for(slug)` elige qué edición mostrar: la que está en curso; si no, la que terminó hace menos de 14 días; si no, la próxima.
  - Sin rebajas detectadas muestra un aviso propio, no "sin resultados con esos filtros".
- **Solo mientras dura el evento** (`catalog.live_event`): su logo va **primero en el menú, a la izquierda de Categorías**, más grande y también en celular. El inicio muestra un aviso con el total de productos y tiendas (si ya hay rebajas), y la página entra al sitemap. Antes y después la página existe, pero no se promueve.
- **Logos propios** (`server.event_logo`): Cyber con un rayo y degradado rosa a lavanda; Black Friday en una pastilla negra con una etiqueta dorada; CyberDay también con el rayo (preferencia del usuario), pero con degradado lavanda a verde salvia. **No se usan los logos oficiales:** son marcas registradas (el de CyberDay, de la Cámara de Comercio de Santiago) y darían a entender que Yumori participa oficialmente.
- Depende de que el scraping corra durante el evento: hoy corre una vez al día, al iniciar sesión en el PC.

## Despacho por tienda (2026-10-04, pedido del usuario)
- **`shipping.py`:** por tienda chilena, el despacho más barato publicado (`desde`), el mínimo para envío gratis (`gratis`), su alcance (`donde`), una nota y la página de donde se leyó. Revisado a mano en el sitio de cada tienda (`REVIEWED`).
- **Nunca se suma al precio** ni cambia el mejor precio: el despacho se cobra por pedido, depende de la comuna y el envío gratis depende del total del carro.
- Se muestra bajo cada tienda en "Precios por tienda" (`server.shipping_text`), con la nota "Los precios no incluyen despacho" y la fecha de revisión, y en las tarjetas de `/tiendas`.
- Lo que una tienda no publica en texto queda como "Despacho no informado". Sin revisar (bloquean nuestras consultas o estaban caídas): Kosmeticos, Belleza Coreana, Vierose y K Belleza. Novasalud, Farmaloop y Paris no muestran montos en texto.
- Hay que volver a revisarlo cada tanto: estas condiciones cambian (por ejemplo, en eventos como el Cyber).

## Buscador (2026-09-28)
- Desde 2 letras, sugiere hasta 6 productos en tarjetas horizontales (`/fragmento/sugerencias`, con 150 ms de espera entre teclas), más "Ver los N resultados en Explorar".
- Orden de las sugerencias: con stock primero, individuales antes que packs y más tiendas primero.
- Combobox accesible: flechas, Enter y Escape.
- **Dermocosmética en las sugerencias:** primero lo asiático y, si sobra espacio hasta las 6, productos de dermocosmética con la etiqueta "Dermocosmética ·" al inicio de su línea. Al final, un enlace por sección que tenga resultados ("Ver los N resultados en Explorar" y "... en Dermocosmética"), con el total real de cada una. Así "eucerin" se encuentra desde cualquier página sin mezclar los listados.

## Favoritos
Se guardan en el navegador (`localStorage`, clave `yumori:fav`), por id de producto.
- Se valida que el dato sea una lista de strings. La página solicita lotes de hasta 100 ids para no truncar listas grandes; solo actualiza tarjetas y almacenamiento tras completar todos los lotes. Una respuesta HTTP fallida o un error de red conserva los favoritos y muestra un botón de reintento. Si la lista cambia durante la carga, se vuelve a leer antes de reemplazarla.
- **Si el matching cambia un id**, el favorito no se pierde: `/fragmento/cards` lo resuelve con `Catalog.resolve`, y al abrir `/favoritos` la lista del navegador se reescribe con los ids actuales. Un enlace viejo a `/p/<id>` redirige con 301.

## Límites conocidos
- **Imágenes:** se cargan desde cada tienda (hotlink), así que si una tienda se cae sus fotos no cargan (caso real: kosmeticos.cl, 2026-10-04). Desde ese día cada producto lleva fotos de respaldo, una por cada otra tienda que lo vende (`Product.alts`, en `data-alts`). `static/app.js` cambia a la siguiente si la foto da error o no carga en 6 s; el plazo corre recién cuando la imagen está en pantalla. Una tienda que falló se recuerda en la página: sus demás fotos pasan directo al respaldo y sus miniaturas se ocultan. Un producto que solo vende la tienda caída queda sin foto. Al publicar conviene cachear las imágenes.
- **Contador de favoritos del menú:** puede contar ids de productos que ya no existen hasta que se abre `/favoritos`, que limpia la lista.
- **Chips de categoría al llegar desde el banner:** cuentan búsqueda, marca y stock, y no la tienda ni las ofertas, así que no coinciden con el título.
