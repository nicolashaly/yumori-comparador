# Frontend Next.js (fases 4 y 5)

Presentación local con Next.js 16, React 19 y TypeScript. Python mantiene reglas y SQLite. Las versiones exactas están en `package-lock.json`. Instalación según la [documentación de Next](https://nextjs.org/docs/app/getting-started/installation); requiere Node >=20.9.

Desde la raíz, en una terminal:

```powershell
python server.py
```

En otra terminal:

```powershell
cd frontend
npm ci
npm run build
npm start
```

Abrir http://127.0.0.1:3000/. Python continúa en http://127.0.0.1:8000. Para otro puerto de API, definir `YUMORI_API_ORIGIN` en el entorno o copiar `.env.example` a `.env.local`. Es una variable exclusiva del servidor. Solo admite HTTP de loopback, sin credenciales, rutas ni redirecciones.

`npm run dev` permite editar. La CSP usa nonce por respuesta, sin `unsafe-inline` ni `unsafe-eval` para scripts. Verificar con el build de producción; las herramientas de desarrollo pueden necesitar permisos que esta CSP no concede. No debilitarla para activarlas.

Inicio, listados por sección, packs, eventos, marcas, tiendas, legales y `/p/<id>` consultan la API v1 sin caché. La ficha incluye un gráfico SVG del historial (rangos de 1 día, 1 semana y 1 mes, solo las 3 tiendas más baratas hoy; geometría en `lib/chart.mjs`), despacho, relacionados y enlaces de packs. Filtros, paginación, estados, empates, precios y metadatos provienen de Python. Alias redirigen al id canónico. React escapa textos y valida URLs externas. Los errores de conexión y filtros muestran un aviso SSR con respuesta 200; productos inexistentes responden 404. Un fallo nunca conserva precios de una lectura anterior.

No se publica este piloto. El puerto 3000 es otro origen: conserva la clave `yumori:fav`, pero su almacenamiento es independiente del puerto 8000. No hay traslado de favoritos entre orígenes: la pantalla de exportar/importar se quitó el 2026-10-17 por no ser intuitiva sin cuentas de usuario (las funciones `exportIds`/`importIds` siguen en `lib/favorites.mjs`). Tampoco se incorporan aún bibliotecas de componentes o animaciones. Para volver al renderer anterior, detener Next y abrir el puerto 8000; no hay migración de base.

Verificación: `npm test` (favoritos), `npm run typecheck`, `npm run build`, `python tests/run.py` y desde la raíz `python tests/next_pilot_e2e.py`. [Detalles y límites](../docs/architecture/next-pilot-testing.md).

El diseño usa `app/original.css`, copia exacta de `../static/style.css`, y las fuentes y fondos originales en `public/static/`.
`app/style.css` contiene únicamente ajustes para los controles React, traslado de favoritos y gráfico del historial.
Al editar el diseño compartido, actualizar también la copia: la prueba HTTP comprueba su igualdad y la de fuentes y SVG.
El HTML Python continúa operativo; este checkpoint conserva la presentación de la fase 5 antes de preparar la publicación.
