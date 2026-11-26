import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

from match import key_of

BRANDS = {("cosrx",), ("beauty", "of", "joseon")}


def k(vendor, title):
    return key_of(vendor, title, BRANDS)


def test_same_product_different_names():
    a = k("CosRx", "COSRX Advanced Snail 96 Mucin Power Essence 100ml")
    b = k("rakuencosmeticacoreana", "Cosrx Advanced Snail 96 Mucin Power Essence 100ml")  # vendor = nombre de tienda
    c = k("Cosrx", "Advanced Snail 96 Mucin Power Essence 100 ml")
    assert a == b == c
    s1 = k("Beauty of Joseon", "Beauty of Joseon Protector Solar Relief Sun Rice + Probiotics FPS 50 50ml")
    s2 = k("Rakuen", "Beauty Of Joseon Relief Sun: Rice + Probiotics (SPF50+ PA++++) 50ml")
    assert s1 == s2


def test_different_products_stay_apart():
    full = k("Cosrx", "Advanced Snail 96 Mucin Power Essence 100ml")
    mini = k("Cosrx", "(Miniatura) Advanced Snail 96 Mucin Power Essence 20ml")
    other_size = k("Cosrx", "Advanced Snail 96 Mucin Power Essence 25ml")
    assert len({full, mini, other_size}) == 3


def test_one_pack_is_ignored_but_two_pack_is_not():
    a = k("Beauty of Joseon", "Relief Sun Aqua-Fresh : Rice + B5 (SPF50+ PA++++) 1-Pack")
    b = k("Beauty of Joseon", "Relief Sun Aqua Fresh Rice B5 SPF50+ PA++++")
    c = k("Beauty of Joseon", "Relief Sun Aqua-Fresh : Rice + B5 (SPF50+ PA++++) 2-Pack")
    assert a[1] == b[1] and c[1] != a[1]


def test_official_store_variant_noise_is_ignored():
    off = k("Cosrx", "Advanced Snail Glass Glow Hydrogel Mask (1ea)")
    dom = k("Cosrx", "Advanced Snail Glass Glow Hydrogel Mask")
    assert off == dom and k("Cosrx", "Advanced Snail Glass Glow Hydrogel Mask (3ea)") != dom  # 3 unidades es otro producto
    assert k("Beauty of Joseon", "Green Plum Refreshing Cleanser 3.38 fl. oz 100 ml") == k("Beauty of Joseon", "Green Plum Refreshing Cleanser 100ml")
    assert k("Cosrx", "Eye Patch 100 g 3.52 oz")[2] == ("100g",)  # tamaño en oz descartado si hay g
    assert k("Cosrx", "Invisible Sunscreen Single") == k("Cosrx", "Invisible Sunscreen")


def test_sizeless_foreign_offer_merges_by_price_in_pesos():
    from match import load
    from db import connect, save

    def item(i, title, price, cur):
        return dict(ext_id=str(i), sku=None, title=title, variant=None, vendor="Anua", url="u", price=price,
                    compare_at=None, available=1, currency=cur)

    db = connect(":memory:")
    db.execute("INSERT INTO fx VALUES('2026-09-21', 958.42)")
    save(db, "a.cl", [item(1, "Anua Toner 250ml", 22000, "CLP")])
    save(db, "yes.com", [item(2, "Anua Toner", 1900, "USD")])  # US$19 = ~$21.700 con IVA: mismo producto, sin tamaño
    save(db, "yes.com", [item(3, "Anua Toner", 400, "USD")])  # US$4 = ~$4.600: una miniatura, no se une
    sizes = sorted(len(v) for v in load(db).values())
    assert sizes == [1, 2], sizes


def test_sizeless_merge_needs_similar_price():
    from match import load
    from db import connect, save

    def item(i, title, price):
        return dict(ext_id=str(i), sku=None, title=title, variant=None, vendor="Anua",
                    url="u", price=price, compare_at=None, available=1)

    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Anua Cleansing Oil 200ml", 30000)])
    save(db, "b.cl", [item(2, "Anua Cleansing Oil", 28000)])  # mismo producto sin tamaño: se une
    save(db, "c.cl", [item(3, "Anua Cleansing Oil", 6000)])  # precio muy distinto: otro tamaño, no se une
    sizes = sorted(len(v) for v in load(db).values())
    assert sizes == [1, 2], sizes


def _gtin_db(*rows):
    """rows: (tienda, título, gtin) -> base con esos listings (vendor Anua, mismo precio)."""
    from db import connect, save
    db = connect(":memory:")
    for i, (store, title, code) in enumerate(rows):
        save(db, store, [dict(ext_id=str(i), sku=None, title=title, variant=None, vendor="Anua", url="u", price=20000, compare_at=None,
                              available=1, gtin=code)])
    return db


G1, G2 = "08809640734526", "08809640734533"


def test_gtin_joins_groups_the_text_keeps_apart():
    from match import load, load_ex
    db = _gtin_db(("a.cl", "Anua Heartleaf Toner 250ml", G1), ("b.cl", "Heartleaf 77 Soothing Toner Calming 250 ml", G1),
                  ("c.cl", "Heartleaf 77 Soothing Toner Calming 250 ml", None))
    by_text = load(db, gtin=False)
    assert len(by_text) == 2
    groups, info = load_ex(db)
    assert len(groups) == 1 and info["stats"]["uniones"] == 1 and len(next(iter(groups.values()))) == 3
    assert list(groups) == [max(by_text, key=lambda k: len(by_text[k]))]  # la clave es la del grupo con más listings
    assert list(groups) == list(load_ex(db)[0])  # determinista
    assert all(info["origin"][r[0]] in by_text for rows in groups.values() for r in rows)  # origin: la clave de texto de cada listing


