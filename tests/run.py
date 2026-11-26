"""Descubre todas las funciones test_*; cada suite usa una base temporal, nunca data/yumori.db."""
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_file(path):
    import catalog
    import db
    import match
    import server

    with tempfile.TemporaryDirectory(prefix="yumori-tests-") as tmp, ExitStack() as stack:
        isolated = Path(tmp) / "test.db"
        con = db.connect(isolated)
        con.close()
        for module in (db, catalog, match, server):
            stack.enter_context(patch.object(module, "DB", isolated))
        init, history = catalog.Catalog.__init__, catalog.Catalog.history

        def fixture_catalog(self, source, *args, **kwargs):
            init(self, source, *args, **kwargs)
            self._test_source = source

        def fixture_history(self, connection, product):
            # La ficha abre server.DB, pero su historial debe provenir de la MISMA fixture
            # que sus ofertas, no de listings reales con ids coincidentes.
            return history(self, self._test_source, product)

        stack.enter_context(patch.object(catalog.Catalog, "__init__", fixture_catalog))
        stack.enter_context(patch.object(catalog.Catalog, "history", fixture_history))
        namespace = runpy.run_path(str(path), run_name="yumori_tests")
        tests = sorted((name, fn) for name, fn in namespace.items() if name.startswith("test_") and callable(fn))
        classes = [cls for cls in namespace.values() if isinstance(cls, type) and issubclass(cls, unittest.TestCase)
                   and cls is not unittest.TestCase]
        if not tests and not classes:
            raise RuntimeError(f"No hay pruebas en {path.name}")
        original_catalog = server.get_catalog

        def isolated_test(fn):
            def run():
                with patch.object(server, "get_catalog", original_catalog):
                    fn()
            return run

        suite = unittest.TestSuite(unittest.FunctionTestCase(isolated_test(fn), description=name) for name, fn in tests)
        for cls in classes:
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
        return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--file":
        return 0 if run_file(Path(sys.argv[2])) else 1
    failed = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for test in sorted(Path(__file__).parent.glob("test_*.py")):
        result = subprocess.run([sys.executable, "-B", __file__, "--file", str(test)], cwd=ROOT,
                                env=env, capture_output=True, text=True)
        print(f"{'OK   ' if result.returncode == 0 else 'FALLA'} {test.name}", flush=True)
        print(result.stdout + result.stderr, end="", flush=True)
        if result.returncode:
            failed.append(test.name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
