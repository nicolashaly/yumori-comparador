# API de Yumori (server.py): solo Python estándar, sin pip install.
# Sin scraping dentro del contenedor: el scraping corre en los PC del usuario y la base se sube como archivo (docs/operations/docker-ec2.md).
FROM python:3.12-slim

# Sin .pyc (el código es de root y de solo lectura para el usuario) y con registros sin búfer.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Parches de seguridad de Debian publicados después de la última reconstrucción de python:3.12-slim (trivy-images los marca
# con "Fixed Version" aunque la imagen oficial aún no los traiga; p. ej. libzstd1, CVE-2026-124851, en noviembre de 2026).
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# UID 1000: es el del usuario por defecto de Ubuntu y Amazon Linux en EC2, así puede escribir en el ./data montado desde el host.
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin yumori

WORKDIR /app

# Solo lo que importa server.py (verificado): api, catalog, db, describe, legal, match, shipping y de scrapers/ solo dermo.py (lo usa catalog.py).
# No van tests, docs, frontend, scrape.py, ratings.py ni data/.
COPY api.py catalog.py db.py describe.py legal.py match.py server.py shipping.py ./
COPY scrapers/__init__.py scrapers/dermo.py ./scrapers/
COPY static/ ./static/

# La base vive en /app/data (db.py:7) y se monta como volumen; esta carpeta solo existe para que el contenedor arranque sin él.
RUN mkdir data && chown yumori:yumori data
VOLUME /app/data

USER yumori

# Por defecto Python escucha solo en 127.0.0.1 (YUMORI_HOST): dentro del contenedor eso basta, porque `web` comparte su red
# (network_mode: service:api en docker-compose.yml) y el puerto 8000 no se publica. Para ver la ruta de estáticos no hace falta la base.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/static/style.css', timeout=5)"]

CMD ["python", "server.py"]