def test_gtin_never_joins_a_pack_a_mini_or_another_size():
    from match import load_ex
    for a, b, why in [("Anua Toner 250ml", "Anua Toner Set 250ml", "pack"), ("Anua Toner 250ml", "Anua Toner Mini 250ml", "miniatura"),
                      ("Anua Toner 250ml", "Anua Toner Calming 500ml", "tamaño")]:
        groups, info = load_ex(_gtin_db(("a.cl", a, G1), ("b.cl", b, G1)))
        assert len(groups) == 2 and info["stats"]["uniones"] == 0 and info["stats"][f"bloqueada_{why}"] == 1, (why, dict(info["stats"]))


def test_gtin_used_twice_by_one_store_identifies_nothing():
    from match import load_ex
    groups, info = load_ex(_gtin_db(("a.cl", "Anua Heartleaf Serum 30ml", G1), ("a.cl", "Anua Heartleaf Cream 50ml", G1), ("b.cl", "Anua Heartleaf Cream 50ml", G1)))
    assert len(groups) == 2 and info["stats"]["bloqueada_codigo_repetido"] == 1 and info["stats"]["uniones"] == 0


def test_product_with_two_gtins_is_not_split_and_is_listed_as_conflict():
    from match import gtin_conflicts, load
    groups = load(_gtin_db(("a.cl", "Anua Heartleaf Toner 250ml", G1), ("b.cl", "Anua Heartleaf Toner 250ml", G2)))
    assert len(groups) == 1  # el texto lo unió y el GTIN no lo separa
    (key, codes), = gtin_conflicts(groups)
    assert sorted(codes) == [G1, G2] and codes[G1] == [("a.cl", "Anua Heartleaf Toner 250ml")]


def test_similar_joins_a_shorter_name_of_the_same_brand_and_size():
    from match import load_ex
    db = _gtin_db(("a.cl", "Heartleaf Pore Control Cleansing Oil 200ml", None), ("b.cl", "Anua Heartleaf Pore Control Cleansing Oil Renewed 200ml", None),
                  ("c.cl", "Anua Heartleaf Pore Control Cleansing Oil Renewed 200ml", None))
    groups, info = load_ex(db)
    assert len(groups) == 1 and info["stats"]["similar_uniones"] == 1
    (w, absorbed), = info["similar"].items()
    assert "renewed" in w[1] and len(absorbed) == 1  # gana el grupo con más listings
    assert list(groups) == list(load_ex(db)[0])  # determinista


def test_similar_never_joins_when_in_doubt():
    from match import load_ex
    for rows, why in [
        ((("a.cl", "Anua Heartleaf Toner 250ml"), ("b.cl", "Anua Heartleaf Toner Calming 250ml"), ("c.cl", "Anua Heartleaf Toner Pore 250ml")), "ambiguo"),
        ((("a.cl", "Anua Heartleaf Toner 250ml"), ("a.cl", "Anua Heartleaf Toner Calming 250ml")), "misma_tienda"),
        ((("a.cl", "Anua Heartleaf Toner 250ml"), ("b.cl", "Anua Heartleaf Toner Light 250ml")), "variante"),
        ((("a.cl", "Anua Heartleaf Toner 250ml"), ("b.cl", "Anua Heartleaf Toner M 250ml")), "variante"),
        ((("a.cl", "Anua Heartleaf Barrier Cream 40ml"), ("b.cl", "Anua Heartleaf Barrier Cream Cobre SPF50+ 40ml")), "variante"),
    ]:
        groups, info = load_ex(_gtin_db(*((s, t, None) for s, t in rows)))
        assert len(groups) == len(rows) and info["stats"]["similar_uniones"] == 0 and info["stats"][f"similar_{why}"] >= 1, (why, dict(info["stats"]))
    groups, _ = load_ex(_gtin_db(("a.cl", "Anua Heartleaf Toner 250ml", None), ("b.cl", "Anua Heartleaf Toner Calming 500ml", None)))
    assert len(groups) == 2  # otro tamaño: ni se compara


def test_is_pack_words():
    from match import is_pack
    for t in ["Anua Heartleaf Duo Set", "Pack: Masajeador Facial LED + Sérum Anua Niacinamide 30ml", "Pack Rutina Elasticity Filler 137ml",
              "Dúo La Roche Posay Effaclar Piel Mixta a Grasa", "Pack Effaclar Gel Limpiador 400ml + DUO +M 40ml", "COSRX 2-Pack Snail Essence"]:
        assert is_pack(t), t
    for t in ["Crema Effaclar Duo+M Unifiant 40 mL", "Effaclar Dúo (+) FPS30 40ml", "Laneige Water Sleeping Pack 70ml", "Sheet Mask 10ea"]:
        assert not is_pack(t), t


if __name__ == "__main__":
    test_same_product_different_names()
    test_different_products_stay_apart()
    test_one_pack_is_ignored_but_two_pack_is_not()
    test_official_store_variant_noise_is_ignored()
    test_sizeless_foreign_offer_merges_by_price_in_pesos()
    test_sizeless_merge_needs_similar_price()
    test_gtin_joins_groups_the_text_keeps_apart()
    test_gtin_never_joins_a_pack_a_mini_or_another_size()
    test_gtin_used_twice_by_one_store_identifies_nothing()
    test_product_with_two_gtins_is_not_split_and_is_listed_as_conflict()
    test_similar_joins_a_shorter_name_of_the_same_brand_and_size()
    test_similar_never_joins_when_in_doubt()
    test_is_pack_words()
    print("ok")
