"""Base de datos de Yumori: esquema, conexión y guardado con historial de precios."""
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).parent / "data" / "yumori.db"
# Tiendas que se leen por marca y no completas (con un tope de solicitudes por corrida): que un producto no venga en una corrida no
# significa que la tienda lo sacó, solo que su marca no se leyó. Cada adaptador anota en meta '<prefijo>:<marca>' las marcas leídas
# completas, y catalog.missing() solo marca faltantes dentro de esas marcas.
BY_BRAND = {"www.yesstyle.com": "yesstyle", "www.stylevana.com": "stylevana"}
# Tiendas que solo dejan leer una parte de cada listado sin su API interna (Paris: los 30 primeros por marca; Farmaloop: 15 por página, sin
# paginación): un producto que no vino puede seguir a la venta. Como en BY_BRAND, se avisa "Sin actualizar" y no "No aparece en la tienda".
PARTIAL = {"www.paris.cl", "www.farmaloop.cl"}
# Tiendas retiradas de STORES: ya no se leen y sus listings no se muestran (sus datos quedan en la base; sacarla de aquí la devuelve).
# "Sin conexión" diría que es pasajero. Kosmeticos nos bloquea (403) desde el 2026-10-07; el dominio de K Belleza no existe desde el 2026-09-23;
# Stylevana nos bloquea (403, desde la primera solicitud) desde el 2026-10-13.
RETIRED = {"kosmeticos.cl", "kbelleza.cl", "bellezacoreana.cl", "www.stylevana.com"}
# Tiendas en pausa: la corrida completa y ratings.py no las piden, pero siguen visibles como "Sin conexión" (Catalog.stale).
# `python scrape.py <dominio>` aún las lee a mano. Las 11 tiendas Shopify pausadas por 429 (2026-10-22) volvieron el 2026-11-24,
# leídas una por una y firmadas sin un solo 429 (ADR-010).
PAUSED = set()


SCHEMA = """
CREATE TABLE IF NOT EXISTS listing(
  id INTEGER PRIMARY KEY, store TEXT NOT NULL, ext_id TEXT NOT NULL,
  sku TEXT, title TEXT, variant TEXT, vendor TEXT, url TEXT,
  image TEXT, rating REAL, reviews INTEGER, currency TEXT NOT NULL DEFAULT 'CLP', description TEXT, images TEXT,
  gtin TEXT,  -- código de barras en 14 dígitos (ver scrapers.common.gtin); NULL si la tienda no lo publica
  last_seen TEXT,  -- última corrida en que la tienda lo devolvió (ver catalog.missing)
  pid TEXT,  -- último id de producto con que el catálogo mostró este listing (ver sync_aliases)
  card_price INTEGER, card_name TEXT,  -- precio solo con tarjeta de la tienda (ej. CMR Falabella en Ahumada): dato actual, sin historial, nunca es mejor precio
  UNIQUE(store, ext_id));
CREATE TABLE IF NOT EXISTS price(
  listing_id INTEGER NOT NULL REFERENCES listing(id), ts TEXT NOT NULL,
  price INTEGER, compare_at INTEGER, available INTEGER);
CREATE INDEX IF NOT EXISTS price_listing ON price(listing_id, ts);
CREATE TABLE IF NOT EXISTS fx(date TEXT PRIMARY KEY, usd_clp REAL NOT NULL);  -- dólar observado (mindicador.cl)
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);  -- scraped:<tienda> = cuándo se leyó por última vez con éxito
CREATE TABLE IF NOT EXISTS scrape_run(  -- una fila por tienda en cada corrida: qué pasó, cuánto tardó y cuántos productos (ver scrape.py --estado)
  run TEXT NOT NULL, store TEXT NOT NULL, started TEXT NOT NULL, seconds REAL, status TEXT NOT NULL,
  items INTEGER, changed INTEGER, anomalies INTEGER, error TEXT);
CREATE INDEX IF NOT EXISTS scrape_run_store ON scrape_run(store, started);
CREATE TABLE IF NOT EXISTS brand_text(  -- descripciones de los sitios oficiales de las marcas: solo texto, nunca precio (scrapers/brand_text.py)
  source TEXT NOT NULL, ext_id TEXT NOT NULL, vendor TEXT, title TEXT, description TEXT, url TEXT, seen TEXT NOT NULL,
  PRIMARY KEY(source, ext_id));
CREATE TABLE IF NOT EXISTS product_alias(  -- id de producto que ya no existe -> el que lo reemplaza (ver sync_aliases y Catalog.resolve)
  old_id TEXT PRIMARY KEY, new_id TEXT NOT NULL, ts TEXT NOT NULL);
"""

