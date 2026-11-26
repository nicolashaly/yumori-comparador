"""Firma Web Bot Auth contra los vectores del RFC 8032 (Ed25519) y del RFC 8037 (huella JWK)."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers import webbotauth as w

SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")  # RFC 8032 §7.1, prueba 1


def test_ed25519_rfc8032():
    assert w.public_key(SEED).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert w.sign(SEED, b"").hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    seed2 = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")  # prueba 2: un byte de mensaje
    assert w.sign(seed2, bytes([0x72])).hex() == (
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")


def test_thumbprint_rfc8037():
    key = w.jwk(SEED)
    assert key["x"] == "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"
    assert w.thumbprint(key) == "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k"


def test_headers_sign_the_documented_base():
    h = w.headers("https://Moonbow.cl/products.json?page=2", SEED, now=1000, nonce="n")
    params = ('("@authority" "signature-agent");created=1000;expires=1060'
              ';keyid="kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k";alg="ed25519";nonce="n";tag="web-bot-auth"')
    assert h["Signature-Agent"] == '"https://yumori.cl"'
    assert h["Signature-Input"] == f"sig1={params}"
    base = f'"@authority": moonbow.cl\n"signature-agent": "https://yumori.cl"\n"@signature-params": {params}'
    assert h["Signature"] == f"sig1=:{base64.b64encode(w.sign(SEED, base.encode())).decode()}:"


def test_directory_headers_sign_the_documented_base():
    h = w.directory_headers(SEED, "Yumori.cl", now=1000, days=1)
    params = ('("@authority";req);created=1000;expires=87400'
              ';keyid="kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k";alg="ed25519";tag="http-message-signatures-directory"')
    assert h["Signature-Input"] == f"sig1={params}"
    base = f'"@authority";req: yumori.cl\n"@signature-params": {params}'
    assert h["Signature"] == f"sig1=:{base64.b64encode(w.sign(SEED, base.encode())).decode()}:"


def test_caddyfile_directory_signature_matches_key_and_is_current():
    """La firma fija del Caddyfile debe ser de la clave publicada y no estar por vencer (se renueva con firmar-directorio)."""
    import json
    import re
    import time
    caddy = (Path(__file__).resolve().parent.parent / "Caddyfile").read_text(encoding="utf-8")
    key = json.loads(re.search(r"respond @wba `(.*?)` 200", caddy).group(1))["keys"][0]
    inp = re.search(r"header @wba Signature-Input `(.*?)`", caddy).group(1)
    assert f'keyid="{w.thumbprint(key)}"' in inp, "La firma del directorio no es de la clave publicada: regenerarla"
    expires = int(re.search(r"expires=(\d+)", inp).group(1))
    assert expires - time.time() > 14 * 86400, (
        "La firma del directorio de Web Bot Auth vence en menos de 14 días: correr `python -m scrapers.webbotauth "
        "firmar-directorio`, pegar las dos líneas en el Caddyfile y redesplegar (ADR-010)")


def test_get_signs_only_with_a_published_key():
    """get(sign=True) firma solo si la clave de este PC está en el directorio; si no, pide sin firmar (ADR-010)."""
    import json
    import tempfile
    from unittest import mock
    from scrapers import http

    class Page:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n): return self.body

    for published, signed in (([w.jwk(SEED)], True), ([{"kty": "OKP", "crv": "Ed25519", "x": "otra"}], False)):
        sent = []

        def fake_urlopen(req, timeout):
            if req.full_url.endswith("http-message-signatures-directory"):
                return Page(json.dumps({"keys": published}).encode())
            sent.append(req)
            return Page(b"{}")

        with tempfile.TemporaryDirectory() as d:
            key = Path(d) / "webbotauth.key"
            key.write_bytes(SEED)
            http._seed.cache_clear()
            with mock.patch.object(w, "KEY", key), mock.patch.object(http.urllib.request, "urlopen", fake_urlopen), \
                    mock.patch.object(http, "log", lambda m: None):
                http.get("https://moonbow.cl/products.json", sign=True)
                http.get("https://dbs.cl/x.json")  # sin sign: nunca se firma
            http._seed.cache_clear()
        assert (sent[0].get_header("Signature") is not None) is signed
        assert sent[1].get_header("Signature") is None
