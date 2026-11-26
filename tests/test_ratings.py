import json
import sys
from pathlib import Path
from unittest.mock import Mock, call, patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import ratings
from ratings import gtins_for, parse, parse_gtins


def test_parse():
    assert parse("<div class='jdgm-prev-badge' data-average-rating='4.80' data-number-of-reviews='12'>") == (4.8, 12)
    assert parse("<div data-average-rating='0.00' data-number-of-reviews='0'>") == (None, None)  # sin reseñas: no se muestra
    assert parse("<html>sin badge</html>") == (None, None)


def ld(obj):
    return f'<script type="application/ld+json">{json.dumps(obj)}</script>'


# Recortes de páginas reales (2026-10-04). Los "barcode" sueltos son de productos recomendados y no deben tomarse.
RECOMENDADO = '<script>var r=[{"id":1,"barcode": "793969939855"}]</script>'
SOKOBOX_MULTI = ld({"@context": "http://schema.org/", "@type": "Product", "name": "Acai Berry Mask Sheet", "sku": "HOLIKA19-7", "gtin8": "8806334368142",
                    "gtin13": "8806334368142", "offers": [
                        {"@type": "Offer", "sku": "HOLIKA19-7", "price": 1592.0, "url": "https://sokobox.cl/products/acai?variant=36409872187555"},
                        {"@type": "Offer", "sku": "HOLIKA19-7-SET", "price": 15920.0, "url": "https://sokobox.cl/products/acai?variant=36409828769955"}]})
SOKOBOX_UNO = ld({"@type": "Product", "name": "Real Mugwort Clay Mask", "sku": "ISN10", "gtin13": "8809800940200",
                  "offers": [{"@type": "Offer", "sku": "ISN10", "url": "https://sokobox.cl/products/m?variant=36403368067235"}]})
ARUMI_GRUPO = ld({"@type": "ProductGroup", "name": "Mood On Eye Color Stick", "hasVariant": [
    {"@type": "Product", "sku": "BBMOECS-PS", "gtin": "8809759906708", "offers": {"@type": "Offer", "url": "https://arumi.cl/products/b?variant=49932116099347"}},
    {"@type": "Product", "sku": "BBMOECS-SB", "gtin": "8809759906739", "offers": {"@type": "Offer", "url": "https://arumi.cl/products/b?variant=49932116132115"}},
    {"@type": "Product", "sku": "BBMOECS-S", "offers": {"@type": "Offer", "url": "https://arumi.cl/products/b?variant=49932116164883"}}]})
RAKUEN_FALSO = ld({"@type": "Product", "gtin": "17336219801206", "offers": {"@type": "Offer", "url": "https://rakuen/products/a?variant=45210229801206"}})
# varias variantes con el mismo sku y un solo código a nivel de producto: no hay forma de saber de cuál es
SIN_RELACION = ld({"@type": "Product", "sku": "BC000002", "gtin13": "8809640732829", "offers": [
    {"@type": "Offer", "sku": "BC000002", "url": "https://moonbow.cl/products/p?variant=1"},
    {"@type": "Offer", "sku": "BC000002", "url": "https://moonbow.cl/products/p?variant=2"}]})


def test_gtin_producto_principal():
    assert parse_gtins(SOKOBOX_UNO + RECOMENDADO) == {"36403368067235": "08809800940200"}  # el barcode del recomendado no entra
    assert parse_gtins(RECOMENDADO) == {}
    assert parse_gtins("<html>sin json-ld</html>") == {}


def test_gtin_variantes():
    # Sokobox: el código del Product es el de la variante cuyo sku coincide; la de 10 unidades (SET) no tiene el suyo
    codes = parse_gtins(SOKOBOX_MULTI + RECOMENDADO)
    assert codes == {"36409872187555": "08806334368142"}
    assert gtins_for([(1, "36409828769955"), (2, "36409872187555")], codes) == [(2, "08806334368142")]
    # Arumi/Rakuen: ProductGroup con un código por variante; la que no lo trae queda sin código
    codes = parse_gtins(ARUMI_GRUPO)
    assert gtins_for([(1, "49932116099347"), (2, "49932116132115"), (3, "49932116164883")], codes) == [(1, "08809759906708"), (2, "08809759906739")]


def test_gtin_no_adivina():
    assert parse_gtins(SIN_RELACION) == {}  # varias variantes y ninguna se relaciona con el código
    assert gtins_for([(1, "1"), (2, "2")], parse_gtins(SIN_RELACION)) == []
    assert parse_gtins(RAKUEN_FALSO) == {}  # código que no pasa el verificador GS1: no es un código de barras
    assert gtins_for([(1, "x"), (2, "y")], {None: "08809800940200"}) == []  # sin variante y 2 listings: nada
    assert gtins_for([(1, "x")], {None: "08809800940200"}) == [(1, "08809800940200")]  # sin variante y 1 listing: sí


