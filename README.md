# Yumori: comparador de precios de cosmética asiática

Sitio que compara precios de skincare y cosmética asiática en unas 20 tiendas chilenas e internacionales. Está publicado en **https://yumori.cl**.

> Este repositorio es una copia pública del proyecto, para mostrar el código. El desarrollo sigue en un repositorio privado.

## Qué hace

- Un bot revisa los precios de cada tienda todos los días.
- Agrupa el mismo producto aunque cada tienda lo escriba distinto, y muestra dónde está más barato.
- Guarda el historial de precios, así una "oferta" se mide contra lo que costaba antes y no contra el precio tachado de la tienda.
- Respeta las reglas de cada sitio: revisa el `robots.txt`, se identifica con un User-Agent honesto, deja de pedir si la tienda lo bloquea y nunca intenta evadir un bloqueo.
- En las tiendas Shopify, el bot firma sus peticiones con Web Bot Auth (Ed25519), como pide Shopify a los bots.

## Tecnologías

- **Backend:** Python, solo con la librería estándar, y SQLite.
- **Frontend:** Next.js con React y TypeScript. Solo muestra los datos; las reglas están en Python.
- **API:** JSON de solo lectura (`/api/v1`) que consume el frontend.
- **Despliegue:** Docker y Caddy en un servidor de AWS (EC2). GitHub Actions corre las pruebas y actualiza el servidor sin SSH ni llaves guardadas en GitHub (OIDC y AWS Systems Manager).
- **Seguridad en CI:** Semgrep, Trivy, `npm audit` y Dependabot.

## Estructura

| Archivo o carpeta | Qué hace |
|---|---|
| `scrape.py`, `scrapers/` | El bot: un adaptador por tipo de tienda (Shopify, WooCommerce y otros) |
| `match.py` | Agrupa el mismo producto de distintas tiendas |
| `db.py` | Esquema de la base y migraciones |
| `catalog.py` | Catálogo, búsqueda, filtros y ofertas |
| `api.py`, `server.py` | API JSON y servidor |
| `frontend/` | Sitio en Next.js |
| `tests/` | Pruebas |
| `docs/` | Arquitectura y decisiones técnicas ([índice](docs/README.md)) |

Las decisiones importantes están explicadas en [`docs/decisions/`](docs/decisions/), por ejemplo por qué no usar dependencias en Python o cómo se decide que dos productos son el mismo.

## Cómo probarlo

Necesitas Python 3.12 y Node.js 22.

```
python tests/run.py      # pruebas
python server.py         # sitio y API en http://127.0.0.1:8000
```

El frontend en Next.js se levanta aparte; los pasos están en [`frontend/README.md`](frontend/README.md). Sin una base con datos el sitio parte vacío; `python scrape.py <dominio>` llena la base con una tienda.

## Autoría

Lo desarrollé con apoyo de agentes de IA (Claude Code y Codex). Yo defino qué se construye, tomo las decisiones del proyecto (las que están en `docs/decisions/`) y reviso los cambios.

Nicolás Haly Arroyo
