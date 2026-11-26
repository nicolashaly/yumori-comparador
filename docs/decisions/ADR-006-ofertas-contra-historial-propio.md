# ADR-006: Las ofertas se miden contra nuestro historial

**Estado:** aceptada (2026-10-03).

**Contexto:** el precio "antes" (tachado) de una tienda puede estar inflado. Sokobox tenía 1.139 tachados y solo 868 bajas reales.

**Decisión:**
- **La baja** (`Offer.drop`) es frente al precio más alto que vimos en los últimos 14 días (`DEAL_DAYS`). Las bajas de más de 80% y los precios fuera de rango los marca la regla única de anomalías (`db.anomaly`, desde el 2026-10-03): la oferta queda "Precio por confirmar" y no cuenta como oferta. Un precio de relleno ($1.000.000) tampoco sirve de referencia.
- **Una oferta** es una baja de al menos 10% (`DEAL_PCT`).
- **La franja del inicio** muestra productos con una baja de al menos 20% (`DEAL_SHOW`), intercalando tiendas en orden alfabético (desde el 2026-10-04; antes, tiendas con 20+ rebajados, `DEAL_MIN`).
- **Con una tienda elegida,** el filtro mira la baja propia de esa tienda.
- **Lo verifica una prueba:** el número de "Ver las N ofertas" es exactamente el total que muestra Explorar al hacer clic.

**Consecuencias:**
- Detecta solo bajas desde que existe el historial (2026-09-21).
- Una tienda que siempre muestra precio tachado, sin bajar de verdad, no aparece como oferta.
