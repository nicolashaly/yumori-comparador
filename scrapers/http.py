"""Descarga y registro: User-Agent honesto, Blocked ante 403/429 y log en data/yumori.log."""
import functools
import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from db import DB
from scrapers import webbotauth


UA = "YumoriBot/0.1 (+https://yumori.cl/bot)"  # la página explica el bot y cómo excluirse; igual al registro de Web Bot Auth en Shopify (ADR-010)
DELAY = 10  # segundos entre requests a una misma tienda (1 s hasta el 2026-10-06, luego 3; subido por cortesía: ninguna tienda nos había bloqueado)
TIMEOUT = 30  # segundos por request
MAX_BYTES = 20_000_000  # una respuesta más grande no es un listado normal (los más pesados, de YesStyle, rondan 1 MB): se corta

LOG = DB.parent / "yumori.log"


class Blocked(Exception):
    """La tienda pidió bajar el ritmo (429) o nos cerró la puerta (403). No se reintenta ni se evade: se detiene."""


@functools.cache
def _seed():
    """Semilla para firmar con Web Bot Auth (ADR-010), solo si su clave pública está en el directorio de yumori.cl: sin eso la firma
    no se puede verificar (otro PC sin clave publicada, o el sitio caído). Se revisa una vez por corrida; si falla, se pide sin firmar."""
    if not webbotauth.KEY.exists():
        log("firma Web Bot Auth: este PC no tiene clave, se pide sin firmar")
        return None
    seed = webbotauth.KEY.read_bytes()
    try:
        keys = get(f"{webbotauth.AGENT}/.well-known/http-message-signatures-directory", tries=2)["keys"]
    except Exception as e:
        log(f"firma Web Bot Auth: no se pudo leer el directorio ({e}), se pide sin firmar")
        return None
    if webbotauth.jwk(seed)["x"] not in {k.get("x") for k in keys}:
        log("firma Web Bot Auth: la clave de este PC no está en el directorio, se pide sin firmar")
        return None
    return seed


def get(url, tries=3, text=False, sign=False):
    """sign=True firma con Web Bot Auth, como pide Shopify a los bots (ADR-010). No cambia el ritmo ni el parar ante 403/429."""
    for i in range(tries):
        try:
            headers = {"User-Agent": UA}
            if sign and (seed := _seed()):
                headers |= webbotauth.headers(url, seed)  # firma nueva en cada intento: vence a los 60 s
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise ValueError(f"respuesta de más de {MAX_BYTES // 1_000_000} MB, se descarta: {url}")
                if text:
                    return body.decode("utf-8", "replace")
                if body.lstrip()[:1] == b"<":  # HTML con 200 donde va JSON: un desafío anti-bot (bellezacoreana.cl, 2026-10-10)
                    raise Blocked("respondió HTML en vez de JSON (probable desafío anti-bot)")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise Blocked(f"HTTP {e.code} (Retry-After: {e.headers.get('Retry-After', 'no indicado')})") from e
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
        except Blocked:
            raise  # sin reintentos: insistir ante un bloqueo es evadirlo
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def log(msg):
    """Imprime y agrega al archivo data/yumori.log (con pythonw no hay consola)."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
