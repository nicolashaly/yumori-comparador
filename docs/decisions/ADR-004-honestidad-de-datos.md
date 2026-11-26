# ADR-004: Honestidad de datos

**Estado:** aceptada (decisiones del usuario entre el 2026-09-21 y el 2026-10-03).

**Decisión:**
- **No inventar:** si una tienda no nombra los productos de un pack, no se enlazan. Una descripción sin datos no se muestra. No se nombran eventos (CyberDay) que los datos no traen.
- **Lo no confirmado se avisa con texto neutro y no cuenta como mejor precio:** "Sin conexión", "No aparece en la tienda", "Sin actualizar", "Precio por confirmar" (un precio que parece un error de carga, ver `db.anomaly`) y "Estimado".
- **Sin favoritismo:**
  - en un empate, botones en orden alfabético;
  - el banner de ofertas, en orden alfabético;
  - "Tiendas" sin ranking;
  - lo patrocinado irá siempre marcado.
- **Valoraciones por tienda, sin mezclarlas:** nunca el texto de las reseñas ni un "0", y la nota en la card solo con 5 o más reseñas.
- **Las descripciones son propias:** se extraen datos y se redacta con plantillas, sin copiar ni parafrasear.

**Consecuencias:** se pierde algo de cobertura (packs y descripciones) a cambio de no mostrar datos falsos.
