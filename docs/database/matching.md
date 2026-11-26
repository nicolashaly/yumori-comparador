# Matching y packs

El matching (`match.py`) agrupa listings de distintas tiendas en un mismo producto. Es la parte difícil del proyecto: entre tiendas coinciden solo ~22 SKUs, así que el criterio principal es el texto, el código de barras (GTIN) es el segundo, donde las tiendas lo publican, y el tercero es la unión por nombre parecido. Ver [ADR-002](../decisions/ADR-002-matching-por-texto.md).

## Clave de producto
`key_of` arma la clave con (marca, palabras normalizadas sin ruido, tamaños, es_miniatura).
- **La marca** sale del vendor de la tienda si es confiable. Si el vendor es el nombre de la tienda o viene vacío, se busca en el título una marca ya conocida (`NOT_BRANDS` lista los vendors que son tiendas). Con dos marcas candidatas del mismo largo se desempata por orden alfabético, para que los ids no cambien entre ejecuciones.
- **Vierose** no trae marca en su API: se lee del sufijo "– Marca" del título (`brand_from_title`, en `scrapers/common.py`).
- **Ruido de las tiendas oficiales** ("1-Pack", "1ea", "Single", "3.38 fl. oz"): se limpia antes de comparar.
- **Filtro solar:** desde el 2026-10-07 se conserva la intensidad: `FPS 50`, `SPF50` y `SPF50+` normalizan a `spf50`; SPF30 queda separado de SPF50 y de una versión sin intensidad declarada. Antes se descartaba este dato, lo que podía unir variantes incorrectas. Un GTIN compartido tampoco permite unir intensidades explícitas diferentes.
- **Un listing sin tamaño** se une al único grupo con tamaño que tenga las mismas palabras, solo si su precio está a ±30% del grupo. Así no se une una miniatura con el tamaño normal. Entre monedas, el precio se compara en pesos.
- **El id del producto** es un hash de la clave: cambiar la clave cambia los ids. Los ids que cambian quedan con un alias (ver [más abajo](#ids-estables-alias)).

## Unión por GTIN (2026-10-04)
Después del texto, `match.merge_gtin` une los grupos que comparten un GTIN (`listing.gtin`, 14 dígitos). Es transitivo (union-find) y nunca separa lo que el texto ya unió.
- **La clave del grupo unido** es la del grupo con más listings y, a igualdad, la menor en orden (`match.sortkey`). Así el id no depende del orden de carga y el grupo grande suele conservar su id.
- **`Product.matched_by`:** `"texto"` o `"gtin"` (este último: se unieron grupos por código de barras).
- **Salvaguardas** (una unión bloqueada se cuenta en `stats`; `load_ex` las devuelve):
  - **pack:** un pack con un producto suelto no se une;
  - **miniatura:** una miniatura con el tamaño normal (`es_miniatura` distinto) no se une;
  - **tamaño:** tamaños declarados distintos y no vacíos no se unen (un código compartido entre tamaños es un error de la tienda). Si un lado no declara tamaño sí se une;
  - **código repetido:** si una misma tienda pone el código en 2 o más grupos de texto distintos, el código no identifica nada y se ignora entero. Caso real: Unnie usa un mismo código para dos bálsamos Banila Co distintos (Pore Clarifying y Revitalizing) y para tres productos Boncept.
- **Medido el 2026-10-04** (base real, ¡Qué Coreana! y Unnie con GTIN): 10.329 productos antes y 10.270 después. Productos en 2 o más tiendas: 740 antes y 763 después. 59 uniones; bloqueadas: 5 por tamaño, 3 por código repetido, 3 por miniatura y 1 por pack. 65 listings cambiaron de id (59 ids). Revisión a mano de 11 uniones: todas el mismo producto y tamaño. Las 59 tienen alias.
- **Límite:** un par con el mismo número en `g` y en `ml` ("60g" contra "60ml") queda bloqueado por la regla de tamaño, aunque comparta código (3 casos hoy: Some By Mi Miracle Cream, COSRX Snail 92 y Centella Blemish Cream). No se relajó, porque no se puede confirmar sin adivinar.
- **Conflictos:** un producto con 2 o más GTIN distintos **no se separa** automáticamente. `python match.py --gtin-conflictos` lista producto, tiendas y códigos. Hoy son 6 (Anua Heartleaf 77 Toner, 2 sérums de IUNIK, Mixsoon Glacier Water, Nineless A-Control Cream y VT Pro Cica Reedle Shot 100): en todos, ¡Qué Coreana! y Unnie dan un código distinto para el mismo producto y tamaño. Parecen envases renovados o códigos por mercado, no uniones erróneas. Ninguno participó en una unión por GTIN.
- Más tiendas con GTIN (Sokobox, Rakuen, Arumi y Moonbow vía `ratings.py`) cambiarán el agrupamiento al llegar: los ids que cambien quedarán con alias, y conviene volver a medir.

## Unión por nombre parecido (2026-10-04)
Tercer criterio, después del texto y del GTIN: `match.merge_similar` une un grupo cuyas palabras están **todas** en el nombre de otro grupo de la misma marca y tamaño. Es el mismo producto escrito más corto: Ahumada pone "Ampoule Tone Brightening 100 mL" (SKIN1004) donde las tiendas coreanas ponen "SKIN1004 Madagascar Centella Tone Brightening Capsule Ampoule 100ml", y las farmacias escriben en español con otro orden ("Crema Effaclar Duo+M Unifiant 40 mL" frente a "Crema Anti-Imperfecciones Effaclar Duo +M Unifiant 40 ml").
- **Exige:** marca, tamaño declarado e igual en ambos, la misma condición de pack y de miniatura, y al menos 2 palabras en el nombre corto.
- **Salvaguardas** (cada bloqueo se cuenta en `stats` como `similar_*`):
  - **ambiguo:** el nombre corto cabe en 2 o más grupos;
  - **misma tienda:** una tienda vende los dos, así que para ella son productos distintos; se comprueba también sobre los grupos ya acumulados antes de cada unión;
  - **variante:** al nombre corto le falta una palabra de variante o formato (`VARIANT`: light, color, cream, serum, spray, kids, refill, english, rose, unscented...), un número o una sigla de 1 o 2 letras ("Duo+ M"); o solo uno de los dos menciona un filtro solar. Las intensidades SPF forman parte de la clave;
  - **precio:** los precios no se parecen (±30%; entre monedas, 0,4 a 2,5 veces).
- **No es transitivo:** un grupo se une a lo más con uno, y si el grupo largo también cabe en otro, no se une nada. La clave del unido es la del grupo con más listings, como en el GTIN. `Product.matched_by` = `"nombre"`.
- **Medido el 2026-10-04** (base real con las 6 tiendas de dermocosmética nuevas): 176 uniones; bloqueadas 184 por ambiguas, 92 por misma tienda, 227 por variante y 17 por precio. Productos en 2 o más tiendas: 1.364 → 1.449 (con alguna farmacia o tienda de dermocosmética: 333 → 377). La sección Dermocosmética quedó con 1.798 productos, 341 comparados en 2 o más tiendas.
- **Revisión a mano:** las 111 uniones de la base anterior (solo tiendas asiáticas y Ahumada) y las 72 nuevas con farmacias. Todas el mismo producto salvo dos: la crema Uriage con y sin SPF (motivó la regla del filtro solar) y un tratamiento Kundal sin aroma en el título unido con la versión "English Rose" (límite conocido: si una tienda omite el aroma o el tono, no hay cómo saberlo).
- **Los ids que cambian** quedan con alias, como con el GTIN (ver abajo).

## Ids estables: alias
El catálogo se arma en el sitio, y cualquier cambio de matching (reglas, datos o GTIN) puede cambiar ids. Para que los favoritos del navegador y los enlaces viejos sigan funcionando:
- **`listing.pid`:** el último id con que el catálogo mostró cada listing.
- **`product_alias(old_id, new_id, ts)`:** un id que ya no existe apunta al que lo reemplaza.
- **Quién escribe:** `Catalog.__init__` llama a `db.sync_aliases` al final del armado, y `get_catalog()` abre la base con `db.connect()` (timeout 60 y migraciones al día). Se escribe ahí, y no en `scrape.py`, porque los ids también cambian al editar `match.py` y reiniciar el sitio sin que corra ningún scraping. Es una sola transacción corta (el primer relleno de ~12.500 listings costó ~0,15 s). Si la base está ocupada, el alias igual vale en memoria y el siguiente armado repite el cálculo.
- **Primer relleno** (listings con `pid` vacío): la línea base es el id **por texto** anterior a GTIN y a conservar SPF (`preserve_spf=False`). Las lecturas de referencia son de solo lectura. Si la persistencia de alias falla, `Catalog.synced` queda falso y la caché reintenta después de `REFRESH`, incluso sin cambio de archivo; una cerradura serializa los armados concurrentes.
- **Reglas:**
  - un id viejo recibe alias solo si ya no es vigente;
  - si sus listings se repartieron entre varios productos, gana el que se llevó más (a igualdad, el menor id): no se puede adivinar más;
  - las cadenas se aplanan (a→b y b→c deja a→c);
  - un id vigente nunca tiene alias, así que no hay ciclos (`resolve` también se protege de uno);
  - nada se borra salvo el alias de un id que volvió a ser vigente.
- **`Catalog.resolve(pid)`:** el id actual (`pid` vigente o alias), o `None`. Medido: los 10.329 ids del catálogo anterior resuelven a un producto vigente.

## Límites conocidos (medidos el 2026-09-21)
- **Tonos de maquillaje** (cushion, corrector): no se cruzan entre tiendas.
- **Títulos en español contra títulos en inglés:** en la práctica casi no importa. De las 11 marcas de Nooki y Coreana Chile, solo Amplen se vende también en una tienda con títulos en inglés, y Amplen ya cruza bien entre esas dos tiendas.
- **Dos tiendas sin tamaño pueden unir versiones distintas** (visto en Eqqualberry Swimming Pool Toner). Se revisaron 10 de 299 uniones por precio y las 143 agrupaciones más grandes: todas correctas.
- **"Fecha corta" / "vencimiento ..." en el título** (Sokobox 180 listados, Raku 61, Quecoreana 31, medido el 2026-10-17): son unidades por vencer que la tienda publica aparte. Se agrupan con el producto normal y su precio puede salir como mejor precio y base del % de oferta. **Decisión del usuario (2026-10-17): se deja así**; no se excluyen ni se separan. Si se retoma: excluir como en Farmaloop (simple) o mostrarlas aparte (toca el matching, medir ids antes, ADR-002).

## Packs
`match.is_pack()` detecta set, kit, dúo, trío, bundle, combo, rutina, "N-pack" y "1+1" en el título, y un título que **empieza** con "Pack" ("Pack: Masajeador LED + Sérum", 79 listings que antes pasaban como productos sueltos; 2026-10-04). "Sleeping Pack", "10ea" y "Collection" NO son packs, ni "Effaclar Duo+" (una crema de La Roche-Posay: sus 13 listings caían en packs al sumar las farmacias).
- **Dónde aparecen:** no entran en Explorar ni en la comparación de un producto. Van en `/packs` (mismo explorador). Un pack se compara solo con el mismo pack en otras tiendas.
- **Enlace con sus productos** (`Catalog._link_packs`):
  - **Mismo producto x N** ("2-Pack"): enlace exacto con cantidad (`multipack_base`).
  - **Lista explícita de la tienda:** `describe.contents()` reconoce dos formatos. Uno es la lista pegada ("Nombre 30ml Nombre 50ml", tras "incluye:" o "contiene:"). El otro es el de Vierose ("Contenido del set: Nombre (50 ml) – frase."). Cada producto se muestra con su tamaño exacto (`Product.content_rows`).
  - **Por nombre:** solo si el título o la descripción nombran el producto (misma marca, nombre de 2 o más palabras), con entre 1 y 8 coincidencias. Si un nombre existe en varios tamaños, se elige el tamaño que menciona la descripción (`size_after()`). Si no se puede decidir, no se adivina.
- **Tamaños dentro del pack** (reporte del usuario: el "Pine Calming Cica Trial Kit" trae miniaturas, no los tamaños normales):
  - `Product.small_format`: el pack es mini si su título o descripción dicen mini, miniatura o trial, o si su título dice travel, sample o muestra. En la descripción, "travel" no cuenta, porque aparece también en sets de tamaño normal.
  - Las tarjetas de "Este pack incluye" dicen, por ejemplo, "En el pack: 20 ml · suelto: 50 ml", con el aviso "Ojo con los tamaños".
- **Cobertura (2026-09-21):** 269 de 644 packs enlazan al menos un producto y 39 tienen una lista explícita. La mayoría del resto no nombra sus productos (puro texto de marketing), y adivinar violaría la regla de no inventar.
- **Límite:** dos productos con casi el mismo nombre (por ejemplo "345 Relief Serum") pueden aparecer ambos en un pack.
