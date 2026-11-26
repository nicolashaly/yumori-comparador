# Documentación de Yumori

Índice de la documentación del proyecto. Se puede abrir como vault de Obsidian (carpeta `docs/`): los enlaces son Markdown relativo, así que también funcionan en GitHub.

## Arquitectura
- [API de lectura v1](architecture/read-api.md): rutas JSON, filtros, monedas, alias y límites del contrato para el piloto Next.js.
- [Transición gradual a Next.js](architecture/migration.md): fases reversibles y base de pruebas para la continuidad con Codex.
- [Visión general](architecture/overview.md): flujo de datos, módulos, contratos entre capas y la regla del id de producto.

## Datos
- [Esquema de la base](database/schema.md): tablas, claves de `meta` y migraciones.
- [Matching y packs](database/matching.md): cómo se agrupan listings de distintas tiendas en un producto, packs y sus límites.

## Scraping
- [Arquitectura del scraping](scraping/architecture.md): adaptadores, reglas, bloqueos y estados "sin conexión" o "no aparece".
- [Agregar una tienda](scraping/adding-a-store.md): pasos.

## Sitio
- [Funciones del sitio](site/features.md): páginas, descripciones, galería, valoraciones, ofertas, buscador y diseño.
- [SEO](seo/strategy.md): metadatos, sitemap, datos estructurados y lo que falta al publicar.

## Operación
- [Desplegar con Docker en una EC2](operations/docker-ec2.md): contenedores `api` y `web`, subir la base y puertos del security group.
- [Pruebas y despliegue automático](operations/ci-cd.md): GitHub Actions corre las pruebas y actualiza la EC2 con AWS SSM (OIDC, sin SSH ni llaves); pasos de la consola de AWS, variables, protección de `master` y vuelta atrás.
- [Escaneos de seguridad en CI](operations/security-scanning.md): Semgrep, Trivy, `npm audit` y Dependabot; cómo leer un fallo, tratar falsos positivos y pasar de informativo a requisito.
- [Scraping diario](operations/daily-scraping.md): tareas programadas, registro y problemas conocidos.

## Decisiones (ADR)
- [ADR-001](decisions/ADR-001-stack-stdlib-sqlite.md): Python stdlib y SQLite local.
- [ADR-002](decisions/ADR-002-matching-por-texto.md): matching por clave de texto, sin fuzzy, con id = hash de la clave.
- [ADR-003](decisions/ADR-003-nunca-evadir-bloqueos.md): scraping respetuoso, nunca evadir bloqueos.
- [ADR-004](decisions/ADR-004-honestidad-de-datos.md): honestidad de datos (no inventar, avisar lo no confirmado, sin favoritismo).
- [ADR-005](decisions/ADR-005-productos-internacionales.md): incluir productos que solo vende una tienda internacional.
- [ADR-006](decisions/ADR-006-ofertas-contra-historial-propio.md): las ofertas se miden contra nuestro historial.
- [ADR-007](decisions/ADR-007-stack-objetivo-nextjs.md): stack objetivo (Next.js) diferido.
- [ADR-008](decisions/ADR-008-reestructuracion.md): reestructuración de carpetas y documentación (2026-10-03).
- [ADR-009](decisions/ADR-009-frontend-nextjs.md): Next.js en `frontend/` como capa de presentación; Python sigue dueño de las reglas y sin dependencias.
- [ADR-010](decisions/ADR-010-web-bot-auth.md): firmar las peticiones a Shopify con Web Bot Auth (Ed25519 en Python puro). Aceptada (2026-11-24), solo para Shopify.
