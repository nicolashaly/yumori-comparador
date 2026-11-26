"""Completitud explícita, sin red ni acceso al catálogo real."""
import importlib
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scrape
from db import connect, save
from scrapers.common import ScrapeCompletion
from scrapers.http import Blocked

FIXTURES = Path(__file__).parent / "fixtures"
OLD = "2026-01-01T00:00:00+00:00"


def item(pid, vendor="Anua", currency="CLP"):
    return dict(ext_id=str(pid), sku=None, title="Serum 30ml", variant=None,
                vendor=vendor, url="https://example.com/serum", price=1000,
                compare_at=None, available=1, currency=currency)


@contextmanager
def database():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.db"
        db = connect(path)
        try:
            yield db, path
        finally:
            db.close()


@contextmanager
def adapter(name, path=None):
    mod = importlib.import_module("scrapers." + name)
    with ExitStack() as stack:
        stack.enter_context(patch.object(mod, "log"))
        stack.enter_context(patch.object(mod.time, "sleep"))
        if path:
            stack.enter_context(patch.object(mod, "DB", path))
        yield mod


class CompletionTests(unittest.TestCase):
    def test_collect_keeps_dict_contract_and_legacy_return(self):
        def gen():
            yield item(1)
            return ScrapeCompletion(True, (("observed:a", OLD),))
        items, result = scrape.collect(gen())
        self.assertEqual(items, [item(1)])
        self.assertTrue(result.partial)
        self.assertEqual(result.metadata, (("observed:a", OLD),))
        self.assertEqual(scrape.collect(iter(items))[1], ScrapeCompletion())

    def test_explicit_partial_above_80_percent_preserves_previous_last_seen(self):
        with database() as (db, _), patch.object(scrape, "log"):
            domain = "example.com"
            save(db, domain, [item(i) for i in range(10)], seen_at=OLD)
            def gen(_):
                yield from [item(i) for i in range(9)]
                return ScrapeCompletion(True, (("observed:a", OLD),))
            with patch.dict(scrape.STORES, {domain: gen}):
                scrape.scrape_store(db, domain, "run")
            self.assertEqual(db.execute("SELECT status FROM scrape_run").fetchone()[0], "parcial")
            self.assertEqual(set(db.execute("SELECT last_seen FROM listing")), {(OLD,)})
            self.assertEqual(db.execute("SELECT value FROM meta WHERE key='observed:a'").fetchone()[0], OLD)

    def test_certified_complete_read_of_a_smaller_store_is_ok_and_marks_the_rest_missing(self):
        from catalog import missing
        with database() as (db, _), patch.object(scrape, "log"):
            domain = "example.com"
            save(db, domain, [item(i) for i in range(10)], seen_at=OLD)
            def gen(_):
                yield from [item(i) for i in range(5)]  # menos del 80%: sin la certificación quedaría parcial para siempre
                return ScrapeCompletion(complete=True)
            with patch.dict(scrape.STORES, {domain: gen}):
                scrape.scrape_store(db, domain, "run")
            self.assertEqual(db.execute("SELECT status FROM scrape_run").fetchone()[0], "ok")
            ids = dict(db.execute("SELECT ext_id, id FROM listing"))
            self.assertEqual(set(missing(db)), {ids[str(i)] for i in range(5, 10)})

    def test_novasalud_certifies_complete_only_when_every_counted_page_was_read(self):
        with adapter("novasalud") as mod:
            with patch.object(mod, "get", return_value="fixture"), patch.object(mod, "parse_listing", return_value=([item(1)], 0, (1, 36, 36))):
                result = scrape.collect(mod.novasalud("example.com"))[1]
                self.assertTrue(result.complete and not result.partial)
            pages = iter([([item(1)], 0, (1, 36, 72))])
            def parse(_):
                return next(pages)  # la página 2 falla al parsear
            with patch.object(mod, "get", return_value="fixture"), patch.object(mod, "parse_listing", side_effect=parse):
                result = scrape.collect(mod.novasalud("example.com"))[1]
                self.assertTrue(result.partial and not result.complete)

    def test_failed_save_does_not_publish_completion_or_synced_metadata(self):
        with database() as (db, _), patch.object(scrape, "log"):
            def gen(_):
                yield item(1)
                yield {"ext_id": "broken"}
                return ScrapeCompletion(False, (("yesstyle:anua", OLD),))
            with patch.dict(scrape.STORES, {"example.com": gen}):
                scrape.scrape_store(db, "example.com", "run")
            self.assertEqual(db.execute("SELECT status FROM scrape_run").fetchone()[0], "error")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM listing").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 0)

    def test_complete_brand_and_partial_brand_only_mark_missing_in_complete_brand(self):
        from catalog import missing
        with database() as (db, _), patch.object(scrape, "log"):
            domain = "www.yesstyle.com"
            save(db, domain, [item(1, "Anua", "USD"), item(2, "Anua", "USD"),
                              item(3, "Cosrx", "USD"), item(4, "Cosrx", "USD")], seen_at=OLD)
            ts = scrape.now()
            def gen(_):
                yield item(1, "Anua", "USD")
                yield item(3, "Cosrx", "USD")
                return ScrapeCompletion(True, (("yesstyle:anua", ts),
                    ("yesstyle_observed:anua", ts), ("yesstyle_observed:cosrx", ts)))
            with patch.dict(scrape.STORES, {domain: gen}):
                scrape.scrape_store(db, domain, "run")
            ids = dict(db.execute("SELECT ext_id, id FROM listing WHERE store=?", (domain,)))
            self.assertEqual(set(missing(db)), {ids["2"]})
            self.assertEqual(db.execute("SELECT status FROM scrape_run").fetchone()[0], "parcial")
            self.assertNotIn("yesstyle:cosrx", dict(db.execute("SELECT key, value FROM meta")))

    def test_yesstyle_full_window_observed_not_completed_and_rotates(self):
        with database() as (db, path), adapter("yesstyle", path) as ys:
            save(db, "local.cl", [item(1), item(2, "Cosrx"), item(3)])
            page = (FIXTURES / "yesstyle_cards.html").read_text(encoding="utf-8")
            sitemap = "".join(f"<loc>https://www.yesstyle.com/en/{v}/list.html/bpt.299_bid.{i}</loc>"
                              for i, v in enumerate(("anua", "cosrx"), 1))
            asked = []
            def get(url, **_):
                asked.append(url)
                return sitemap if url.endswith(".xml") else page
            with patch.object(ys, "get", get), patch.object(ys, "PAGE_SIZE", 3), patch.object(ys, "YESSTYLE_MAX_BRANDS", 1):
                items, result = scrape.collect(ys.yesstyle("www.yesstyle.com"))
                self.assertTrue(result.partial)
                self.assertEqual({k for k, _ in result.metadata}, {"yesstyle_observed:anua"})
                self.assertEqual(db.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 0)
                save(db, "www.yesstyle.com", items, metadata=result.metadata)
                asked.clear()
                scrape.collect(ys.yesstyle("www.yesstyle.com"))
                self.assertIn("/cosrx/", asked[1])

    def test_yesstyle_short_valid_page_completes_but_unparsed_card_does_not(self):
        with database() as (db, path), adapter("yesstyle", path) as ys:
            save(db, "local.cl", [item(1)])
            page = (FIXTURES / "yesstyle_cards.html").read_text(encoding="utf-8")
            sitemap = "<loc>https://www.yesstyle.com/en/anua/list.html/bpt.299_bid.1</loc>"
            with patch.object(ys, "get", side_effect=[sitemap, page]):
                _, result = scrape.collect(ys.yesstyle("www.yesstyle.com"))
                self.assertFalse(result.partial)
                self.assertIn("yesstyle:anua", dict(result.metadata))
            broken = page + '<a class="itemContainer" href="/en/x/info.html/pid.999"><b>€1</b></a>'
            with patch.object(ys, "get", side_effect=[sitemap, broken]):
                _, result = scrape.collect(ys.yesstyle("www.yesstyle.com"))
                self.assertTrue(result.partial)
                self.assertNotIn("yesstyle:anua", dict(result.metadata))

    def test_stylevana_page_limit_never_completes_and_rotation_uses_observed(self):
        with database() as (db, path), adapter("stylevana", path) as sv:
            save(db, "local.cl", [item(1), item(2, "Cosrx"), item(3)])
            page = (FIXTURES / "stylevana_cards.html").read_text(encoding="utf-8")
            with patch.object(sv, "get", return_value=page) as get, patch.object(sv, "STYLEVANA_MAX_PAGES", 1), patch.object(sv, "STYLEVANA_MAX_REQUESTS", 1):
                items, result = scrape.collect(sv.stylevana("www.stylevana.com"))
                self.assertTrue(result.partial)
                self.assertEqual({k for k, _ in result.metadata}, {"stylevana_observed:anua"})
                self.assertEqual(get.call_count, 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 0)
                save(db, "www.stylevana.com", items, metadata=result.metadata)
                get.reset_mock()
                scrape.collect(sv.stylevana("www.stylevana.com"))
                self.assertIn("/cosrx.html", get.call_args.args[0])

    def test_stylevana_incomplete_page_never_completes(self):
        with database() as (db, path), adapter("stylevana", path) as sv:
            save(db, "local.cl", [item(1)])
            page = (FIXTURES / "stylevana_cards.html").read_text(encoding="utf-8")
            page = page.replace('>251</span>', '>36</span>')
            with patch.object(sv, "get", return_value=page):
                _, result = scrape.collect(sv.stylevana("www.stylevana.com"))
                self.assertTrue(result.partial)
                self.assertNotIn("stylevana:anua", dict(result.metadata))

    def test_blocked_and_known_incomplete_adapters_return_partial(self):
        for name, function, pages_name in (("dbs", "dbs", "BRANDS"), ("sfcc", "sfcc", "PAGES"),
                                          ("paris", "paris", "PAGES"), ("nextdata", "farmaloop", "FARMALOOP_PAGES")):
            with self.subTest(adapter=function), adapter(name) as mod:
                with patch.object(mod, pages_name, ["first"]), patch.object(mod, "get", side_effect=Blocked("HTTP 429")) as get:
                    items, result = scrape.collect(getattr(mod, function)("example.com"))
                    self.assertEqual(items, [])
                    self.assertTrue(result.partial)
                    self.assertEqual(get.call_count, 1)

    def test_sfcc_more_and_dbs_short_signal_partial_without_block(self):
        for name, pages_name, parsed in (("sfcc", "PAGES", ([item(1)], {}, True)),
                                         ("dbs", "BRANDS", ([item(1)], 2))):
            with self.subTest(adapter=name), adapter(name) as mod:
                with patch.object(mod, pages_name, ["first"]), patch.object(mod, "get", return_value="fixture"), patch.object(mod, "parse_listing", return_value=parsed):
                    items, result = scrape.collect(getattr(mod, name)("example.com"))
                    self.assertEqual(len(items), 1)
                    self.assertTrue(result.partial)

    def test_ecofarmacias_stops_after_block_with_partial(self):
        with adapter("ecofarmacias") as mod:
            def wc(*_):
                raise Blocked("HTTP 403")
                yield
            with patch.object(mod, "woocommerce", wc):
                _, result = scrape.collect(mod.ecofarmacias("example.com"))
                self.assertTrue(result.partial)

    def test_jumpseller_failed_page_preserves_other_items_as_partial(self):
        with adapter("jsonld") as mod:
            sitemap = "<loc>https://example.com/a</loc><loc>https://example.com/b</loc>"
            with patch.object(mod, "get", side_effect=[sitemap, "page", Blocked("HTTP 429")]), patch.object(mod, "jsonld_products", return_value=[{"name": "Serum"}]), patch.object(mod, "item_from_jsonld", return_value=item(1)):
                items, result = scrape.collect(mod.jumpseller("example.com"))
                self.assertEqual(len(items), 1)
                self.assertTrue(result.partial)

    def test_novasalud_missing_counter_and_vtex_limit_signal_partial(self):
        with adapter("novasalud") as mod:
            with patch.object(mod, "get", return_value="fixture"), patch.object(mod, "parse_listing", return_value=([item(1)], 0, None)):
                self.assertTrue(scrape.collect(mod.novasalud("example.com"))[1].partial)
        with adapter("vtex") as mod:
            with patch.object(mod, "get", return_value=[{}]), patch.object(mod, "STEP", 1), patch.object(mod, "MAX_ITEMS", 1), patch.object(mod, "parse_product", return_value=[item(1)]), patch.object(mod, "NOT_COSMETICS", {}):
                self.assertTrue(scrape.collect(mod.vtex("example.com", categories=["1"]))[1].partial)


if __name__ == "__main__":
    unittest.main()
