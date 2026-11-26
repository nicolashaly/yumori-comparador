# ADR-009: Next.js como capa de presentación, con Python como dueño de las reglas

**Estado:** aceptada. El plan de migración se autorizó el 2026-10-07 y las fases 4 y 5 se hicieron ese día; esta decisión se registra el 2026-10-10. Activa en parte el [ADR-007](ADR-007-stack-objetivo-nextjs.md) y acota la regla de solo stdlib del [ADR-001](ADR-001-stack-stdlib-sqlite.md).

**Contexto:**
- El ADR-007 fijó Next.js como stack del producto final, pero difirió la migración hasta tener una razón concreta. Esa razón es preparar la publicación: el dominio `yumori.cl` se compró el 2026-10-06. Para publicar se necesitan componentes reutilizables, responsive, accesibilidad y SEO.
- El ADR-001 pide justificar antes cualquier librería nueva. El piloto ([migración](../architecture/migration.md), fases 4 y 5) agregó dependencias de npm sin un ADR. Este documento cubre esa falta.
- El valor de Yumori está en Python: scraping, matching, historial y reglas de precios, ya probados y con ids estables. Reescribirlo no resuelve ningún problema medido.

**Decisión:**
- **Next.js vive solo en `frontend/`:** Next.js 16 (App Router), React 19 y TypeScript. Las dependencias de ejecución son únicamente `next`, `react` y `react-dom`; las de desarrollo son `typescript` y los tipos. Las versiones exactas quedan fijadas en `package-lock.json` y se instalan con `npm ci`.
- **Python sigue sin dependencias:** la regla 1 no cambia para `scrape.py`, `scrapers/`, `db.py`, `match.py`, `catalog.py`, `server.py`, `api.py` ni `tests/`.
- **Next solo presenta.** Lee la [API de lectura v1](../architecture/read-api.md) desde el servidor, sin caché, y nunca abre SQLite. No replica `Catalog._match()`, el matching, los precios, los estados, los eventos ni los conteos: todos llegan calculados desde Python. Si falta un dato, se agrega a la API, no se calcula en TypeScript.
- **Seguridad:**
  - React escapa los textos y no se usa `dangerouslySetInnerHTML`;
  - las URLs externas se validan como HTTP/HTTPS sin credenciales;
  - la CSP usa un nonce por respuesta, sin `unsafe-inline` ni `unsafe-eval` en los scripts (`frontend/proxy.ts`), y no se relaja para resolver errores;
  - `YUMORI_API_ORIGIN` solo admite loopback.
- **Lo que queda pendiente del ADR-007** (Tailwind, shadcn/ui, Motion y Lucide) se incorpora solo cuando una ruta lo necesite, justificándolo aquí o en un ADR nuevo.
- **La migración es gradual y reversible:** el renderer Python sigue funcionando hasta la fase 7. Volver atrás es detener Next y abrir el puerto 8000; no hay migración de base que deshacer.
- **Favoritos:** se conservan los ids, `/p/<id>`, los alias y la clave `yumori:fav`. Como el puerto 3000 es otro origen, los favoritos se trasladan deliberadamente, exportándolos e importándolos desde `/favoritos`.

**Alternativas descartadas:**
- **Quedarse solo con el renderer Python:** no requiere instalar nada, pero componentes, accesibilidad y SEO crecerían como HTML hecho a mano en `server.py`.
- **Reescribir todo en Node:** se perderían el scraping y el matching probados, y con ellos la estabilidad de los ids ([ADR-002](ADR-002-matching-por-texto.md)).
- **Que Next lea SQLite directamente:** duplicaría las reglas y rompería la regla de que `Catalog._match()` es el único filtro.

**Consecuencias:**
- El sitio Python sigue funcionando sin instalar nada. Next requiere Node >= 20.9, `npm ci` y `npm run build`, con 60 paquetes en el lockfile.
- En local corren dos procesos: Python en el puerto 8000 y Next en el 3000 (configuración `yumori-next` de `.claude/launch.json`). Next sin Python muestra un aviso y nunca precios antiguos.
- npm agrega riesgo de cadena de suministro. Las actualizaciones se hacen a propósito, revisando el lockfile, y antes de publicar se corre `npm audit`.
- `frontend/app/original.css` es una copia exacta de `static/style.css`. Al cambiar el diseño se actualizan ambas; `tests/next_pilot_e2e.py` comprueba que coincidan.
- **Verificación:** `npm test`, `npm run typecheck` y `npm run build` en `frontend/`, más `python tests/run.py` y `python tests/next_pilot_e2e.py` ([pruebas del piloto](../architecture/next-pilot-testing.md)).
- **Pendiente:**
  - **fase 6, publicación:** hosting para Python y SQLite, HTTPS, origen fijo, límites, respaldos con restauración probada, permisos de tiendas y datos del operador;
  - **fase 7:** retirar el renderer Python solo después de confirmar estabilidad y paridad.
