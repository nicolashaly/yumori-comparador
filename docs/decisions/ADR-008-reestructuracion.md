# ADR-008: Reestructuración de carpetas y documentación

**Estado:** aceptada (2026-10-03, pedido del usuario: "más organización y pensado en mantenimiento a futuro").

**Contexto:**
- Un prompt de reestructuración proponía un monorepo (`apps/` + `packages/`), pnpm, Postgres, Playwright y un modelo de 10 entidades.
- Yumori tiene ~4.000 líneas de Python stdlib, corre en local y es de un solo usuario.
- Sus problemas reales eran otros:
  - `scrape.py` mezclaba descarga, adaptadores, esquema y corrida;
  - las pruebas estaban en la raíz;
  - `CLAUDE.md` tenía cientos de líneas de historia.

**Decisión:**
- **Código:**
  - `db.py` (esquema y persistencia);
  - `scrapers/` (un archivo por plataforma, más `http.py` y `common.py`);
  - `tests/` con `run.py`.
- **Puntos de entrada en la raíz:** `scrape.py`, `server.py` y `ratings.py` siguen ahí, así no cambian ni la tarea programada ni `.claude/launch.json`.
- **Documentación:** `CLAUDE.md` queda corto, con reglas y mapa, y el detalle va en `docs/` (abrible como vault de Obsidian).
- **No se adopta** lo que no resuelve un problema actual: monorepo, pnpm, Turborepo, Postgres, Playwright, API aparte, fuzzy matching, panel de admin, CI/CD ni SEO antes de publicar.

**Verificación:**
- los 9.575 ids de producto quedaron idénticos;
- las 7 pruebas pasan sin red;
- una corrida real de una tienda funcionó.

**Siguientes fases** (ver la hoja de ruta): la fase 3 (`scrape_run`, anomalías y límites) quedó hecha el mismo día. Falta GTIN/EAN.
