"""La fixture del piloto es aislada y sus marcadores asocian el precio correcto."""
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api

HELPERS = runpy.run_path(str(Path(__file__).with_name("next_pilot_e2e.py")))


class PilotFixtureTests(unittest.TestCase):
    def test_fixture_preserves_alias_price_and_all_unconfirmed_states(self):
        with tempfile.TemporaryDirectory(prefix="yumori-pilot-") as directory:
            path = Path(directory) / "fixture.db"
            cat, pid, alias = HELPERS["seed"](path)
            status, _, body = api.route(cat, f"/api/v1/products/{alias}", {}, path)
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["canonical_id"], pid)
            product = data["product"]
            self.assertEqual(product["display_price"]["amount"], 20000)
            self.assertEqual(product["best_store_ids"], ["tie.cl", "valid.cl"])
            states = {offer["store"]: offer["status"] for offer in product["domestic_offers"]}
            self.assertEqual(states["stale.cl"], "stale")
            self.assertEqual(states["gone.cl"], "missing")
            self.assertEqual(states["suspect.cl"], "suspect")
            self.assertEqual(product["international_offers"][0]["price"],
                             {"amount": 1732, "currency": "USD", "decimals": 2})
            for section, packs in [("asiatica", True), ("dermocosmetica", False), ("dermocosmetica", True)]:
                with self.subTest(section=section, packs=packs):
                    items, total = cat.search(stock=True, section=section, packs=packs)
                    self.assertGreater(total, 0)
                    self.assertTrue(all(p.section == section and p.is_pack == packs for p in items))

    def test_price_marker_uses_own_card_or_offer_context(self):
        document = HELPERS["Document"](
            '<article data-product-id="one"><span data-price-amount="20000">$20.000</span></article>'
            '<article data-product-id="two"><span data-price-amount="15000">$15.000</span></article>'
            '<table><tr data-store-id="a.cl" data-offer-status="stale"><td>'
            '<span data-price-amount="9000">$9.000</span></td></tr></table>')
        self.assertEqual([(attrs.get("data-product-id"), attrs["data-price-amount"])
                          for attrs in document.prices[:2]], [("one", "20000"), ("two", "15000")])
        self.assertEqual(document.prices[2]["data-store-id"], "a.cl")
        self.assertEqual(document.prices[2]["data-offer-status"], "stale")
        self.assertNotIn("data-product-id", document.prices[2])

    def test_product_markers_preserve_section_scope(self):
        document = HELPERS["Document"]('<section data-products="related">'
                                       '<article data-product-id="one"></article></section>'
                                       '<article data-product-id="main"></article>')
        self.assertEqual(document.products[0], {"data-products": "related", "data-product-id": "one"})
        self.assertEqual(document.products[1], {"data-product-id": "main"})

    def test_csp_rejects_unsafe_script_sources_and_nonce_mismatch(self):
        document = HELPERS["Document"]('<script nonce="fixture">inline()</script>'
                                       '<script nonce="fixture" src="/_next/static/main.js"></script>')
        headers = {"Content-Security-Policy": "default-src 'self'; script-src 'self' 'nonce-fixture'; style-src 'unsafe-inline'"}
        with patch.dict(HELPERS["verify_csp"].__globals__,
                        get=lambda *a, **k: (200, "", "", {"Content-Type": "application/javascript"})):
            HELPERS["verify_csp"]("http://127.0.0.1:1234", document, headers)
            for policy in ("script-src 'self' 'nonce-fixture' 'unsafe-inline'",
                           "script-src 'self' 'nonce-fixture' 'unsafe-eval'",
                           "script-src 'self' 'nonce-other'"):
                with self.subTest(policy=policy), self.assertRaises(AssertionError):
                    HELPERS["verify_csp"]("http://127.0.0.1:1234", document,
                                          {"Content-Security-Policy": policy})

    def test_facets_and_best_label_remain_associated_with_their_elements(self):
        document = HELPERS["Document"]('<label><input type="checkbox" name="tienda" value="a.cl">Tienda A '
                                       '<span data-facet-name="tienda" data-facet-value="a.cl" data-facet-count="2">2</span></label>'
                                       '<label><input type="checkbox" name="tienda" value="b.cl">Tienda B '
                                       '<span data-facet-name="tienda" data-facet-value="b.cl" data-facet-count="0">0</span></label>'
                                       '<a href="/explorar?cat=facial">Cuidado facial '
                                       '<span data-facet-name="cat" data-facet-value="facial" data-facet-count="1234">1.234</span></a>'
                                       '<tr data-store-id="a.cl"><td>Mejor precio confirmado</td></tr>'
                                       '<tr data-store-id="b.cl"><td>Sin conexión</td></tr>')
        self.assertEqual(document.facets, {"tienda": {"a.cl": ["2"], "b.cl": ["0"]}, "cat": {"facial": ["1.234"]}})
        self.assertEqual(document.facet_counts, {"tienda": {"a.cl": 2, "b.cl": 0}, "cat": {"facial": 1234}})
        self.assertIn("Mejor precio confirmado", document.rows["a.cl"]["text"])
        self.assertNotIn("Mejor precio confirmado", document.rows["b.cl"]["text"])

    def test_repeated_facet_markers_fail_instead_of_overwriting_counts(self):
        with self.assertRaises(AssertionError):
            HELPERS["Document"]('<span data-facet-name="tienda" data-facet-value="a.cl" data-facet-count="2">2</span>'
                                 '<span data-facet-name="tienda" data-facet-value="a.cl" data-facet-count="3">3</span>')
