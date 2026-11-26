# Verificación del piloto Next

La suite Python continúa con `python tests/run.py`. El chequeo HTTP del piloto se ejecuta aparte, después de instalar y compilar `frontend`:

```powershell
python tests/next_pilot_e2e.py
# Si Node no está en PATH:
python tests/next_pilot_e2e.py --node C:/ruta/node.exe
# Mantener una fixture aislada para inspección en navegador:
python tests/next_pilot_e2e.py --serve
```

El script usa únicamente stdlib. Crea SQLite en un directorio temporal, arma `Catalog(sync=False)`, levanta el handler Python real en un puerto local libre y arranca el build de Next con `YUMORI_API_ORIGIN` apuntando a esa fixture. No abre la base personal, migra datos existentes ni consulta tiendas. Ambos servidores se detienen al terminar, incluso ante fallos.

Compara HTML SSR contra el JSON de la API: IDs en el orden del listado, total, facetas y sus conteos, precio de resumen y moneda, búsqueda, filtros repetidos, stock, orden, páginas vacías y búsqueda sin resultados. La ficha verifica precios CLP y USD en unidades menores, estados disponibles/sin conexión/desaparecidos/sospechosos, ambos empates como mejor precio confirmado, metadatos de actualización y URL canónica. Comprueba respuesta 308 y destino del alias antes de seguirlo, 404 real, filtros inválidos y mensaje de caída de API sin reutilizar datos en caché.

En listado y ficha comprueba que `script-src` excluya `unsafe-inline` y `unsafe-eval`, que los scripts lleven el nonce de la cabecera CSP y que los assets JavaScript locales respondan correctamente. Permitir estilos en línea no se confunde con permitir scripts en línea.

Los atributos `data-product-id`, `data-total`, `data-price-amount`, `data-store-id` y `data-offer-status` identifican datos visibles; se comprueban dentro de su card u oferta para evitar que un precio de otra tienda haga pasar la prueba. El script falla ante discrepancias y devuelve código distinto de cero.

La paridad visual conserva el CSS original y sus cinco assets (dos fuentes y tres fondos SVG): el chequeo exige copias idénticas byte por byte y respuestas HTTP con el mismo contenido. Las categorías se presentan como chips y las facetas como checkboxes; `data-facet-name`, `data-facet-value` y `data-facet-count` asocian cada número visible con su opción. Se comparan los conteos exactos del contrato y los checks seleccionados, incluidas opciones marcadas con cero resultados. El panel mantiene los límites originales de 16 tipos y 12 ingredientes, más las opciones seleccionadas. Los chips usan `category_counts`, que conserva los filtros de búsqueda, marca y stock del renderer Python.

La fase 5 extiende la matriz a inicio, marcas, tiendas, dermocosmética, packs de ambas secciones, eventos y sus packs, privacidad, términos, cookies y favoritos. Los listados y directorios se comparan en orden contra `/api/v1/products` y `/api/v1/site`; el texto legal procede de los bloques del contrato Python. La fixture incluye productos y packs de ambas secciones. Cada observación del historial se asocia con su tienda, captura, monto y moneda mediante `data-history-store` y `data-captured-at`. Las rutas Next de favoritos y sugerencias deben devolver el mismo JSON que Python, rechazar parámetros inválidos y declarar `no-store`; una caída de Python devuelve 503. Favoritos SSR se verifica como página disponible; su interacción y persistencia requieren las pruebas JavaScript y navegador. Cinco rutas del renderer Python continúan respondiendo en esta misma fixture.

`--serve` imprime las URLs locales de Next y del renderer Python y los mantiene con esta misma SQLite temporal hasta Ctrl+C. Permite comparar diseño, teclado, favoritos y CSP sin abrir la base personal. Al finalizar detiene ambos procesos y elimina la fixture; no usar esas URLs como servidor público.

Este chequeo HTTP no ejecuta JavaScript del navegador y no certifica accesibilidad, navegación con teclado, diseño móvil ni CSP en un navegador. Esas comprobaciones requieren una revisión separada. La fixture es deliberadamente pequeña; el contrato Python cubre de manera más amplia reglas de catálogo e historial.

Verificación de cierre de fase 5: build y TypeScript en verde, suite Python completa, siete pruebas Node de favoritos y
40 comprobaciones HTTP. Revisión manual del build en el navegador con la fixture: guardar/quitar, contador,
persistencia tras recargar, exportar JSON, importar ese archivo y autocompletado con flechas/Enter hasta la ficha.
Sin errores JavaScript ni CSP en los registros de esa revisión. No constituye una auditoría WCAG ni una prueba exhaustiva
de tamaños de pantalla; esas verificaciones siguen pendientes antes de publicar.

Tras incorporar la presentación original, build y 46 comprobaciones HTTP en verde sobre la fixture aislada. Las seis comprobaciones adicionales cubren CSS y assets originales. La revisión de escritorio y móvil se realiza aparte en navegador.
