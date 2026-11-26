# Escaneos de seguridad en CI (Semgrep, Trivy, npm audit y Dependabot)

Un conjunto gratuito de revisiones automáticas, parecido en espíritu a Checkmarx pero más modesto. Corren en `.github/workflows/security.yml` (workflow *Security*) en cada pull request, en cada push a `master`, **una vez por semana** (lunes 09:00 UTC) y a mano (*Run workflow*). El de cada semana existe porque aparecen vulnerabilidades nuevas en dependencias e imágenes sin que cambie una línea de código. Dependabot (`.github/dependabot.yml`) propone actualizaciones.

Es **independiente** del flujo de pruebas y despliegue ([CI/CD](ci-cd.md)): no está conectado al job `deploy` y no lo frena. Son herramientas **solo de CI**: no agregan nada a la aplicación ni a sus dependencias ([ADR-001](../decisions/ADR-001-stack-stdlib-sqlite.md), [ADR-009](../decisions/ADR-009-frontend-nextjs.md)).

Nada de esto se ha ejecutado todavía en GitHub: el flujo solo se valida con su primera ejecución real (ver el final de este documento).

## Qué hace cada pieza

| Job | Qué revisa | Qué **no** cubre |
|---|---|---|
| `semgrep` | Código Python, JavaScript, TypeScript y React; Dockerfile; workflows de GitHub Actions; secretos en el texto. Solo hallazgos `ERROR` (alta confianza). | Semgrep OSS trae menos reglas que un producto de pago como Checkmarx. Que su motor gratuito no haga análisis de flujo de datos entre archivos es lo que recuerdo de su documentación (**no verificado aquí**): esperar menos hallazgos de inyección que una herramienta comercial. No revisa dependencias. |
| `trivy-fs` | El repositorio en git: vulnerabilidades de `frontend/package-lock.json`, secretos y errores de configuración del Dockerfile. HIGH y CRITICAL, solo con versión corregida. | Que lea `docker-compose.yml` no está confirmado (su documentación nombra Dockerfile, Kubernetes, Terraform y otros, no Compose). No revisa los workflows (eso es de Semgrep). No ve nada de Python: no hay dependencias, es solo stdlib. |
| `trivy-images` | Las imágenes `yumori-api` y `yumori-web`, construidas en el job, y la imagen pública `caddy:2-alpine`: vulnerabilidades del sistema y de las librerías. HIGH y CRITICAL, solo con versión corregida. | No revisa secretos ni configuración dentro de las imágenes, ni la configuración en tiempo de ejecución del servidor. La etiqueta `2-alpine` es móvil: lo que se escanea es lo último publicado hoy. |
| `npm-audit` | `npm audit --omit=dev --audit-level=high` en `frontend/`: dependencias de producción con vulnerabilidad conocida de severidad alta o crítica. ADR-009 ya pedía correrlo antes de publicar. | Solo dependencias de producción (las de desarrollo no están en la imagen). Usa la base de avisos de npm: si el registro no responde, el job falla sin que sea un hallazgo. |
| Dependabot | Abre pull requests para actualizar `frontend/` (npm), los dos Dockerfile (imágenes base) y las acciones de `.github/workflows/`. Semanal, máximo 5 abiertos por ecosistema, mensajes `chore(deps): ...`, espera 7 días tras la publicación de una versión y agrupa en uno solo los cambios menores y de parche de npm. | No actualiza Python (no hay dependencias) ni `caddy:2-alpine` (`docker-compose.yml` no está configurado). Las imágenes base no saltan de versión mayor (y en la API tampoco de menor): cambiar de Python o de Node es manual y hay que tocar también `ci.yml`. |

Ninguna de estas herramientas reemplaza una revisión de código ni una auditoría. Encuentran lo conocido.

