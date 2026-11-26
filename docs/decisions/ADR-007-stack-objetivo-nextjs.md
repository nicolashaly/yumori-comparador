# ADR-007: Stack objetivo diferido (Next.js)

**Estado:** aceptada como objetivo (2026-09-22, pedido del usuario: "esa lista la dejamos para el producto final, se vayan cumpliendo de a poco"). En ejecución parcial desde el 2026-10-07: Next.js, React y TypeScript están en `frontend/`; Tailwind, shadcn/ui, Motion y Lucide siguen diferidos ([ADR-009](ADR-009-frontend-nextjs.md)).

**Decisión:**
- **Stack del producto final:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, shadcn/ui, Motion y Lucide.
- **Prioridades:** responsive, accesibilidad, componentes reusables, baja densidad visual, carga rápida y SEO.
- **No se migra** hasta que haya una razón concreta (publicar, cuentas de usuario).

**Consecuencias:**
- El design system de `static/style.css` (tokens de color, spacing en base 4 px, radios y sombras) está pensado para portarse a Tailwind y shadcn: afinarlo hoy no es trabajo perdido.
- El backend (scraping, matching y SQLite) no depende del frontend.