def mock_db(urls, listings=None):
    db = Mock()

    def execute(sql, params):
        if sql.startswith("SELECT DISTINCT url"):
            return [(url,) for url in urls[params[0]]]
        if sql.startswith("SELECT id, ext_id"):
            return Mock(fetchall=Mock(return_value=(listings or {}).get(params, [])))
        return Mock()

    db.execute.side_effect = execute
    return db


def updates(db):
    return [c for c in db.execute.call_args_list if c.args[0].startswith("UPDATE")]


def test_blocked_detiene_solo_tienda():
    for code in (403, 429):
        db = mock_db({"a.cl": ["a/1", "a/2", "a/3"], "b.cl": ["b/1"]},
                     {("a.cl", "a/1"): [(7, "36403368067235")]})
        html = SOKOBOX_UNO + "<div data-average-rating='4.80' data-number-of-reviews='12'>"
        with patch.object(ratings, "get", side_effect=[html, ratings.Blocked(f"HTTP {code}"), "sin badge"]) as get, \
                patch.object(ratings.time, "sleep") as sleep, patch.object(ratings, "log") as log:
            ratings.run(db, ["a.cl", "b.cl"])
        assert get.call_args_list == [call("a/1", text=True, sign=True), call("a/2", text=True, sign=True), call("b/1", text=True, sign=True)]
        assert updates(db) == [
            call("UPDATE listing SET rating=?, reviews=? WHERE store=? AND url=?", (4.8, 12, "a.cl", "a/1")),
            call("UPDATE listing SET gtin=? WHERE id=?", ("08809800940200", 7)),
            call("UPDATE listing SET rating=?, reviews=? WHERE store=? AND url=?", (None, None, "b.cl", "b/1")),
        ]
        assert db.commit.call_count == 4  # fichas exitosas y cierre de cada tienda
        assert sleep.call_args_list == [call(ratings.DELAY), call(ratings.DELAY)]
        log.assert_any_call(f"a/2: HTTP {code}")
        log.assert_any_call("a.cl: detenido por bloqueo, 1 de 3 productos con reseñas, 1 listings con código de barras")
        log.assert_any_call("b.cl: listo, 0 de 1 productos con reseñas, 0 listings con código de barras")
        assert log.call_args_list[-1] == call("ratings: fin")


def test_errores_transitorios_pausan_antes_de_siguiente_ficha():
    db = mock_db({"a.cl": ["a/1", "a/2", "a/3"]})
    events = []
    responses = iter([TimeoutError("timeout"), URLError("sin conexión"), "sin badge"])

    def get(url, text, sign):
        events.append(("get", url))
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    with patch.object(ratings, "get", side_effect=get), \
            patch.object(ratings.time, "sleep", side_effect=lambda delay: events.append(("sleep", delay))), \
            patch.object(ratings, "log") as log:
        ratings.run(db, ["a.cl"])
    assert events == [("get", "a/1"), ("sleep", ratings.DELAY),
                      ("get", "a/2"), ("sleep", ratings.DELAY),
                      ("get", "a/3"), ("sleep", ratings.DELAY)]
    assert updates(db) == [call("UPDATE listing SET rating=?, reviews=? WHERE store=? AND url=?", (None, None, "a.cl", "a/3"))]
    assert db.commit.call_count == 2
    log.assert_any_call("a/1: timeout")
    log.assert_any_call("a/2: <urlopen error sin conexión>")


def test_run_limite_y_tienda_vacia():
    for limit, expected in ((0, []), (1, [call("a/1", text=True, sign=True)])):
        db = mock_db({"vacia.cl": [], "a.cl": ["a/1", "a/2"]})
        with patch.object(ratings, "get", return_value="sin badge") as get, \
                patch.object(ratings.time, "sleep") as sleep, patch.object(ratings, "log"):
            ratings.run(db, ["vacia.cl", "a.cl"], limit=limit)
        assert get.call_args_list == expected
        assert sleep.call_args_list == [call(ratings.DELAY)] * len(expected)
        assert len(updates(db)) == len(expected)
        assert db.commit.call_count == 2 + len(expected)


if __name__ == "__main__":
    test_parse()
    test_gtin_producto_principal()
    test_gtin_variantes()
    test_gtin_no_adivina()
    test_blocked_detiene_solo_tienda()
    test_errores_transitorios_pausan_antes_de_siguiente_ficha()
    test_run_limite_y_tienda_vacia()
    print("ok")
