"""Dólar observado (mindicador.cl)."""
from scrapers.http import get


def fx_from(data):
    """Respuesta de mindicador.cl -> (fecha 'YYYY-MM-DD', pesos por dólar)."""
    last = data["serie"][0]
    return last["fecha"][:10], float(last["valor"])


def update_fx(db):
    date, usd = fx_from(get("https://mindicador.cl/api/dolar"))
    db.execute("INSERT OR REPLACE INTO fx VALUES(?,?)", (date, usd))
    db.commit()
    return date, usd
