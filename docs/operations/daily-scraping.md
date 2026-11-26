# Scraping diario

## Tareas programadas (Windows)
`install_schedule.ps1` registra dos tareas del usuario actual, sin permisos de administrador. Corren con `pythonw.exe` (sin ventana) y dejan registro en `data/yumori.log`.

| Tarea | Cuándo | Qué corre |
|---|---|---|
| `Yumori-scrape` | Todos los días a las 07:00 (por defecto) **y** 2 min después de iniciar sesión | `scrape.py --diario` |
| `Yumori-ratings` | Domingos 10:00 | `ratings.py` (~5 horas, 5 s entre fichas) |

- **Hora del PC:** la del sistema, que es la de Chile (`America/Santiago`, con cambio de horario incluido).
- **Cambiar la hora:** `powershell -ExecutionPolicy Bypass -File install_schedule.ps1 -Hora 09:00`.
- **Dos disparadores:** el de las 07:00 solo falló en el notebook (ver abajo) y el de inicio de sesión solo no corre si el PC no se reinicia ni se vuelve a iniciar sesión (suspender no cuenta; pasó el 2026-10-24). Con los dos, `scrape.py --diario` se omite si ya hubo una corrida completa ese día (`done_today`). Una corrida cortada no cuenta y se repite.
- **Quitar las tareas:** `Unregister-ScheduledTask -TaskName Yumori-scrape,Yumori-ratings -Confirm:$false`.

## Qué PC hace qué (al 2026-10-03)
- **Desde el 2026-10-24, el scraping y la subida a la EC2 se hacen solo desde el PC de escritorio.** Ahí corren las tareas (con los dos disparadores) y está `data/publish.json`. Es la única máquina que acumula el historial que se publica.
- **Notebook:** solo desarrollo. No debe tener las tareas registradas ni `data/publish.json`, para no hacer dos lecturas ni subir una base distinta. Su base propia (desde el 2026-09-21) quedó sin actualizar. Antes tuvo la tarea a las 07:00 (varios días no corrió sola aunque el PC estaba encendido) y desde el 2026-10-03 con `-AlIniciar`, opción que ya no existe.
- El PC de escritorio se clonó el 2026-09-27 con base propia (sin el historial del notebook).
- Si el notebook aún tiene las tareas: `Unregister-ScheduledTask -TaskName Yumori-scrape,Yumori-ratings -Confirm:$false`.
- Cada máquina tiene su propia base y su propio historial: `data/` no va en git.

## Duración típica de una corrida completa
~2 h 15 min desde el 2026-10-06, cuando se alargaron las pausas por cortesía (antes ~58 min). La tarea programada se corta a las 8 h (`-ExecutionTimeLimit` en `install_schedule.ps1`).
- **Pausas** (2026-10-06, pedido del usuario dos veces: más lento, para no saturar a las tiendas): 10 s entre páginas de una misma tienda (`http.DELAY`; era 1 s y luego 3 s), 5 s entre fichas de Jumpseller (`JUMPSELLER_DELAY`; era 1,5 s y luego 2,5 s), 5 s entre fichas en `ratings.py`, 10 a 20 s en las farmacias y tiendas grandes, y 90 s en YesStyle (era 45 s). Ninguna tienda chilena nos había bloqueado: es margen. Las tiendas se leen de a una, nunca en paralelo.
- Las tiendas chilenas tardan ~2-5 min.
- `unniebeauty.cl` tarda ~80 min (una ficha por producto, a 5 s cada una).
- Las 6 tiendas de dermocosmética nuevas, ~12 min en total (10 a 20 s entre páginas).
- Las tiendas oficiales tardan segundos.
- Stylevana (~13 min) se retiró el 2026-10-15: nos bloquea con 403 (ver tiendas).
- YesStyle tarda ~7 min: el sitemap y 4 marcas con 90 s de pausa (`YESSTYLE_MAX_BRANDS`), y para antes de su límite.

## Publicación en el sitio
Si el PC tiene `data/publish.json`, la corrida completa termina subiendo la base a la EC2 (`publish_db.py`; ver [Docker en EC2](docker-ec2.md#automático-al-terminar-el-scraping-publish_dbpy)). Sin ese archivo no se sube nada.

## Revisar cómo fue
- **Resumen por tienda:** `python scrape.py --estado`. Muestra la última lectura de cada una, con su estado (`ok`, `parcial`, `vacía` o `error`), duración, productos, cambios, precios anómalos y error. Se guarda en la tabla `scrape_run`.
- **El registro:** `data/yumori.log`. Cada tienda deja "N variantes, M con cambios" o `ERROR ...`, y la corrida termina con "scrape: fin".
- **El estado de la tarea:** `Get-ScheduledTask -TaskName Yumori-scrape | Get-ScheduledTaskInfo`.
  - `LastTaskResult` 0: terminó bien.
  - `0x8007042B` o `0x40010004`: se cortó porque el PC se apagó o suspendió.
- **Muchos "con cambios" en una tienda** suelen ser ofertas reales o el regreso de una tienda. Lo que cuenta como cambio es una fila nueva en `price`, que también se escribe cuando solo cambia el stock o el "antes".

## Problemas conocidos y su causa
- **Corridas cortadas a medias:** el notebook se suspendía por inactividad (primero se cae el Wi-Fi). `scrape.py` ahora pide a Windows que no se suspenda mientras corre, pero eso no evita que se suspenda al cerrar la tapa.
- **Una tienda falla:** se anota `ERROR` en el registro y la corrida sigue con las demás. Si deja de responder, el sitio la marca como "Sin conexión" (ver [arquitectura del scraping](../scraping/architecture.md#estados-no-confirmados)).
- **YesStyle "HTTP 429":** es esperado. Corta la corrida de YesStyle y guarda lo ya leído.
- **"database is locked":** se evita con transacciones cortas y `timeout=60`.
