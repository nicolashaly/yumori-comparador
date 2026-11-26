"""Regresiones de SPF y uniones acumuladas entre tiendas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import connect, save
from match import key_of, load_ex
from catalog import Catalog


def fixture(rows):
    db = connect(":memory:")
    for i, (store, title, code) in enumerate(rows, 1):
        save(db, store, [dict(ext_id=str(i), sku=None, title=title, variant=None, vendor="Anua", url="u", price=20000,
                             compare_at=None, available=1, gtin=code)])
    return db


def test_spf_strengths_and_unknown_version_are_distinct():
    brands = {("anua",)}
    keys = [key_of("Anua", title, brands) for title in ("Sun Cream SPF30 50ml", "Sun Cream SPF50+ 50ml", "Sun Cream 50ml")]
    assert len(set(keys)) == 3
    assert keys[1] == key_of("Anua", "Sun Cream FPS 50 50ml", brands)
    db = fixture([("a.cl", "Sun Cream SPF30 50ml", None), ("b.cl", "Sun Cream SPF50 50ml", None),
                  ("c.cl", "Sun Cream 50ml", None)])
    assert len(load_ex(db)[0]) == 3
    db.close()


def test_gtin_does_not_override_conflicting_spf():
    db = fixture([("a.cl", "Sun Cream SPF30 50ml", "08809640734526"),
                  ("b.cl", "Sun Cream SPF50 50ml", "08809640734526")])
    groups, info = load_ex(db)
    assert len(groups) == 2 and info["stats"]["bloqueada_spf"] == 1
    db.close()


def test_accumulated_matching_never_absorbs_two_names_from_same_store():
    db = fixture([("a.cl", "Alpha Beta 50ml", None), ("a.cl", "Gamma Delta 50ml", None),
                  ("b.cl", "Alpha Beta Gamma Delta 50ml", None)])
    groups, info = load_ex(db)
    assert len(groups) == 2 and info["stats"]["similar_misma_tienda"] == 1
    assert all(len([r for r in rows if r[1] == "a.cl"]) == 1 for rows in groups.values())
    db.close()


def test_omitted_fragrance_is_not_assumed_to_be_english_rose():
    db = fixture([("a.cl", "Hair Treatment 500ml", None), ("b.cl", "Hair Treatment English Rose 500ml", None)])
    assert len(load_ex(db)[0]) == 2
    db.close()


def test_existing_spf_link_resolves_after_split():
    db = fixture([("a.cl", "Sun Cream SPF30 50ml", None), ("b.cl", "Sun Cream SPF50 50ml", None)])
    from catalog import pid_of
    legacy, _ = load_ex(db, gtin=False, preserve_spf=False)
    old = pid_of(*next(iter(legacy)))
    db.execute("UPDATE listing SET pid=?", (old,))
    db.commit()
    cat = Catalog(db)
    assert len(cat.products) == 2 and cat.resolve(old) in cat.by_id
    assert Catalog(db).resolve(old) == cat.resolve(old)
    db.close()
