# ADR-003: Scraping respetuoso, nunca evadir bloqueos

**Estado:** aceptada (2026-09-21).

**Decisión:**
- Revisar el robots.txt antes de agregar una tienda.
- User-Agent honesto (`YumoriBot`) y pausas entre solicitudes. Desde el 2026-10-29 enlaza a [yumori.cl/bot](https://yumori.cl/bot), que explica qué lee y cómo pedir la exclusión.
- Ante 403 o 429, `get()` lanza `Blocked` y se deja de pedir: sin reintentos, sin cambiar de identidad y sin evadir Cloudflare ni captchas.
- Se prefiere el JSON de la plataforma y los datos estructurados antes que el HTML.

**Consecuencias:**
- YesStyle se lee de a pocas marcas por corrida, con rotación.
- iHerb y YesAsia quedaron descartadas.
- MercadoLibre solo con app y token oficiales.
- Olive Young queda pospuesta.
