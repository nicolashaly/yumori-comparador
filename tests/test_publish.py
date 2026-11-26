"""Subida de la base a la EC2, sin red: scp y ssh se simulan."""
import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import publish_db
from db import connect, save

def item(pid):
    return dict(ext_id=str(pid), sku=None, title="Serum 30ml", variant=None, vendor="Anua", url="https://example.com/serum",
                price=1000, compare_at=None, available=1, currency="CLP")


CFG = {"host": "203.0.113.7", "user": "ubuntu", "key": "llave.pem"}


@contextmanager
def setup(config=CFG, listings=True):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        con = connect(tmp / "yumori.db")
        if listings:
            save(con, "tienda.cl", [item(1)], "2026-01-01T00:00:00+00:00")
        con.close()
        if config is not None:
            (tmp / "publish.json").write_text(json.dumps(config), encoding="utf-8")
        with patch.object(publish_db, "DB", tmp / "yumori.db"), patch.object(publish_db, "COPY", tmp / "yumori-subir.db"), \
                patch.object(publish_db, "CONFIG", tmp / "publish.json"), patch.object(publish_db, "log"):
            yield tmp


def test_without_config_does_nothing():
    with setup(config=None), patch.object(publish_db.subprocess, "run") as run:
        assert publish_db.publish() is None
        run.assert_not_called()


def test_uploads_then_moves_atomically_and_cleans_copy():
    with setup() as tmp, patch.object(publish_db.subprocess, "run") as run:
        assert publish_db.publish() is True
        scp, ssh = (call.args[0] for call in run.call_args_list)
        assert scp[0] == "scp" and scp[-1] == "ubuntu@203.0.113.7:yumori/data/yumori.db.nueva" and scp[-2] == str(tmp / "yumori-subir.db")
        assert "llave.pem" in scp and "BatchMode=yes" in scp
        assert ssh[0] == "ssh" and ssh[-1] == "cp -p yumori/data/yumori.db yumori/data/yumori.db.anterior; mv yumori/data/yumori.db.nueva yumori/data/yumori.db"
        assert not (tmp / "yumori-subir.db").exists()


def test_failed_upload_is_reported_not_raised_and_never_moves_the_db():
    error = subprocess.CalledProcessError(1, ["scp", "-i", "llave.pem", "ubuntu@203.0.113.7:x"], stderr="denied ubuntu@203.0.113.7 llave.pem")
    with setup() as tmp, patch.object(publish_db.subprocess, "run", side_effect=error) as run, patch.object(publish_db, "log") as log:
        assert publish_db.publish() is False
        assert run.call_count == 1  # el mv no se intenta si scp falló
        message = log.call_args.args[0]
        assert "denied" in message and not any(x in message for x in ("203.0.113.7", "llave.pem", "ubuntu"))


def test_empty_database_is_not_uploaded():
    with setup(listings=False), patch.object(publish_db.subprocess, "run") as run:
        assert publish_db.publish() is False
        run.assert_not_called()
