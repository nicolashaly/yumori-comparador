"""Web Bot Auth (RFC 9421 con tag="web-bot-auth"): firma Ed25519 de las peticiones, como pide Shopify a los bots.

Ed25519 no está en la stdlib (ADR-001): se usa la implementación de referencia del RFC 8032 §6. Es lenta (~ms por firma)
y no es de tiempo constante, lo que no importa aquí: se firma una vez por petición y la clave solo protege la identidad del bot.
Conectada a get(sign=True) para las tiendas Shopify y ratings.py: ver docs/decisions/ADR-010-web-bot-auth.md.

Uso: python -m scrapers.webbotauth directorio      (JSON para /.well-known/http-message-signatures-directory)
     python -m scrapers.webbotauth firmar-directorio  (cabeceras Signature de esa respuesta, para el Caddyfile; vencen en 90 días)
     python -m scrapers.webbotauth probar <url>    (UNA petición firmada; imprime el código HTTP)
"""
import base64
import hashlib
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from db import DB

AGENT = "https://yumori.cl"  # dominio que publica el directorio de claves
KEY = DB.parent / "webbotauth.key"  # 32 bytes de semilla Ed25519; data/ está fuera de git
LIFETIME = 60  # segundos de validez de una firma ("un minuto suele bastar", guía de Cloudflare)

# Curva Ed25519, RFC 8032 §5.1
P = 2**255 - 19
Q = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, -1, P) % P
GX = 15112221349535400772501151409588531511454012693041857206046113283949847762202
GY = 46316835694926478169428394003475163141307993866256225615783033603165251855960
G = (GX, GY, 1, GX * GY % P)


def _add(a, b):
    A, B = (a[1] - a[0]) * (b[1] - b[0]) % P, (a[1] + a[0]) * (b[1] + b[0]) % P
    C, E = 2 * a[3] * b[3] * D % P, 2 * a[2] * b[2] % P
    e, f, g, h = B - A, E - C, E + C, B + A
    return (e * f, g * h, f * g, e * h)


def _mul(s, pt):
    acc = (0, 1, 1, 0)
    while s:
        if s & 1:
            acc = _add(acc, pt)
        pt, s = _add(pt, pt), s >> 1
    return acc


def _compress(pt):
    zinv = pow(pt[2], -1, P)
    x, y = pt[0] * zinv % P, pt[1] * zinv % P
    return (y | (x & 1) << 255).to_bytes(32, "little")


def _expand(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little") & ((1 << 254) - 8) | (1 << 254)
    return a, h[32:]


def public_key(seed):
    return _compress(_mul(_expand(seed)[0], G))


def sign(seed, msg):
    a, prefix = _expand(seed)
    pub = _compress(_mul(a, G))
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % Q
    R = _compress(_mul(r, G))
    k = int.from_bytes(hashlib.sha512(R + pub + msg).digest(), "little") % Q
    return R + ((r + k * a) % Q).to_bytes(32, "little")


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def jwk(seed):
    return {"kty": "OKP", "crv": "Ed25519", "x": _b64url(public_key(seed))}


def thumbprint(key):
    """keyid: huella JWK del RFC 7638 (miembros obligatorios en orden alfabético, sin espacios)."""
    canon = json.dumps({k: key[k] for k in ("crv", "kty", "x")}, separators=(",", ":"))
    return _b64url(hashlib.sha256(canon.encode()).digest())


def headers(url, seed, now=None, nonce=None):
    """Cabeceras Signature-Agent, Signature-Input y Signature para pedir url (formato que acepta Cloudflare: sin etiqueta en Signature-Agent)."""
    created = int(time.time() if now is None else now)
    nonce = nonce or _b64url(secrets.token_bytes(32))
    agent = f'"{AGENT}"'
    params = (f'("@authority" "signature-agent");created={created};expires={created + LIFETIME}'
              f';keyid="{thumbprint(jwk(seed))}";alg="ed25519";nonce="{nonce}";tag="web-bot-auth"')
    base = f'"@authority": {urlsplit(url).netloc.lower()}\n"signature-agent": {agent}\n"@signature-params": {params}'
    sig = base64.b64encode(sign(seed, base.encode())).decode()
    return {"Signature-Agent": agent, "Signature-Input": f"sig1={params}", "Signature": f"sig1=:{sig}:"}


DIRECTORY_DAYS = 90  # vigencia de la firma del directorio (como las firmas de comerciante de Shopify); renovarla antes de que venza


def directory_headers(seed, authority, now=None, days=DIRECTORY_DAYS):
    """Signature-Input y Signature de la RESPUESTA del directorio de claves, como pide Cloudflare para registrar el bot: firma
    ("@authority";req) con tag="http-message-signatures-directory", una por clave. shortcut: se calcula en este PC con vigencia
    larga y Caddy la sirve fija, para no copiar la clave privada a la EC2; si Cloudflare exige firmas recientes, firmar en el servidor."""
    created = int(time.time() if now is None else now)
    params = (f'("@authority";req);created={created};expires={created + days * 86400}'
              f';keyid="{thumbprint(jwk(seed))}";alg="ed25519";tag="http-message-signatures-directory"')
    base = f'"@authority";req: {authority.lower()}\n"@signature-params": {params}'
    sig = base64.b64encode(sign(seed, base.encode())).decode()
    return {"Signature-Input": f"sig1={params}", "Signature": f"sig1=:{sig}:"}


def load_seed():
    if not KEY.exists():
        KEY.parent.mkdir(exist_ok=True)
        KEY.write_bytes(secrets.token_bytes(32))
    return KEY.read_bytes()


if __name__ == "__main__":
    seed = load_seed()
    if sys.argv[1:2] == ["directorio"]:
        print(json.dumps({"keys": [jwk(seed)]}))
    elif sys.argv[1:2] == ["firmar-directorio"]:
        # Líneas para el bloque @wba del Caddyfile. La firma vence en DIRECTORY_DAYS días: regenerar antes y redesplegar.
        h = directory_headers(seed, urlsplit(AGENT).netloc)
        expires = int(h["Signature-Input"].split("expires=")[1].split(";")[0])
        for name in ("Signature-Input", "Signature"):
            print(f'\theader @wba {name} `{h[name]}`')
        print(f"# vence el {time.strftime('%Y-%m-%d', time.gmtime(expires))} (UTC)", file=sys.stderr)
    elif sys.argv[1:2] == ["probar"] and len(sys.argv) == 3:
        from scrapers.http import UA
        req = urllib.request.Request(sys.argv[2], headers={"User-Agent": UA, **headers(sys.argv[2], seed)})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(r.status, r.headers.get("Content-Type"))
        except urllib.error.HTTPError as e:  # una sola petición: sin reintentos (ADR-003)
            print(e.code, e.headers.get("Retry-After"), e.read(200))
    else:
        sys.exit(__doc__)
