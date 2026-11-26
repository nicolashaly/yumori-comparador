# ADR-010: Firmar las peticiones a Shopify con Web Bot Auth

**Estado:** aceptada (2026-11-24), solo para Shopify. Propuesta el 2026-10-29.

**Contexto:**
- Desde el 2026-10-21, las tiendas Shopify responden 429 (`local_rate_limited`) a la primera petición de `products.json`. Desde el 2026-05-30, [Shopify aplica sus límites más estrictos](https://shopify.dev/changelog/bots-and-agents-should-identify-themselves-via-web-bot-auth) a los bots que no firman, y pide identificarse con Web Bot Auth (RFC 9421 con `tag="web-bot-auth"`).
- Cambiar de IP o de cliente para esquivarlo está prohibido (ADR-003). Firmar no esquiva nada: identifica al bot con más precisión que el User-Agent.
- Firmar exige Ed25519, que no está en la stdlib (ADR-001).
- Según el personal de Shopify, una firma válida es "necesaria pero no suficiente": los límites más altos llegan cuando el bot queda registrado por [su formulario](https://forms.gle/V88RD31uAVirqE4e9), que revisa al operador y el caso de uso ([foro](https://community.shopify.dev/t/third-party-web-bot-auth-crawler-coralbay-uk-signature-validates-but-shopify-storefronts-return-429/38542)).
- Descartados:
  - el catálogo UCP de cada tienda (`/api/ucp/mcp`), porque sus términos prohíben guardar los resultados;
  - la API Storefront sin token, porque tiene los mismos límites para bots.

**Decisión propuesta:**
- **Ed25519 sin dependencia:** se usa la implementación de referencia del RFC 8032 §6 en `scrapers/webbotauth.py`. Se prueba contra los vectores del RFC 8032 y del RFC 8037. No es de tiempo constante, lo que da igual aquí: solo firma, en el PC propio.
- **Clave:** `data/webbotauth.key`, fuera de git. Cada PC tiene la suya, porque `data/` no se comparte. El directorio publicado lista las claves públicas de todos los PC que scrapean.
- **Directorio de claves:** `https://yumori.cl/.well-known/http-message-signatures-directory`, servido por Caddy con `Content-Type: application/http-message-signatures-directory+json`.
- **Formato:** el que acepta Cloudflare.
  - `Signature-Agent: "https://yumori.cl"`, sin etiqueta.
  - Componentes firmados: `("@authority" "signature-agent")`.
  - Parámetros: `created`, `expires` (60 s), `keyid` (huella JWK del RFC 7638), `alg="ed25519"`, `nonce` y `tag="web-bot-auth"`.
- **Sin cambios a ADR-003:** se mantienen el User-Agent `YumoriBot`, las pausas y el parar ante 403/429.

**Prueba antes de aceptar:**
1. Publicar el directorio en la EC2 y comprobar que responde.
2. Registrar el bot en el formulario de Shopify (lo hace el titular).
3. Hacer una sola petición firmada por tienda con `python -m scrapers.webbotauth probar <url>`, antes y después del registro.
4. **Si responde 200:** conectar `headers()` a `get()` solo para Shopify y aceptar este ADR. **Si sigue en 429:** mantener las tiendas pausadas y esperar sus permisos o firmas (ver abajo).

**Resultados:**
- **2026-10-29, sin publicar el directorio:** Moonbow respondió `429 local_rate_limited`.
- **2026-10-29, con el directorio publicado en yumori.cl y sin registro:** Moonbow siguió respondiendo `429 local_rate_limited`. Publicar la clave no basta: falta el formulario.
- **2026-10-29, recién enviado el formulario** (con `/bot` publicado y el User-Agent `YumoriBot/0.1 (+https://yumori.cl/bot)`), una petición firmada por tienda: Nooki y COSRX respondieron 200, y las otras 10 siguieron en 429. No es concluyente, porque Nooki también respondía 429 esa mañana y no hubo petición sin firma de control. Repetir cuando Shopify confirme el registro.
- **2026-11-02, sin confirmación de Shopify en el correo**, prueba pareada (una petición sin firma y otra firmada, 5 s después) a Nooki y COSRX: las cuatro respondieron `429 local_rate_limited`. El directorio de yumori.cl responde 200 con el tipo correcto. La firma sola no cambia nada: el bloqueo sigue hasta que Shopify apruebe el registro o las tiendas den permiso. Mientras tanto, esas tiendas quedan en `db.PAUSED`.
- **2026-11-24, sin respuesta de Shopify (ni en spam)**, la misma prueba pareada a Nooki y COSRX (`products.json?limit=1`): las cuatro respondieron 200, también las sin firma. El bloqueo de la primera petición ya no está, pero la firma no explica el cambio. Falta saber si una lectura completa (paginada) aguanta; se prueba con una sola tienda antes de sacar las demás de `db.PAUSED`.
- **2026-11-24, lectura completa de Nooki sin firma** (`python scrape.py nooki.cl`, tras la corrida diaria): `ok`, 153 variantes, 24 cambios, 0 anómalos, sin 429. Las demás siguen en `db.PAUSED` hasta probarlas una por una.
- **2026-11-24, conectada la firma** (`get(sign=True)` en `shopify.py` y `ratings.py`) y leídas firmadas, una por una, las otras 10: todas `ok` y sin un 429 (Arumi "parcial" por una baja de 150 a 93 productos, no por bloqueo). Las 11 salen de `db.PAUSED`. La firma no explica el regreso (las peticiones sin firma también pasaron), pero se deja por lo que pide Shopify y para que el registro sirva si lo aprueban.

**Cómo quedó:**
- `get(url, sign=True)` agrega la firma solo si la clave de este PC está publicada en el directorio de yumori.cl (se revisa una vez por corrida). Si este PC no tiene clave, si su clave no está publicada o si el sitio no responde, pide sin firmar y lo anota en el registro: nunca manda una firma que no se pueda verificar.
- **Otro PC que scrapee** necesita su propia `data/webbotauth.key` y agregar su clave pública al directorio de la EC2. Mientras no la publique, pide sin firmar.

**Alternativa en paralelo:** cada tienda puede emitir, desde su panel (Tienda online > Preferencias > Acceso de rastreadores), una firma para un dominio, que vence en 3 meses. Es un permiso explícito del comerciante.

**Registro en Cloudflare (2026-11-25), para Vierose y otras tiendas tras Cloudflare:**
- **Prueba previa:** una petición firmada a `https://crawltest.com/cdn-cgi/web-bot-auth` (la página de prueba de Cloudflare) respondió `401 unknown public key`: el formato de la firma es correcto y solo falta que Cloudflare conozca la clave (400 sería firma mal formada).
- **Respuesta del directorio firmada**, como exige Cloudflare: `Signature-Input`/`Signature` con `("@authority";req)`, `tag="http-message-signatures-directory"`, `keyid`, `created`, `expires` y `alg`, una firma por clave. Se verificó contra el Ed25519 nativo de Node.
  - La calcula este PC (`python -m scrapers.webbotauth firmar-directorio`) y Caddy la sirve fija: la clave privada no sale del PC. **Vigencia de 90 días: la actual vence el 2027-02-23.** Para renovarla, correr ese comando, pegar las dos líneas en el `Caddyfile` y desplegar. `tests/test_webbotauth.py` falla desde 14 días antes del vencimiento, o si la firma no es de la clave publicada.
  - Riesgo sin confirmar: la documentación de Cloudflare no fija un máximo para `expires - created`. Si rechaza una firma de 90 días, hay que firmar en el servidor (con una clave en la EC2) o acortar la vigencia.
  - El despliegue reinicia Caddy cuando cambia el `Caddyfile`, después de validarlo en un contenedor aparte (antes, un cambio del `Caddyfile` no se aplicaba hasta recrear el contenedor). La CI valida el `Caddyfile` en cada PR.
- **Formulario (lo hace el titular):** en el panel de Cloudflare, Manage Account > Configurations > pestaña "Bot Submission Form" (BotBase). Verification Method: "Request Signature"; Validation Instructions: `https://yumori.cl/.well-known/http-message-signatures-directory`; User-Agent: `YumoriBot/0.1 (+https://yumori.cl/bot)`. El estado se ve en BotBase > Submission history. La documentación no dice si basta una cuenta gratuita.
- **Límites:** que Cloudflare verifique el bot no obliga a cada sitio a dejarlo pasar (reglas WAF del dueño, Bot Fight Mode sin confirmar), y no reemplaza un permiso escrito cuando los términos lo exigen (YesStyle). Si se acepta, falta conectar `get(sign=True)` en `scrapers/woocommerce.py` para Vierose.