## Cómo leer una ejecución fallida
1. Repositorio > pestaña **Actions** > workflow *Security* > la ejecución. Los cuatro jobs salen en paralelo.
2. Abrir el job en rojo y el paso que falló. **El resultado está en el registro**, no en otra pestaña (ver *Limitaciones*).
3. Qué mirar según el job:
   - **`semgrep`**: cada hallazgo muestra el identificador de la regla (`python.lang.security....`), el archivo y la línea, y el mensaje. Si falla antes de escanear, casi siempre es la red (descarga de reglas) o la imagen.
   - **`trivy-fs`** y **`trivy-images`**: tablas con el paquete, la vulnerabilidad (CVE), la versión instalada y la **versión corregida** (*Fixed Version*). El arreglo suele ser subir esa versión en `package-lock.json` o en la imagen base. En `trivy-images`, mirar qué paso falló: `yumori-api`, `yumori-web` o `caddy:2-alpine`; los tres corren aunque uno falle. La imagen de la API hace `apt-get upgrade` al construirse: un paquete de Debian que ya tiene versión corregida se arregla solo en la próxima construcción, aunque `python:3.12-slim` no se haya reconstruido (así se resolvió `libzstd1` en noviembre de 2026).
   - **`npm-audit`**: la lista de paquetes y avisos; `npm audit fix` en `frontend/` (sin `--force`) resuelve lo que se pueda con cambios compatibles.
4. Para repetir un escaneo después de arreglar algo: **Re-run jobs**, o *Run workflow* con la rama.

## Falsos positivos
- **Semgrep, una línea concreta:** un comentario con el identificador de la regla en la misma línea o en la anterior y **siempre con el motivo**:
  ```python
  # Motivo: comando fijo, sin datos de usuarios.
  # nosemgrep: python.lang.security.audit.dangerous-system-call.dangerous-system-call
  ```
  Con el identificador completo de la regla (el que muestra el registro); un `# nosemgrep` sin regla silencia todas las de esa línea. El motivo va en su propia línea de comentario.
- **Semgrep, archivos o carpetas enteras:** `.semgrepignore` (raíz del repositorio, sintaxis de `.gitignore`). Ahora omite `.git/`, `node_modules/`, `frontend/.next/`, `tests/fixtures/` y `data/`. Al existir, reemplaza la lista por defecto de Semgrep (que omitía `tests/`); no se toca `tests/` salvo `fixtures`.
- **Trivy:** archivo `.trivyignore` en la raíz (Trivy lo busca solo; los jobs corren con el repositorio como directorio de trabajo). Una línea por CVE o regla, y cada una con **motivo y fecha de vencimiento** en el comentario de arriba, por ejemplo:
  ```
  # CVE-0000-00000: no se usa la función afectada. Revisar antes del 2027-01-31.
  CVE-0000-00000
  ```
  Trivy también permite vencimiento propio (`exp:AAAA-MM-DD` tras el identificador); no está verificado aquí, así que la fecha queda en el comentario. El archivo no existe todavía: se crea solo cuando haya un caso real.
- **`npm audit`:** se corrige subiendo la dependencia. Si no hay arreglo y el riesgo no aplica, se anota la decisión en el pull request; hoy no hay mecanismo de excepción.
- Un falso positivo se documenta en el pull request que lo silencia. No se silencia por comodidad una regla de secretos.

## Plan: empezar sin bloquear
1. **Ahora:** el workflow corre pero **no es requisito** para unir un pull request ni para desplegar. Los jobs pueden salir en rojo; es el estado esperado de la primera línea base.
2. Con la primera ejecución: leer todos los hallazgos, arreglar los reales y silenciar los falsos con motivo (arriba).
3. Cuando una ejecución completa quede en verde, más de una vez: en **Settings** > **Branches** (el mismo conjunto de reglas de `master` del [paso 5 de CI/CD](ci-cd.md)) agregar `semgrep`, `trivy-fs`, `trivy-images` y `npm-audit` como *status checks* requeridos. Los nombres solo aparecen en el buscador después de una primera ejecución.
4. **Cuidado al exigirlos:** `trivy-images` y el análisis semanal dependen de bases de vulnerabilidades que cambian cada día. Un check requerido puede ponerse rojo en un pull request que no tocó nada, solo porque salió una CVE nueva. Decidir antes quién la arregla y en cuánto tiempo, o exigir solo `semgrep` y `npm-audit`.
5. Más adelante, si el ruido es bajo: incluir también hallazgos `WARNING` de Semgrep (quitar `--severity ERROR`).

