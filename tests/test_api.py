"""Contrato de lectura JSON probado mediante server.route y SQLite propia."""
import json
import io
import re
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

import api
import server
from catalog import Catalog, PAGE_SIZE
from db import connect, save


def item(ext_id, title, price=20000, vendor="Cosrx", **extra):
    return dict(ext_id=str(ext_id), sku=None, title=title, variant=None,
                vendor=vendor, url=f"https://fixture.invalid/{ext_id}",
                price=price, compare_at=None, available=1, **extra)


class Cards(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "card-link" in attrs.get("class", "").split():
            self.ids.append(attrs["href"].removeprefix("/p/"))


class ApiTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="yumori-api-")
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "fixture.db"
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        self.cat = None
        self.enterContext(patch.object(server, "DB", self.path))
        self.enterContext(patch.object(server, "get_catalog", lambda: self.cat))
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("No live network")))

    def build(self):
        self.db.commit()
        self.cat = Catalog(self.db, sync=False)
        return self.cat

    def request(self, path="/api/v1/products", query="", status=200):
        result = server.route(path, parse_qs(query, keep_blank_values=True))
        self.assertEqual(result[0], status, result[2].decode())
        self.assertEqual(result[1], "application/json; charset=utf-8")
        self.assertIsInstance(result[2], bytes)
        data = json.loads(result[2])
        self.assertEqual(data["version"], 1)
        if status >= 400:
            self.assertEqual(data["error"]["code"], "invalid_parameters" if status == 400 else "not_found")
        return data

    def detail(self, pid):
        return self.request(f"/api/v1/products/{pid}")["product"]

    def seed_list(self):
        save(self.db, "a.cl", [
            item(1, "Advanced Snail Essence 100ml"),
            item(2, "Low pH Good Morning Gel Cleanser 150ml", 15000),
            {**item(3, "Agotado Cream 50ml"), "available": 0},
            item(4, "Snail Essence 100ml 2-Pack", 35000),
            item(5, "Effaclar Gel 200ml", vendor="La Roche Posay"),
            item(6, "Effaclar Gel 200ml 2-Pack", vendor="La Roche Posay"),
        ])
        save(self.db, "b.cl", [item(10, "Advanced Snail Essence 100ml", 19000)])
        return self.build()

    def assert_parity(self, query, html_path, filters, q="", sort="", page=1):
        data = self.request(query=query)
        products, total = self.cat.search(q, sort=sort, page=page, **filters)
        self.assertEqual([p["id"] for p in data["items"]], [p.id for p in products])
        self.assertEqual(data["total"], total)
        self.assertEqual(data["facets"], {k: dict(v) for k, v in self.cat.counts(q, **filters).items()})
        result = server.route(html_path, parse_qs(query, keep_blank_values=True))
        self.assertEqual(result[0], 200)
        html = result[2].decode()
        self.assertEqual(Cards(html).ids, [p["id"] for p in data["items"]])
        noun = "packs" if filters.get("packs") else "productos"
        self.assertIn(f'{server.fmt(total)} {noun}</p>', html)
        return data

    def test_default_stock_sections_and_pack_lists_match_html(self):
        self.seed_list()
        cases = [
            ("", "/explorar", {"stock": True}, 2),
            ("sinstock=1", "/explorar", {"stock": False}, 3),
            ("seccion=dermocosmetica", "/dermocosmetica", {"stock": True, "section": "dermocosmetica"}, 1),
            ("packs=1", "/packs", {"stock": True, "packs": True}, 1),
            ("packs=1&seccion=dermocosmetica", "/dermocosmetica/packs",
             {"stock": True, "packs": True, "section": "dermocosmetica"}, 1),
        ]
        for query, html_path, filters, total in cases:
            with self.subTest(query=query):
                self.assertEqual(self.assert_parity(query, html_path, filters)["total"], total)
        all_sections = self.request(query="seccion=todas")
        self.assertEqual(all_sections["total"], 3)
        self.assertEqual({p["section"] for p in all_sections["items"]}, {"asiatica", "dermocosmetica"})

    def test_site_uses_catalog_picks_directories_and_plain_legal_blocks(self):
        self.seed_list()
        data = self.request("/api/v1/site")
        self.assertEqual(data["home"]["product_count"], len(self.cat.products))
        self.assertEqual(data["home"]["section_counts"], dict(self.cat.section_counts))
        for key, picks in [("spread", self.cat.top_spread()), ("drops", self.cat.drops())]:
            self.assertEqual([p["id"] for p in data["home"][key]], [p.id for p in picks])
        for section in ("asiatica", "dermocosmetica"):
            counts = self.cat.counts(stock=True, section=section)["tienda"]
            self.assertEqual({s["domain"]: s["count"] for s in data["stores"][section]},
                             {s: counts.get(s, 0) for s in (self.cat.stores if section == "asiatica" else self.cat.derm_stores)})
        # /tiendas: una entrada por tienda chilena, con el conteo de cada sección en la que vende, en orden alfabético
        chile = data["stores"]["chile"]
        self.assertEqual([s["domain"] for s in chile], sorted(set(self.cat.stores) | set(self.cat.derm_stores), key=lambda d: api.words(api.store_name(d))))
        for s in chile:
            self.assertNotIn("count", s)
            self.assertEqual(s["counts"], {section: row["count"] for section in ("asiatica", "dermocosmetica")
                                           for row in data["stores"][section] if row["domain"] == s["domain"]})
        self.assertEqual({b["slug"]: [b["name"], b["count"]] for b in data["brands"]["asiatica"]}, self.cat.brands)
        blocks = data["legal"]["cookies"]["blocks"]
        self.assertTrue(any("yumori:fav" in block["text"] for block in blocks))
        with patch.dict(api.legal.OPERATOR, {"Nombre o razón social": "<script>alert(1)</script>"}):
            blocks = self.request("/api/v1/site")["legal"]["terminos"]["blocks"]
        self.assertTrue(any("<script>alert(1)</script>" in block["text"] for block in blocks))
        self.assertTrue(all(set(block) == {"tag", "text", "inline"} for block in blocks))
        self.request("/api/v1/site", "q=x", status=400)

    def test_favorites_resolve_aliases_deduplicate_and_distinguish_missing(self):
        self.seed_list()
        pid = self.cat.products[0].id
        old, missing = "0123456789", "fffffffffe"
        self.db.execute("INSERT INTO product_alias VALUES(?,?,?)", (old, pid, "2026-10-01T00:00:00+00:00"))
        self.db.commit()
        self.cat = Catalog(self.db)
        data = self.request("/api/v1/favorites", f"ids={old},{pid},{missing},{old}")
        self.assertEqual([p["id"] for p in data["items"]], [pid])
        self.assertEqual(data["resolutions"], {old: pid, pid: pid, missing: None})
        self.assertEqual(data["missing_ids"], [missing])
        self.assertEqual(self.request("/api/v1/favorites")["items"], [])
        self.assertEqual(len(self.request("/api/v1/favorites", "ids=" + ",".join([pid] * 100))["items"]), 1)
        for query in ("ids=x", "ids=" + pid + ",", "ids=" + ",".join([pid] * 101), "ids=&ids=", "q=x"):
            self.request("/api/v1/favorites", query, status=400)

    def test_sitemap_lists_products_listed_in_chile_with_lastmod(self):
        save(self.db, "www.yesstyle.com", [{**item(20, "Solo Afuera Toner 150ml", 1500), "currency": "USD"}])
        self.seed_list()
        data = self.request("/api/v1/sitemap")
        ids = [p["id"] for p in data["products"]]
        self.assertEqual(ids, [p.id for p in self.cat.products if p.listed_in_chile])
        names = {p.id: p.name for p in self.cat.products}
        self.assertIn("Agotado Cream", {names[i] for i in ids})  # sin stock sigue: la tienda chilena lo lista
        self.assertTrue(any("Solo Afuera" in n for n in names.values()))
        self.assertFalse(any("Solo Afuera" in names[i] for i in ids))  # solo extranjero: fuera del sitemap
        self.assertTrue(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["lastmod"]) for p in data["products"]), data["products"])
        self.request("/api/v1/sitemap", "q=x", status=400)

    def test_suggestions_preserve_asian_priority_and_section_totals(self):
        self.seed_list()
        for q in ("cosrx", "effaclar", "no-such-product", ""):
            data = self.request("/api/v1/suggestions", "q=" + q)
            expected = self.cat.suggest(q)
            if len(expected) < 6:
                expected += self.cat.suggest(q, n=6 - len(expected), section="dermocosmetica")
            self.assertEqual([p["id"] for p in data["items"]], [p.id for p in expected])
            for row in data["sections"]:
                self.assertEqual(row["total"], self.cat.search(q, stock=True, section=row["section"])[1])
        for query in ("q=x&q=y", "unknown=x", "q=" + "x" * 201):
            self.request("/api/v1/suggestions", query, status=400)

    def test_remaining_route_callouts_and_detail_links_follow_legacy(self):
        self.seed_list()
        data = self.request(query="q=cosrx&tienda=b.cl")
        self.assertEqual(data["category_counts"], self.request(query="q=cosrx")["category_counts"])
        self.assertEqual(data["related_counts"]["packs"], self.cat.search("cosrx", stock=True, packs=True)[1])
        self.assertEqual(data["related_counts"]["other_section"], self.cat.search("cosrx", stock=True, section="dermocosmetica")[1])
        self.assertEqual(data["section_product_count"], self.cat.section_counts["asiatica"])
        self.assertEqual(self.request(query="packs=1&q=cosrx")["related_counts"], {"packs": 0, "other_section": 0})
        derm = next(p for p in self.cat.products if p.section == "dermocosmetica" and not p.is_pack)
        detail = self.detail(derm.id)
        html = server.product(self.cat, derm.id)[1]
        from html import escape
        for link in detail["search_elsewhere"]:
            self.assertIn(escape(link["url"]), html)
        self.assertTrue(detail["search_elsewhere"])
        pack = next(p for p in self.cat.products if p.section == "dermocosmetica" and p.is_pack)
        self.assertEqual(self.detail(pack.id)["search_elsewhere"], [])
        asian = next(p for p in self.cat.products if len(p.offers) == 2)
        asian.offers[0].price = 1000
        self.assertTrue(self.detail(asian.id)["price_spread_warning"])
        data = self.request("/api/v1/site")
        self.assertEqual(len({ev["slug"] for ev in data["events"]}), len(data["events"]))
        self.assertEqual(data["events"], [api.event_for(ev["slug"]) for ev in data["events"]])

    def test_repeated_filters_search_sort_and_facets_preserve_catalog_behavior(self):
        self.seed_list()
        query = "q=cosrx&tienda=a.cl&tienda=b.cl&tipo=esencia&tipo=limpiador&orden=precio_asc&min=10000&max=25000"
        filters = dict(stock=True, stores=["a.cl", "b.cl"], kinds=["esencia", "limpiador"], pmin=10000, pmax=25000)
        data = self.assert_parity(query, "/explorar", filters, q="cosrx", sort="precio_asc")
        self.assertEqual(data["total"], 2)
        self.assertEqual([p["display_price"]["amount"] for p in data["items"]], [15000, 19000])
        p = next(p for p in self.cat.products if p.kind == "esencia")
        # Repetición OR en cada faceta; se mantiene la intersección entre facetas.
        p.skin[:] = ["Piel seca"]
        p.actives[:] = ["niacinamida"]
        query = "piel=Piel+seca&piel=Piel+sensible&ing=niacinamida&ing=retinol"
        data = self.assert_parity(query, "/explorar", dict(stock=True,
                                  skins=["Piel seca", "Piel sensible"], actives=["niacinamida", "retinol"]))
        self.assertEqual([x["id"] for x in data["items"]], [p.id])

    def test_pagination_has_no_duplicates_and_total_is_not_page_length(self):
        save(self.db, "a.cl", [item(i, f"Fixture Serum Variante{i} 50ml") for i in range(PAGE_SIZE + 3)])
        self.build()
        seen = []
        for page, size in [(1, PAGE_SIZE), (2, 3), (3, 0)]:
            with self.subTest(page=page):
                data = self.assert_parity(f"orden=nombre&pagina={page}", "/explorar",
                                         {"stock": True}, sort="nombre", page=page)
                self.assertEqual((data["page"], data["page_size"], data["pages"]), (page, PAGE_SIZE, 2))
                self.assertEqual(data["total"], PAGE_SIZE + 3)
                self.assertEqual(len(data["items"]), size)
                seen.extend(p["id"] for p in data["items"])
        self.assertEqual(len(set(seen)), PAGE_SIZE + 3)

    def test_detail_alias_returns_canonical_id_without_redirect(self):
        save(self.db, "a.cl", [item(1, "Snail Essence 100ml")])
        self.build()
        pid = self.cat.products[0].id
        old = "0123456789"
        self.db.execute("INSERT INTO product_alias VALUES(?,?,?)", (old, pid, "2026-10-01T00:00:00+00:00"))
        self.db.commit()
        self.cat = Catalog(self.db)
        canonical = self.request(f"/api/v1/products/{pid}")
        alias = self.request(f"/api/v1/products/{old}")
        self.assertEqual((alias["requested_id"], alias["canonical_id"]), (old, pid))
        self.assertEqual(canonical["canonical_id"], pid)
        self.assertEqual(alias["product"], canonical["product"])
        self.assertEqual(alias["product"]["path"], f"/p/{pid}")
        history = self.request(f"/api/v1/products/{old}/history")
        self.assertEqual((history["requested_id"], history["canonical_id"]), (old, pid))
        self.assertEqual(history["stores"], self.request(f"/api/v1/products/{pid}/history")["stores"])
        self.assertEqual(server.route(f"/p/{old}", {})[3]["Location"], f"/p/{pid}")

    def test_deals_follow_own_history_and_selected_store_not_strikethrough(self):
        save(self.db, "a.cl", [item(1, "Snail Essence 100ml", 20000)])
        save(self.db, "b.cl", [{**item(2, "Snail Essence 100ml", 18000), "compare_at": 50000}])
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")
        self.db.execute("UPDATE price SET ts=?", (old,))
        save(self.db, "a.cl", [item(1, "Snail Essence 100ml", 15000)])
        self.build()
        data = self.assert_parity("oferta=1&multi=1", "/explorar", dict(stock=True, deals=True, multi=True))
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["facets"]["tienda"], {"a.cl": 1})
        for store, total in [("a.cl", 1), ("b.cl", 0)]:
            with self.subTest(store=store):
                data = self.assert_parity(f"oferta=1&tienda={store}", "/explorar",
                                          dict(stock=True, deals=True, stores=[store]))
                self.assertEqual(data["total"], total)

    def test_clp_usd_cents_and_estimate_do_not_mix_best_prices(self):
        self.db.execute("INSERT INTO fx VALUES('2026-10-01', 958.42)")
        save(self.db, "a.cl", [item(1, "Snail Essence 100ml", 20000)])
        save(self.db, "foreign.invalid", [item(2, "Snail Essence 100ml", 1732, currency="USD"),
                                           item(3, "Foreign Only Toner 250ml", 1732, currency="USD")])
        self.build()
        mixed = next(p for p in self.cat.products if p.domestic)
        foreign = next(p for p in self.cat.products if not p.domestic)
        data = self.detail(mixed.id)
        self.assertEqual(data["domestic_offers"][0]["price"], {"amount": 20000, "currency": "CLP", "decimals": 0})
        self.assertEqual(data["international_offers"][0]["price"], {"amount": 1732, "currency": "USD", "decimals": 2})
        self.assertEqual(data["international_offers"][0]["estimate"], {"amount": 19754, "currency": "CLP", "decimals": 0})
        self.assertEqual(data["best_store_ids"], ["a.cl"])
        self.assertTrue(data["display_price_confirmed"])
        abroad = self.detail(foreign.id)
        self.assertTrue(abroad["display_is_estimate"])
        self.assertTrue(abroad["display_price_confirmed"])
        self.assertEqual(abroad["display_price"]["amount"], 19754)
        self.assertEqual(abroad["best_store_ids"], [])
        self.assertEqual(abroad["primary_offer_store_ids"], ["foreign.invalid"])
        self.assertEqual(abroad["card_prefix"], "Estimado")
        self.assertIn("Solo en el extranjero", abroad["card_meta"])
        meta = self.request()
        self.assertEqual(meta["exchange_rate"], {"usd_clp": 958.42, "date": "2026-10-01"})
        self.assertTrue(meta["estimate_includes_vat"])
        self.assertFalse(meta["estimate_includes_shipping"])
        self.db.execute("DELETE FROM fx")
        self.build()
        no_fx = self.detail(foreign.id)
        self.assertIsNone(no_fx["display_price"])
        self.assertFalse(no_fx["display_is_estimate"])
        self.assertIsNone(no_fx["international_offers"][0]["estimate"])
        self.assertEqual(no_fx["international_offers"][0]["price"]["amount"], 1732)
        self.assertIn(foreign.id, [p["id"] for p in self.request()["items"]])

    def test_unconfirmed_states_never_win_even_when_cheaper(self):
        title = "Snail Essence 100ml"
        for store, price in [("valid.cl", 20000), ("tie.cl", 20000), ("stale.cl", 10000),
                             ("gone.cl", 11000), ("suspect.cl", 50)]:
            save(self.db, store, [item(1, title, price)], seen_at="2026-10-01T00:00:00+00:00")
        save(self.db, "gone.cl", [item(2, "Other Cleanser 150ml")], seen_at="2026-10-02T00:00:00+00:00")
        for store in ("valid.cl", "tie.cl", "gone.cl", "suspect.cl", "stale.cl"):
            ts = "2026-10-01T00:00:00+00:00" if store == "stale.cl" else "2026-10-02T00:00:00+00:00"
            self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", ("scraped:" + store, ts))
        self.db.execute("INSERT INTO meta VALUES('run:done','2026-10-02T00:00:00+00:00')")
        self.build()
        p = next(p for p in self.cat.products if "Snail" in p.name)
        data = self.detail(p.id)
        offers = {o["store"]: o for o in data["domestic_offers"]}
        for store, state, label in [("stale.cl", "stale", "Sin conexión"),
                                    ("gone.cl", "missing", "No aparece en la tienda"),
                                    ("suspect.cl", "suspect", "Precio por confirmar")]:
            with self.subTest(store=store):
                self.assertEqual((offers[store]["status"], offers[store]["status_label"]), (state, label))
                self.assertFalse(offers[store]["available"])
                self.assertNotIn(store, data["best_store_ids"])
        self.assertEqual(data["best_store_ids"], ["tie.cl", "valid.cl"])
        self.assertEqual(data["primary_offer_store_ids"], ["tie.cl", "valid.cl"])
        self.assertEqual(data["card_prefix"], "desde")
        self.assertIn("100 ml", data["card_meta"])
        self.assertIn("en 5 tiendas", data["card_meta"])
        self.assertEqual(data["display_price"]["amount"], 20000)
        self.db.execute("UPDATE price SET available=0 WHERE listing_id IN (SELECT id FROM listing WHERE store IN ('valid.cl','tie.cl'))")
        self.build()
        unconfirmed = self.detail(p.id)
        self.assertEqual(unconfirmed["best_store_ids"], [])
        self.assertEqual(len(unconfirmed["primary_offer_store_ids"]), 1)
        self.assertFalse(unconfirmed["display_price_confirmed"])
        self.assertNotIn(p.id, [x["id"] for x in self.request()["items"]])

    def test_conditional_card_offer_is_separate_and_not_used_by_price_filter(self):
        save(self.db, "a.cl", [item(1, "Snail Essence 100ml", 25000, card_price=9000, card_name="Tarjeta fixture")])
        save(self.db, "b.cl", [item(2, "Snail Essence 100ml", 20000)])
        self.build()
        data = self.detail(self.cat.products[0].id)
        self.assertEqual(data["best_store_ids"], ["b.cl"])
        self.assertEqual(data["display_price"]["amount"], 20000)
        self.assertEqual(data["card_offers"][0]["normal_price"], {"amount": 25000, "currency": "CLP", "decimals": 0})
        self.assertEqual([(o["store"], o["price"]["amount"], o["card_name"]) for o in data["card_offers"]],
                         [("a.cl", 9000, "Tarjeta fixture")])
        self.assertEqual({o["store"]: o["price"]["amount"] for o in data["domestic_offers"]}, {"a.cl": 25000, "b.cl": 20000})
        self.assertEqual(self.request(query="max=10000")["total"], 0)

    def test_pack_links_keep_pack_sizes_and_unit_quantities(self):
        save(self.db, "a.cl", [
            item(1, "Pine Calming Cica Cleanser 150ml", vendor="Round Lab"),
            item(2, "Pine Calming Cica Toner 250ml", vendor="Round Lab"),
            item(3, "Pine Calming Cica Trial Kit", vendor="Round Lab",
                 description="Rutina mini. Incluye: Pine Calming Cica Cleanser 30ml Pine Calming Cica Toner 20 ml."),
            item(4, "Pine Calming Cica Cleanser 150ml 2-Pack", 35000, vendor="Round Lab"),
        ])
        self.build()
        cleanser = next(p for p in self.cat.products if not p.is_pack and "Cleanser" in p.name)
        toner = next(p for p in self.cat.products if not p.is_pack and "Toner" in p.name)
        kit = next(p for p in self.cat.products if "Trial Kit" in p.name)
        twin = next(p for p in self.cat.products if p.is_pack and p.id != kit.id)
        data = self.detail(kit.id)
        self.assertTrue(data["small_format"])
        self.assertTrue(data["pack_size_warning"])
        # Incluso sin la palabra mini, el tamaño del pack exige el mismo aviso.
        kit.small_format = False
        self.assertTrue(self.detail(kit.id)["pack_size_warning"])
        self.assertFalse(self.detail(twin.id)["pack_size_warning"])
        self.assertEqual({x["product_id"]: x["pack_size"] for x in data["includes"]}, {cleanser.id: "30 ml", toner.id: "20 ml"})
        self.assertEqual({x["product_id"]: x["size"] for x in data["contents"]}, {cleanser.id: "30 ml", toner.id: "20 ml"})
        self.assertEqual([(x["product_id"], x["quantity"]) for x in self.detail(twin.id)["includes"]], [(cleanser.id, 2)])
        single = self.detail(cleanser.id)
        self.assertEqual(single["size"], "150 ml")
        self.assertEqual({x["product_id"]: x["quantity"] for x in single["included_in"]}, {kit.id: 1, twin.id: 2})
        self.assertEqual(single["domestic_store_count"], 1)

    def test_history_uses_own_source_raw_utc_and_readonly_without_writes(self):
        save(self.db, "a.cl", [item(1, "Snail Essence 100ml")])
        save(self.db, "b.cl", [item(2, "Snail Essence 100ml", 22000)])
        self.db.execute("DELETE FROM price")
        ids = dict(self.db.execute("SELECT store,id FROM listing"))
        observations = [("2026-10-01T02:00:00+00:00", 21000, 1),
                        ("2026-10-01T02:00:00+00:00", 21000, 0),
                        ("2026-10-02T02:00:00+00:00", 20000, 1)]
        self.db.executemany("INSERT INTO price VALUES(?,?,?,NULL,?)", [(ids["a.cl"], *row) for row in observations])
        self.db.execute("INSERT INTO price VALUES(?, '2026-10-03T02:00:00+00:00', 22000, NULL, 1)", (ids["b.cl"],))
        self.build()
        pid = self.cat.products[0].id
        before = self.path.read_bytes()
        dump = list(self.db.iterdump())
        original_connect = sqlite3.connect
        opened = []

        def readonly(database, *args, **kwargs):
            self.assertEqual(database, self.path.resolve().as_uri() + "?mode=ro")
            self.assertTrue(kwargs.get("uri"))
            con = original_connect(database, *args, **kwargs)
            opened.append(con)
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("CREATE TABLE forbidden_write(x)")
            return con

        with patch.object(api.sqlite3, "connect", side_effect=readonly), \
             patch("db.connect", side_effect=AssertionError("No migrations during API reads")):
            self.request()
            self.detail(pid)
            pages = [self.request(f"/api/v1/products/{pid}/history", f"pagina={n}&limite=2") for n in (1, 2, 3)]
        for con in opened:
            con.close()
        gathered = []
        for page, data in enumerate(pages, 1):
            self.assertEqual((data["page"], data["limit"], data["canonical_id"]), (page, 2, pid))
            stores = {x["store"]: x for x in data["stores"]}
            self.assertEqual(stores["a.cl"]["total"], 3)
            self.assertEqual(stores["b.cl"]["total"], 1)
            self.assertEqual(len(stores["b.cl"]["observations"]), 1 if page == 1 else 0)
            gathered.extend(stores["a.cl"]["observations"])
        self.assertEqual([(x["captured_at"], x["price"]["amount"], x["available"]) for x in gathered], observations)
        for x in gathered:
            self.assertEqual(datetime.fromisoformat(x["captured_at"]).utcoffset(), timezone.utc.utcoffset(None))
            self.assertEqual((x["price"]["currency"], x["price"]["decimals"]), ("CLP", 0))
        self.assertEqual(list(self.db.iterdump()), dump)
        self.assertEqual(self.path.read_bytes(), before)

    def test_malformed_queries_and_unknown_routes_return_json_errors(self):
        self.seed_list()
        bad = ["unknown=1", "pagina=0", "pagina=-1", "pagina=1.5", "pagina=100001", "pagina=%D9%A1",
               "pagina=1&pagina=2", "min=abc", "min=25000&max=100", "max=1000000001",
               "sinstock=true", "multi=2", "oferta=yes", "packs=2", "seccion=otra", "orden=otro",
               "cat=otra", "evento=no-existe", "q=" + "a" * 201, "&".join(["tienda=a.cl"] * 21)]
        for query in bad:
            with self.subTest(query=query):
                self.request(query=query, status=400)
        pid = self.cat.products[0].id
        self.request(f"/api/v1/products/{pid}", "q=x", status=400)
        for query in ("limite=0", "limite=1001", "limite=x", "pagina=0", "limite=1&limite=2", "q=x"):
            with self.subTest(history=query):
                self.request(f"/api/v1/products/{pid}/history", query, status=400)
        for path in ("/api", "/api/v2/products", "/api/v1/nope", "/api/v1/products/nope",
                     "/api/v1/products/fffffffffe", f"/api/v1/products/{pid}/other",
                     f"/api/v1/products/{pid}/history/extra"):
            with self.subTest(path=path):
                self.request(path, status=404)
        self.assertEqual(self.request(query="q=")["total"], 2)

    def test_executable_urls_are_sanitized_in_list_detail_and_cards(self):
        save(self.db, "a.cl", [{**item(1, "Snail Essence 100ml", card_price=10000, card_name="Fixture"),
                               "url": "javascript:alert(1)", "image": "javascript:alert(2)",
                               "images": json.dumps(["javascript:alert(2)", "https://images.invalid/safe.jpg"])}])
        save(self.db, "foreign.invalid", [{**item(2, "Snail Essence 100ml", 1732, currency="USD"), "url": "javascript:alert(3)"}])
        self.build()
        listed = self.request()["items"][0]
        data = self.detail(listed["id"])
        self.assertIsNone(listed["image"])
        self.assertIsNone(data["domestic_offers"][0]["url"])
        self.assertIsNone(data["international_offers"][0]["url"])
        self.assertIsNone(data["card_offers"][0]["url"])
        self.assertEqual(data["images"], ["https://images.invalid/safe.jpg"])
        self.assertNotRegex(json.dumps([listed, data]), re.compile(r"javascript:", re.I))

    def http_get(self, target):
        # BaseHTTPRequestHandler completo, con una conexión de memoria sin sockets.
        connection = Mock()
        connection.makefile.return_value = io.BytesIO(
            f"GET {target} HTTP/1.0\r\nHost: fixture.invalid\r\n\r\n".encode("ascii"))
        chunks = []
        connection.sendall.side_effect = chunks.append
        server.Handler(connection, ("127.0.0.1", 12345), Mock())
        headers, body = b"".join(chunks).split(b"\r\n\r\n", 1)
        lines = headers.decode("ascii").split("\r\n")
        status = int(lines[0].split()[1])
        headers = dict(line.split(": ", 1) for line in lines[1:])
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.assertEqual(headers["Cache-Control"], "no-cache")
        for name, value in server.SECURITY_HEADERS.items():
            self.assertEqual(headers[name], value)
        return status, json.loads(body)

    def test_http_handler_preserves_blank_values_and_repeated_filters(self):
        self.seed_list()
        status, data = self.http_get("/api/v1/products?tienda=a.cl&tienda=b.cl")
        self.assertEqual(status, 200)
        self.assertEqual(data, self.request(query="tienda=a.cl&tienda=b.cl"))
        for query in ("q=&q=snail", "unknown=", "pagina=&pagina=1"):
            with self.subTest(query=query):
                status, data = self.http_get("/api/v1/products?" + query)
                self.assertEqual(status, 400)
                self.assertEqual(data["error"]["code"], "invalid_parameters")

    def test_http_handler_bounds_url_and_field_count_before_catalog_access(self):
        with patch.object(server, "get_catalog", side_effect=AssertionError("Rejected requests must not open catalog")):
            for target, expected_status, code in [
                ("/api/v1/products?q=" + "x" * 8192, 414, "uri_too_long"),
                ("/api/v1/products?" + "&".join(["tienda=a.cl"] * 81), 400, "invalid_parameters"),
            ]:
                with self.subTest(status=expected_status):
                    status, data = self.http_get(target)
                    self.assertEqual(status, expected_status)
                    self.assertEqual(data["error"]["code"], code)

    def test_http_handler_internal_failure_is_generic_json(self):
        with patch.object(server, "get_catalog", side_effect=RuntimeError("private fixture diagnostic")), \
             patch.object(server.traceback, "print_exc"):
            status, data = self.http_get("/api/v1/products")
        self.assertEqual(status, 500)
        self.assertEqual(data, {"version": 1, "error": {"code": "internal_error", "message": "Error interno"}})
        self.assertNotIn("private fixture diagnostic", json.dumps(data))
