"""Una tienda fallida no deja listings, precios ni marcadores parcialmente confirmados."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import connect, save


def item(i, price):
    return dict(ext_id=str(i), sku=None, title="Toner 100ml", variant=None, vendor="Anua", url="https://a.cl/p",
                price=price, compare_at=None, available=1)


def test_failed_store_rolls_back_updates_new_listings_prices_and_metadata():
    db = connect(":memory:")
    save(db, "a.cl", [item(1, 20000)])
    original = db.execute("SELECT * FROM listing").fetchall()
    try:
        save(db, "a.cl", [item(1, 18000), item(2, 17000), {"ext_id": "broken"}], metadata=[("brand:done", "today")])
        assert False, "un item incompleto debe fallar"
    except KeyError:
        pass
    db.execute("INSERT INTO meta VALUES('error:recorded','yes')")
    db.commit()  # el commit posterior de scrape_store no debe rescatar escrituras fallidas
    assert db.execute("SELECT * FROM listing").fetchall() == original
    assert db.execute("SELECT price FROM price").fetchall() == [(20000,)]
    assert db.execute("SELECT value FROM meta WHERE key='brand:done'").fetchone() is None
    db.close()


def test_completed_store_commits_prices_and_metadata_together():
    db = connect(":memory:")
    assert save(db, "a.cl", [item(1, 20000)], metadata=[("brand:done", "today")]) == (1, 1)
    assert db.execute("SELECT value FROM meta WHERE key='brand:done'").fetchone() == ("today",)
    assert db.execute("SELECT price FROM price").fetchall() == [(20000,)]
    db.close()
