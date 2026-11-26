# ADR-001: Python stdlib y SQLite local

**Estado:** aceptada (2026-09-21).

**Contexto:** Yumori es un proyecto personal que corre en el PC del usuario. Se trabaja en un notebook y en un PC de escritorio, así que el repo debe ser portable.

**Decisión:**
- Python con solo la biblioteca estándar: sin dependencias, ni para el scraping, ni para el servidor, ni para las pruebas.
- SQLite en `data/yumori.db`, fuera de git.
- HTML renderizado en el servidor.
- Rutas relativas.

**Consecuencias:**
- Clonar y correr no requiere instalar nada.
- Cada PC tiene su propia base e historial.
- Una librería nueva (por ejemplo, un parser HTML) debe justificarse.
- Se cambiará a Postgres y a otro frontend solo cuando haya una razón concreta (ver [ADR-007](ADR-007-stack-objetivo-nextjs.md)).
- Desde el 2026-10-07 la presentación tiene además un frontend Next.js en `frontend/`, con dependencias de npm. La regla de solo stdlib sigue vigente para todo el Python ([ADR-009](ADR-009-frontend-nextjs.md)).
