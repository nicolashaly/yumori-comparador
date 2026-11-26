# ADR-002: Matching por clave de texto, sin fuzzy, con id = hash de la clave

**Estado:** aceptada (2026-09-21).

**Contexto:** entre tiendas coinciden solo ~22 SKUs. Los títulos varían ("50ml" o "50 ml", con o sin marca, promos).

**Decisión:**
- Un producto se identifica por la clave (marca, palabras normalizadas sin ruido, tamaños, es_miniatura), en `match.key_of`.
- Sin fuzzy matching, porque une productos distintos.
- La unión de un listing sin tamaño exige un precio a ±30% del grupo.
- El id de producto es un hash de la clave.

**Consecuencias:**
- Hay falsos negativos aceptados, como los tonos de maquillaje.
- **Cambiar la clave cambia los ids y borra los favoritos del navegador:** todo cambio de matching se mide con la base real antes de aplicarlo.

## Enmienda (2026-10-04): el GTIN entra como segundo criterio, con alias
**Contexto:** `listing.gtin` ya lo publican algunas tiendas. De 134 códigos en 2 o más tiendas, 69 estaban en productos distintos por diferencias de texto, y 6 productos mezclaban 2 códigos.

**Decisión:**
- Después del texto, los grupos que comparten GTIN se unen (transitivo), salvo con las salvaguardas de pack, miniatura, tamaño y código repetido por una tienda. La clave del grupo unido es la del grupo con más listings y, a igualdad, la menor en orden. El texto sigue siendo el criterio principal: el GTIN solo une, nunca separa.
- Cada producto guarda cómo se agrupó (`Product.matched_by`: `texto` o `gtin`). Los productos con 2 o más GTIN se listan con `python match.py --gtin-conflictos` y no se separan.
- **Los ids que cambian quedan con alias** (`listing.pid`, `product_alias` y `Catalog.resolve`), así que el cambio no borra favoritos y sirve también para cualquier cambio de matching futuro. El id sigue siendo el hash de la clave. Detalle en [matching](../database/matching.md).

**Consecuencias:**
- Los favoritos y enlaces guardados se resuelven con `Catalog.resolve`: el sitio debe usarlo (redirección de `/producto/<id viejo>` y favoritos).
- El catálogo escribe en la base al armarse (una transacción corta de alias).
- Cuando lleguen más tiendas con GTIN conviene volver a medir.
