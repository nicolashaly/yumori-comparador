"""Sube la base a la EC2 tras un scraping completo (ver docs/operations/docker-ec2.md).

Uso: python publish_db.py     (también lo llama scrape.py al terminar una corrida completa)

Solo corre si existe data/publish.json (git no lo guarda; activa la subida en ESE PC y en ningún otro):
    {"host": "<IP elástica>", "user": "ubuntu", "key": "C:\\\\ruta\\\\llave.pem", "remote_dir": "yumori/data"}
`remote_dir` es relativo al home del usuario y es opcional. El sitio no necesita reinicio: Catalog recarga solo al cambiar el archivo.
"""
import json
import sqlite3
import subprocess
import sys

from db import DB
from scrapers.http import log

CONFIG = DB.parent / "publish.json"
COPY = DB.parent / "yumori-subir.db"
SSH = ["-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30", "-o", "StrictHostKeyChecking=accept-new"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # con pythonw no debe abrirse una consola por cada comando


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1800, creationflags=NO_WINDOW)


def snapshot():
    """Copia consistente de la base (backup de SQLite) y comprobación de que no está vacía ni dañada."""
    COPY.unlink(missing_ok=True)
    src, dst = sqlite3.connect(DB), sqlite3.connect(COPY)
    try:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or not dst.execute("SELECT COUNT(*) FROM listing").fetchone()[0]:
            raise RuntimeError("la copia está dañada o vacía")
    finally:
        dst.close(); src.close()


def publish():
    """-> True si la base quedó subida; None si no está configurado; False si falló (nunca lanza: no debe romper el scraping)."""
    if not CONFIG.exists():
        return None
    cfg = {}
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        target = f"{cfg['user']}@{cfg['host']}"
        remote = cfg.get("remote_dir", "yumori/data").strip("/")
        opts = ["-i", cfg["key"], *SSH]
        snapshot()
        run(["scp", "-C", *opts, str(COPY), f"{target}:{remote}/yumori.db.nueva"])
        # Se guarda la versión anterior (una sola) por si una corrida mala llega a publicarse; mv en la misma carpeta es atómico.
        run(["ssh", *opts, target, f"cp -p {remote}/yumori.db {remote}/yumori.db.anterior; mv {remote}/yumori.db.nueva {remote}/yumori.db"])
        log("publicar: base subida")
        return True
    except Exception as e:
        text = (getattr(e, "stderr", "") or str(e)).strip()
        for secret, mask in ((cfg.get("key"), "<llave>"), (cfg.get("host"), "<host>"), (cfg.get("user"), "<usuario>")):
            if secret:  # el log no debe guardar la IP del servidor, el usuario ni la ruta de la llave
                text = text.replace(str(secret), mask)
        log(f"publicar: ERROR {text}"[:300])
        return False
    finally:
        COPY.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(0 if publish() is not False else 1)
