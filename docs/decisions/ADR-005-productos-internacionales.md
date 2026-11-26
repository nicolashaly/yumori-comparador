# ADR-005: Incluir productos que solo vende una tienda internacional

**Estado:** aceptada (2026-09-21, pedido del usuario: "mejor tener de todo en vez de que un usuario busque algo y no lo encuentre y se vaya").

**Contexto:** el catálogo descartaba 577 de 650 productos internacionales ya leídos, por no tener oferta chilena.

**Decisión:**
- Se incluyen todos (`Product.domestic` es False cuando no hay oferta chilena).
- Su precio es un estimado en CLP: USD × dólar observado × 1,19 (IVA), sin envío y marcado "Estimado".
- El filtro por tienda y "en 2+ tiendas" siguen siendo solo de tiendas chilenas.

**Consecuencias:**
- El id no depende de la oferta chilena: si mañana una tienda chilena vende el producto, es el mismo id y los favoritos siguen apuntando bien.
