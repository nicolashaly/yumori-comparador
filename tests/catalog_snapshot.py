"""Referencia de matching: python -B tests/catalog_snapshot.py <copia.db>.

Solo lectura, sin migraciones ni sincronización de alias. Guardar el JSON en data/, fuera de git.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from catalog import Catalog, pid_of
from match import load_ex


def snapshot(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as con:
        cat = Catalog(con, sync=False)
        groups, _ = load_ex(con)
        mapping = {str(row[0]): pid_of(*key) for key, rows in groups.items() for row in rows}
        return {"products": len(cat.products), "multi_store": sum(len(p.offers) > 1 for p in cat.products),
                "listing_products": dict(sorted(mapping.items(), key=lambda kv: int(kv[0]))), "ids": sorted(cat.by_id)}


if __name__ == "__main__":
    print(json.dumps(snapshot(sys.argv[1]), ensure_ascii=False, sort_keys=True, indent=2))