## Activar Dependabot (manual)
El archivo `.github/dependabot.yml` solo configura las **actualizaciones de versiones**. Las alertas y las actualizaciones de seguridad se encienden en la configuración:
1. Repositorio > **Settings** > **Code security** (o *Advanced Security*, según cómo lo muestre GitHub).
2. **Dependabot alerts**: *Enable*.
3. **Dependabot security updates**: *Enable* (abre pull requests para las vulnerabilidades conocidas).
4. **Dependabot version updates** se activa solo al existir el archivo en la rama por defecto (`master`).

Los pull requests de Dependabot se revisan como cualquier otro: corren las pruebas de `ci.yml` y estos escaneos. Con el despliegue automático en `master`, cada uno que se une **despliega**.

## Limitaciones
- **Repositorio privado, sin pestaña Security.** Según recuerdo (no verificado: confirmar en la documentación de GitHub), el escaneo de código de GitHub (CodeQL) y la subida de resultados SARIF a la pestaña *Security* exigen una licencia de pago en repositorios privados. Por eso no se usan: los resultados se leen solo en el registro de cada job.
- **Los escaneos de Trivy descargan su base de vulnerabilidades** de un registro público en cada ejecución. Si ese registro limita las descargas, el job falla por red y no por un hallazgo: re-ejecutar.
- **Semgrep no usa Semgrep Pro ni cuenta:** sin tareas de triaje, sin historial, sin análisis entre archivos (según recuerdo; no verificado).

## Decisiones de diseño (para quien lo mantenga)
- **Trivy corre desde su imagen oficial fijada por digest, no con `aquasecurity/trivy-action`.** Los tags de una Action de terceros pueden reescribirse después de publicados, y un digest no. Fijar por digest la versión 0.74.0 evita depender de tags mutables. (Una búsqueda web hecha al preparar esto reportó un incidente de seguridad de la cadena de suministro de Trivy en marzo de 2026; no se verificó de forma independiente, y la decisión de fijar por digest se sostiene sin él.)
- **Semgrep también corre desde su imagen, fijada por digest** (1.178.0): sin instalar Python en el runner y sin confiar en PyPI en cada corrida.
- **Las acciones de GitHub oficiales** (`actions/checkout`, `actions/setup-node`) van fijadas a un tag mayor, como `ci.yml`. Dependabot propone sus actualizaciones.
- **Para actualizar Trivy o Semgrep:** elegir una versión de al menos dos semanas, leer su digest en Docker Hub y cambiar la línea. Dependabot no está configurado para esas dos referencias (el `env:` y la imagen del job; que las cubra no está verificado), así que se revisan a mano de vez en cuando.
- **Packs de Semgrep:** `p/python`, `p/javascript`, `p/typescript`, `p/react`, `p/dockerfile`, `p/github-actions` y `p/secrets`. `p/nextjs` se probó y no devuelve reglas sin sesión de Semgrep, por eso no está.

## Lo que solo confirma la primera ejecución
- Que los siete packs de Semgrep carguen sin cuenta dentro del contenedor, y cuántos hallazgos `ERROR` dan.
- Que `trivy-fs` acepte `--skip-dirs tests/fixtures` y que revise (o ignore, sin fallar) `docker-compose.yml`.
- Que el contenedor de Trivy lea los `.tar` de `docker save` con `--input` y que descargue la base sin límite de descargas.
- Que `npm audit` no devuelva ya hallazgos altos.
- Que Dependabot acepte `cooldown` y `groups` tal como están escritos (un error aparece en **Insights** > **Dependency graph** > **Dependabot**).