# Reglas de anomalías de precio, en un solo lugar: las usan save() (para contarlas y anotarlas en el registro) y catalog.py (una
# oferta con precio anómalo no cuenta como mejor precio ni como oferta y se muestra "por confirmar"). Casos reales: Vierose publicó
# 13 productos a $1.000.000 (un precio de relleno para "no disponible") y días después los corrigió a su precio real.
PRICE_RANGE = {"CLP": (100, 500_000), "USD": (50, 200_000)}  # USD en centavos (US$0,50 a US$2.000). Medido el 2026-10-03: ningún precio real en CLP llega a $200.000
MAX_DROP = 80  # % de baja frente al precio de referencia que ya no se cree sin confirmar
MAX_RISE = 300  # % de subida idem (x4)


def anomaly(price, ref=None, currency="CLP"):
    """Motivo si `price` parece un error de carga y no un precio real ("fuera de rango", "bajó 94%", "subió 400%"); None si es normal.
    `ref`: precio de referencia (el anterior, o el más alto de los últimos días). Un precio 0 es un regalo o muestra, no una anomalía:
    se excluye aparte de la comparación."""
    if not price:
        return None
    lo, hi = PRICE_RANGE.get(currency, (1, float("inf")))
    if not lo <= price <= hi:
        return "fuera de rango"
    if ref and lo <= ref <= hi:  # una referencia fuera de rango (el relleno de $1.000.000) no sirve para comparar: su corrección no es una baja
        if price < ref * (1 - MAX_DROP / 100):
            return f"bajó {round(100 - 100 * price / ref)}%"
        if price > ref * (1 + MAX_RISE / 100):
            return f"subió {round(100 * price / ref - 100)}%"
    return None


def connect(path):
    if path != ":memory:":
        Path(path).parent.mkdir(exist_ok=True)
    db = sqlite3.connect(path, timeout=60)
    db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(listing)")}
    for col, typ in ("image", "TEXT"), ("rating", "REAL"), ("reviews", "INTEGER"), ("currency", "TEXT NOT NULL DEFAULT 'CLP'"), ("description", "TEXT"), ("images", "TEXT"), ("last_seen", "TEXT"), ("gtin", "TEXT"), ("pid", "TEXT"), ("card_price", "INTEGER"), ("card_name", "TEXT"):  # bases creadas antes de estas columnas
        if col not in cols:
            db.execute(f"ALTER TABLE listing ADD COLUMN {col} {typ}")
    return db


def sync_aliases(db, current, baseline, return_status=False):
    """Anota los ids de producto que cambiaron, para que los favoritos y enlaces guardados sigan funcionando. Devuelve {id viejo: id nuevo}.

    `current`: {listing_id: id de producto hoy}. `baseline`: función listing_id -> id que tendría sin el cambio de reglas (o None), solo para los listings sin
    `listing.pid` guardado (así la primera vez se anota lo que cambia entre las reglas viejas y las nuevas y no se pierde ningún favorito).
    Un id viejo recibe alias solo si ya no es vigente. Si sus listings se repartieron entre varios productos, gana el que se llevó más
    (a igualdad, el menor id): no se puede adivinar más. Las cadenas se aplanan (a->b y luego b->c deja a->c) y un id vigente nunca
    tiene alias, así que no hay ciclos. Una sola transacción corta; si la base está ocupada o es antigua, el resultado igual vale en memoria."""
    try:
        stored = dict(db.execute("SELECT id, pid FROM listing"))
        old_alias = {o: (n, t) for o, n, t in db.execute("SELECT old_id, new_id, ts FROM product_alias")}
    except sqlite3.OperationalError:  # base antigua sin la columna o la tabla: sin alias
        return ({}, False) if return_status else {}
    live = set(current.values())
    moved, upd = defaultdict(Counter), []
    for lid, new in current.items():
        old = stored.get(lid) or baseline(lid) or new
        if old != new:
            moved[old][new] += 1
        if stored.get(lid) != new:
            upd.append((new, lid))
    alias = {o: n for o, (n, _) in old_alias.items() if o not in live}  # un id vigente no necesita alias
    added = {}
    for old, c in moved.items():
        if old not in live:
            added[old] = min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    for old, new in added.items():
        for k, v in alias.items():
            if v == old:
                alias[k] = new
        alias[old] = new
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    persisted = True
    try:
        for o in old_alias.keys() - alias.keys():
            db.execute("DELETE FROM product_alias WHERE old_id=?", (o,))
        for o, n in alias.items():
            if o not in old_alias or old_alias[o][0] != n:
                db.execute("INSERT INTO product_alias VALUES(?,?,?) ON CONFLICT(old_id) DO UPDATE SET new_id=excluded.new_id, ts=excluded.ts", (o, n, ts))
        db.executemany("UPDATE listing SET pid=? WHERE id=?", upd)
        db.commit()
    except sqlite3.OperationalError:  # ocupada o de solo lectura: el próximo armado repite el cálculo
        db.rollback()
        persisted = False
    return (alias, persisted) if return_status else alias


