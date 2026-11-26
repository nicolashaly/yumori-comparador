"""La caché serializa reconstrucciones y reintenta alias que no pudieron guardarse."""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import catalog
from db import connect, save, sync_aliases


def test_alias_write_failure_is_reported_and_rolls_back():
    db = connect(":memory:")
    save(db, "a.cl", [dict(ext_id="1", title="Toner", vendor="Anua", sku=None, variant=None,
                           url="https://a.cl/p", price=20000, compare_at=None, available=1)])
    lid = db.execute("SELECT id FROM listing").fetchone()[0]
    db.execute("PRAGMA query_only=ON")
    aliases, persisted = sync_aliases(db, {lid: "new"}, lambda _: "old", return_status=True)
    assert aliases == {"old": "new"} and not persisted
    assert db.execute("SELECT pid FROM listing").fetchone() == (None,)
    db.execute("PRAGMA query_only=OFF")
    aliases, persisted = sync_aliases(db, {lid: "new"}, lambda _: "old", return_status=True)
    assert persisted and db.execute("SELECT pid FROM listing").fetchone() == ("new",)
    db.close()


def test_cache_retries_unsaved_aliases_without_a_file_change():
    old = SimpleNamespace(synced=False)
    fresh = SimpleNamespace(synced=True)
    state = dict(mtime=10, built=0, catalog=old)
    path = SimpleNamespace(stat=lambda: SimpleNamespace(st_mtime=10))
    with patch.object(catalog, "_cache", state), patch.object(catalog, "DB", path), \
            patch.object(catalog.time, "time", return_value=120), patch.object(catalog, "connect") as conn, \
            patch.object(catalog, "Catalog", return_value=fresh) as build:
        assert catalog.get_catalog() is fresh
        assert catalog.get_catalog() is fresh
        build.assert_called_once()
        conn.return_value.close.assert_called_once()


def test_simultaneous_requests_build_only_one_catalog():
    fresh = SimpleNamespace(synced=True)
    state = dict(mtime=None, built=0, catalog=None)
    path = SimpleNamespace(stat=lambda: SimpleNamespace(st_mtime=10))
    barrier = threading.Barrier(6)
    results = []
    errors = []
    def request():
        try:
            barrier.wait(timeout=5)
            results.append(catalog.get_catalog())
        except Exception as error:
            errors.append(error)
    with patch.object(catalog, "_cache", state), patch.object(catalog, "DB", path), \
            patch.object(catalog, "connect"), patch.object(catalog, "Catalog", return_value=fresh) as build:
        threads = [threading.Thread(target=request) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert not errors and len(results) == 6 and all(r is fresh for r in results)
        build.assert_called_once()
