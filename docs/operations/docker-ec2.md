# Desplegar con Docker en una EC2

Yumori corre en un solo servidor con dos contenedores: `api` (Python, `server.py`) y `web` (Next.js). Se levantan con `docker compose up -d --build`. Los archivos son `Dockerfile`, `frontend/Dockerfile` y `docker-compose.yml`, en la raíz del repositorio.

**Qué no hace esto:**
- **No scrapea.** El scraping sigue en los PC del usuario con las tareas programadas de Windows ([scraping diario](daily-scraping.md)). La EC2 solo recibe el archivo `yumori.db` ya armado.
- **No hace copias de seguridad.** Están en pausa a propósito: la copia de referencia de los datos es la de los PC locales. Antes de publicar de verdad hay que decidir respaldos con restauración probada (fase 6 de la [migración](../architecture/migration.md)).
- **No configura el DNS.** El dominio se apunta a la IP en el servicio de DNS (ver [Dominio y HTTPS](#dominio-y-https)). Caddy se ocupa del certificado una vez que el DNS apunta.

## Cómo se conectan los contenedores
[ADR-009](../decisions/ADR-009-frontend-nextjs.md) obliga a que Next llame a Python por loopback (`YUMORI_API_ORIGIN` solo admite `127.0.0.1`). Por eso `web` usa la red de `api` (`network_mode: "service:api"`): para los dos, `127.0.0.1:8000` es Python.
- Python escucha en `127.0.0.1` (el valor por defecto de `YUMORI_HOST`): el puerto 8000 no se publica y no se alcanza desde fuera.
- Al exterior solo sale **Caddy** (puertos 80 y 443), que reenvía a Next por `api:3000` (`web` comparte la red de `api`, así que Next es alcanzable con ese nombre). El 3000 solo se abre en el loopback de la EC2 (`127.0.0.1:3000`), para pruebas, y se declara en `api` porque `web` no tiene red propia.
- Ambos contenedores corren como usuario sin privilegios (UID 1000), sin capacidades extra, y la imagen de la API no incluye `data/`, pruebas, docs ni `frontend/`.

## Primer despliegue
1. **Instalar Docker Engine y el plugin Compose** en la instancia, según la [guía oficial](https://docs.docker.com/engine/install/) de su distribución. Con el usuario por defecto (`ubuntu` o `ec2-user`, UID 1000) no hace falta más.
2. **Clonar el repositorio** y crear la carpeta de datos antes de levantar nada:
   ```sh
   git clone https://github.com/nicolashaly/yumori.git && cd yumori
   mkdir -p data
   ```
   Si el usuario no es UID 1000, `sudo chown 1000:1000 data`. Si Docker crea `data/` solo, queda de root y Python no puede escribir.
3. **Subir la base** (ver abajo) a `data/yumori.db`.
4. **Levantar:**
   ```sh
   docker compose up -d --build
   docker compose ps          # api y web deben quedar "healthy"
   ```
5. **Dominio:** crear `.env` junto a `docker-compose.yml` con `YUMORI_DOMAIN=yumori.cl` (git lo ignora) y levantar de nuevo. Mientras el DNS no apunte a la IP, Caddy no puede sacar el certificado: ver [Dominio y HTTPS](#dominio-y-https).
6. Probar desde la propia EC2 con `curl -I http://127.0.0.1:3000` y, con el DNS listo, abrir `https://<dominio>`. Sin `data/yumori.db` Python no puede armar el catálogo y el sitio muestra "El catálogo no está disponible". Al arrancar, Python imprime un aviso de `legal.py` mientras falten los datos del titular; completarlos antes de publicar.

## Subir y actualizar la base
El `.db` viene del PC local. Copiar un SQLite en uso a mano puede dejarlo a medias: primero se saca una copia consistente (ver continuar desde otro PC), y recién esa se sube. Ejemplo, **solo como referencia** (ajustar usuario, llave e IP):
```sh
# En el PC local, desde la raíz del repositorio:
python -c "import sqlite3; s = sqlite3.connect('data/yumori.db'); d = sqlite3.connect('yumori-subir.db'); s.backup(d); d.close(); s.close()"
scp -i <llave.pem> yumori-subir.db ubuntu@<IP>:~/yumori/data/yumori.db.nueva

# En la EC2:
mv ~/yumori/data/yumori.db.nueva ~/yumori/data/yumori.db   # mv en la misma carpeta es atómico
```
### Automático al terminar el scraping (`publish_db.py`)
Al final de una corrida **completa** (`scrape.py` sin dominio), `scrape.py` llama a `publish_db.py`, que hace lo del ejemplo: copia consistente con `backup`, comprueba que no esté dañada ni vacía, la sube por `scp` como `yumori.db.nueva` y la mueve a `yumori.db` por `ssh`. Todo queda en `data/yumori.log` (`publicar: base subida ...` o `publicar: ERROR ...`). Un fallo de subida nunca interrumpe ni invalida el scraping. Sirve también a mano: `python publish_db.py`.
- **Activarlo en un PC:** crear `data/publish.json` (git lo ignora; sin ese archivo no hace nada):
  ```json
  {"host": "<IP elástica>", "user": "ubuntu", "key": "C:\ruta\llave.pem", "remote_dir": "yumori/data"}
  ```
  `remote_dir` es relativo al home del usuario de la EC2 y es opcional. La llave `.pem` no va en el repositorio. En Windows, el cliente `ssh` rechaza una llave que otros usuarios puedan leer: dejar solo tu usuario con permisos sobre el archivo.
- **Activarlo en un solo PC.** Cada PC tiene su propia base e historial: si los dos publican, el que termine último pisa la base del otro en el sitio.
- **Copia anterior:** antes de reemplazar la base, la EC2 guarda la versión previa como `data/yumori.db.anterior` (solo una). Si una corrida mala llega a publicarse: `cd ~/yumori/data && mv yumori.db.anterior yumori.db`.
- **No requiere deploy.** La base se recoge sola (siguiente párrafo); el código sí se despliega aparte al hacer push a `master` ([CI/CD](ci-cd.md)).
- **Seguridad de la EC2:** el puerto 22 debe estar abierto a la IP del PC que sube (ver [Red y security group](#red-y-security-group)). Si la IP de casa cambia, la subida falla hasta actualizar la regla.

**No hace falta reiniciar.** `catalog.get_catalog()` mira la fecha de modificación de la base en cada petición y reconstruye el catálogo cuando cambia, como máximo una vez por minuto (`REFRESH = 60`). Por eso `docker-compose.yml` monta la carpeta `data/` y no el archivo: un archivo montado seguiría apuntando a la base vieja tras el reemplazo. Si no se ve el cambio, `docker compose restart api` lo fuerza.

## Lectura y escritura
El volumen es de lectura y escritura; `:ro` **no** funciona. Verificado en el código: `db.connect()` ejecuta el esquema y las migraciones de columnas, `Catalog` anota los alias de ids en `listing.pid` y `product_alias`, y SQLite crea su archivo de journal junto a la base. Por la misma razón no se debe dejar `yumori.db` solo en lectura para el usuario del contenedor.

Para probar con una base de prueba sin tocar `./data`: `YUMORI_DATA=/ruta/de/prueba docker compose up -d --build`.

## Dominio y HTTPS
1. **DNS.** Registros `A` de `@` y `CNAME` de `www` hacia la IP elástica de la instancia, en el servicio que aloje el DNS (con un `.cl`, nic.cl solo delega los servidores de nombres). Si el DNS es Cloudflare, dejar los registros en "DNS only" (nube gris) para que Let's Encrypt llegue a Caddy. Comprobar con `nslookup <dominio>`.
2. **`.env`** con `YUMORI_DOMAIN=<dominio>` y `docker compose up -d`.
3. **Certificado.** Caddy lo pide solo la primera vez que recibe tráfico del dominio y lo renueva. Se guarda en el volumen `caddy_data`, que **no** hay que borrar: Let's Encrypt limita cuántos certificados emite por dominio. Si falla, `docker compose logs caddy`.
4. `www.<dominio>` redirige a `<dominio>`.
5. El sitio ya no es alcanzable por la IP sin el dominio: Caddy responde según el nombre de host.

HSTS (`Strict-Transport-Security`) activo desde el 2026-10-17 con `max-age` de 30 días (`frontend/proxy.ts`): un navegador que lo recibe no vuelve a abrir el sitio por HTTP durante ese plazo. Subirlo a un año cuando pase un mes sin problemas de HTTPS.

## Red y security group
- **Entrada:** 80 y 443 desde cualquier IP (`0.0.0.0/0`) y 22 solo desde la IP propia.
- **No abrir el 3000 ni el 8000.** El 3000 solo escucha en el loopback de la instancia, así que una regla pública no lo expondría, pero tampoco tiene que existir.
- Sin el 80 abierto, Let's Encrypt no puede validar el dominio.

## Comandos útiles
```sh
docker compose logs -f api web     # registros
docker compose down                # detener y quitar los contenedores (la base queda en ./data)
git pull && docker compose pull caddy && docker compose build --pull && docker compose up -d   # actualizar a mano
```
`build --pull` y `pull caddy` traen las imágenes base al día. Sin eso, Docker reusa las que tiene en caché y producción
puede quedar con una vulnerabilidad que el escaneo de CI ya no ve, porque CI siempre parte de imágenes nuevas
(zlib1g, CVE-2026-85091, en `python:3.12-slim`, 2026-11-23).
El despliegue también puede ser automático al hacer push a `master`: ver [pruebas y despliegue automático](ci-cd.md).

Los favoritos viven en el navegador de cada origen: al cambiar de `127.0.0.1:3000` a la dirección pública se trasladan exportándolos e importándolos desde `/favoritos` ([ADR-009](../decisions/ADR-009-frontend-nextjs.md)).