def short_read(db, store, n):
    """Si una lectura de `n` productos quedó incompleta, la hora de la lectura anterior (para anotarla como last_seen); si no, None.

    Incompleta = trajo menos del 80% de la anterior (sus listings con el last_seen más reciente): un bloqueo a mitad de camino (el
    `except Blocked` de jumpseller()), productos que fallaron por red o una paginación cortada sin error. Los precios se guardan igual,
    pero la lectura no cuenta como nueva para decidir qué dejó de listar la tienda (catalog.missing): que falte un quinto de golpe es
    mucho más probable que sea una lectura cortada que una tienda que sacó un quinto de su catálogo. Las tiendas de BY_BRAND quedan
    fuera: se leen por marca a propósito (ver catalog.missing())."""
    prev_at, prev_n = db.execute("SELECT last_seen, COUNT(*) FROM listing WHERE store = ? AND last_seen = "
                                 "(SELECT MAX(last_seen) FROM listing WHERE store = ?)", (store, store)).fetchone()
    return prev_at if store not in BY_BRAND and prev_n and n < 0.8 * prev_n else None


def save(db, store, items, seen_at=None, anomalies=None, metadata=()):
    """Guarda items; solo inserta un precio nuevo si cambió respecto al último. Devuelve (total, cambios).
    `seen_at`: hora a anotar como last_seen si no es esta (lectura incompleta: ver short_read).
    `anomalies`: si es una lista, se le agrega (título, motivo) por cada precio nuevo que parece un error de carga (ver anomaly())."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = changed = 0
    with db:  # los listings, precios y marcadores se confirman juntos; un error revierte toda la tienda
        for it in items:
            lid = db.execute(
                """INSERT INTO listing(store, ext_id, sku, title, variant, vendor, url, image, rating, reviews, currency, description, images, gtin, last_seen, card_price, card_name)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(store, ext_id) DO UPDATE SET sku=excluded.sku, title=excluded.title,
                     variant=excluded.variant, vendor=excluded.vendor, url=excluded.url,
                     image=COALESCE(excluded.image, image), rating=COALESCE(excluded.rating, rating),
                     reviews=COALESCE(excluded.reviews, reviews), currency=excluded.currency,
                     description=COALESCE(excluded.description, description), images=COALESCE(excluded.images, images), gtin=COALESCE(excluded.gtin, gtin),
                     last_seen=excluded.last_seen,
                     card_price=excluded.card_price, card_name=excluded.card_name  -- sin COALESCE: una oferta con tarjeta que termina vuelve a NULL
                   RETURNING id""",
                (store, it["ext_id"], it["sku"], it["title"], it["variant"], it["vendor"], it["url"],
                 it.get("image"), it.get("rating"), it.get("reviews"), it.get("currency", "CLP"), it.get("description"), it.get("images"), it.get("gtin"), seen_at or ts,
                 it.get("card_price"), it.get("card_name")),
            ).fetchone()[0]
            last = db.execute(
                "SELECT price, compare_at, available FROM price WHERE listing_id=? ORDER BY ts DESC, rowid DESC LIMIT 1",
                (lid,),
            ).fetchone()
            cur = (it["price"], it["compare_at"], it["available"])
            total += 1
            if last != cur:
                db.execute("INSERT INTO price VALUES(?,?,?,?,?)", (lid, ts, *cur))
                changed += 1
                why = anomaly(it["price"], last[0] if last else None, it.get("currency", "CLP"))
                if why and anomalies is not None:
                    anomalies.append((it["title"], why))
        db.executemany("INSERT OR REPLACE INTO meta VALUES(?,?)", metadata)
    return total, changed


def done_today(db):
    """True si una corrida completa ya terminó hoy (hora local). Para `--diario`: la tarea al iniciar sesión puede dispararse
    varias veces al día; solo cuenta una corrida completa, así que una que se cortó (PC apagado) se repite al volver a prenderlo."""
    row = db.execute("SELECT value FROM meta WHERE key = 'run:done'").fetchone()
    return bool(row) and datetime.fromisoformat(row[0]).astimezone().date() == datetime.now().astimezone().date()
