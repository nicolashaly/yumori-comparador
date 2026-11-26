"""Agrupa listings de distintas tiendas en un mismo producto y compara precios.

Uso: python match.py [texto ...]   (filtra por palabras del nombre; sin texto: mayor diferencia de precio)
"""
import re
import sqlite3
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict

from db import DB, RETIRED

# vendors que en realidad son el nombre de la tienda, no una marca
NOT_BRANDS = {"sokobox", "rakuen", "rakuencosmeticacoreana", "arumi", "quecoreana", "kosmeticos", "nookichile", "dermotiendachile"}
MINI = {"miniatura", "mini", "muestra", "sample", "travel"}
STOP = {"protector", "solar", "filtro", "pa", "de", "con", "para", "el", "la", "y", "the", "single"}


# Sobre texto sin tildes ni mayúsculas. "sleeping pack" o "sheet mask 10ea" NO son packs, pero un título que EMPIEZA con "Pack" sí ("Pack: Masajeador
# LED + Sérum"). "Effaclar Duo+" es una crema de La Roche-Posay, no un dúo.
PACK = re.compile(r"^\W*pack\b|\b((?<!effaclar )duos?|trios?|sets?|kits?|bundles?|combos?|rutina|routine|pack of [2-9]|[2-9][- ]?packs?|1\+1)\b")


def words(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def is_pack(text):
    """¿El título describe varios productos juntos (set, kit, duo, rutina, bundle, 2-pack)?"""
    return bool(PACK.search(words(text)))


def parse(text, preserve_spf=True):
    """-> (tokens, sizes, mini). Los tamaños (100ml, 50g) salen de los tokens."""
    s = words(text)
    if preserve_spf:
        s = re.sub(r"\b(?:spf|fps)\s*(\d+)\s*\+?", r" spf\1 ", s)
    sizes = tuple(sorted(
        n.replace(",", ".") + ("g" if u in ("g", "gr") else u)
        for n, u in re.findall(r"(\d+(?:[.,]\d+)?)\s*(ml|gr|g|oz|kg)\b", s)
    ))
    if any(x.endswith(("ml", "g")) for x in sizes):
        sizes = tuple(x for x in sizes if not x.endswith("oz"))  # "100 g / 3.52 oz": sobra la de oz
    s = re.sub(r"(\d+(?:[.,]\d+)?)\s*(ml|gr|g|oz|kg)\b", " ", s)
    s = re.sub(r"\b1[- ]?(?:pack|ea)\b", " ", s)  # "1-Pack"/"1ea": unidad normal de tiendas oficiales; "2-Pack"/"3ea" siguen distinguiendo
    s = re.sub(r"\d+(?:[.,]\d+)?\s*fl\.?\s*oz\b", " ", s)  # "3.38 fl. oz": el tamaño ya viene en ml
    tokens = re.findall(r"[a-z0-9]+", s.replace("&", " "))
    size_nums = {re.sub(r"\D", "", x) for x in sizes}
    mini = bool(MINI & set(tokens))
    tokens = [t for t in tokens if t not in MINI and t not in STOP
              and not (not preserve_spf and re.fullmatch(r"(?:spf|fps)\d*", t)) and t not in size_nums]
    return tokens, sizes, mini


def find_sub(tokens, sub):
    for i in range(len(tokens) - len(sub) + 1):
        if tokens[i:i + len(sub)] == sub:
            return i
    return -1


def key_of(vendor, text, brands, preserve_spf=True):
    """Clave de producto: (marca, palabras, tamaños, es_miniatura)."""
    tokens, sizes, mini = parse(text, preserve_spf=preserve_spf)
    v = re.findall(r"[a-z0-9]+", words(vendor or "").replace("&", " "))
    # más larga primero; entre marcas del mismo largo, alfabético: `brands` es un set y su orden cambia entre ejecuciones, así que un
    # título con dos marcas empatadas podía quedar con una u otra marca (y otro id de producto) cada vez que se reinicia el servidor
    cands = [tuple(v)] if tuple(v) in brands else sorted(brands, key=lambda b: (-len(b), b))
    for b in cands:
        i = find_sub(tokens, list(b))
        if i >= 0 or b == tuple(v):
            if i >= 0:
                tokens = tokens[:i] + tokens[i + len(b):]
            return b, frozenset(tokens), sizes, mini
    return (), frozenset(tokens), sizes, mini


def load(db, gtin=True):
    """Agrupa los listings en productos: {clave: filas}. `gtin=False` es el agrupamiento solo por texto."""
    return load_ex(db, gtin)[0]


def load_ex(db, gtin=True, preserve_spf=True):
    """-> (grupos, info). `info`: `origin` {listing_id: clave de texto, antes de unir por GTIN}, `gtin` {clave ganadora: [claves absorbidas]}
    y `stats` (uniones hechas y bloqueadas por cada salvaguarda)."""
    rows = db.execute("""
        SELECT l.id, l.store, l.title, l.variant, l.vendor, l.url, p.price, p.compare_at, p.available,
               l.image, l.rating, l.reviews, l.currency, l.description, l.images, l.gtin
        FROM listing l JOIN price p ON p.listing_id = l.id
        WHERE p.rowid = (SELECT rowid FROM price WHERE listing_id = l.id ORDER BY ts DESC, rowid DESC LIMIT 1)
          AND l.store NOT IN (%s)""" % ",".join("?" * len(RETIRED)), sorted(RETIRED)).fetchall()
    brands = set()
    for r in rows:
        b = tuple(re.findall(r"[a-z0-9]+", words(r[4] or "").replace("&", " ")))
        if b and "".join(b) not in NOT_BRANDS:
            brands.add(b)
    groups = defaultdict(list)
    for r in rows:
        groups[key_of(r[4], f"{r[2]} {r[3] or ''}", brands, preserve_spf=preserve_spf)].append(r)
    # una tienda a veces omite el tamaño en el título: se une al único grupo con tamaño y mismas palabras
    sized = defaultdict(list)
    for k in groups:
        if k[2]:
            sized[(k[0], k[1], k[3])].append(k)
    # ...pero solo si el precio es parecido (±30%; entre monedas ±60%, porque el envío y el tipo de cambio mueven más); si no,
    # probablemente es otro tamaño (ej. una miniatura)
    fx = db.execute("SELECT usd_clp FROM fx ORDER BY date DESC LIMIT 1").fetchone()
    fx = fx[0] if fx else None

    def pesos(r):  # precio en pesos comparable: USD en centavos -> CLP con IVA 19%
        return r[6] if r[12] == "CLP" else (r[6] / 100 * fx * 1.19 if fx else 0)

    for k in [k for k in groups if not k[2]]:
        cands = sized.get((k[0], k[1], k[3]), [])
        prices = [pesos(r) for r in groups[k] if pesos(r) > 0]
        base = [pesos(r) for r in groups[cands[0]] if pesos(r) > 0] if len(cands) == 1 else []
        if prices and base:
            med = statistics.median(base)
            lo, hi = (0.7, 1 / 0.7) if all(r[12] == "CLP" for r in groups[k]) else (0.4, 2.5)
            if all(lo <= p / med <= hi for p in prices):
                groups[cands[0]] += groups.pop(k)
    origin = {r[0]: k for k, rs in groups.items() for r in rs}
    if not gtin:
        return groups, {"origin": origin, "gtin": {}, "similar": {}, "stats": Counter()}
    groups, merged, stats = merge_gtin(groups)
    groups, similar, stats2 = merge_similar(groups, pesos)
    return groups, {"origin": origin, "gtin": merged, "similar": similar, "stats": stats + stats2}


def sortkey(k):
    """Orden total de las claves (tienen un frozenset): sirve para desempatar siempre igual."""
    return k[0], tuple(sorted(k[1])), k[2], k[3]


def merge_gtin(groups):
    """Segundo criterio, después del texto: los grupos que comparten un GTIN (14 dígitos) son el mismo producto. Unión transitiva.

    Se une solo si no hay motivo para dudar; cada motivo se cuenta en `stats`:
    - pack: un pack con un producto suelto;
    - miniatura: una miniatura con el tamaño normal;
    - tamaño: tamaños declarados distintos y no vacíos (un código compartido entre tamaños es un error de la tienda);
    - código repetido: una misma tienda usa el código en 2 o más productos de texto distintos, así que no identifica nada (se ignora entero).
    Nunca separa lo que el texto ya unió. La clave del grupo unido es la del grupo con más listings (a igualdad, la menor en orden):
    así el id no depende del orden de carga y, en el caso típico, el grupo grande conserva su id.
    -> (grupos, {clave ganadora: [claves absorbidas]}, stats)"""
    keys = sorted(groups, key=sortkey)
    parent = {k: k for k in keys}
    props = {k: ({any(is_pack(f"{r[2]} {r[3] or ''}") for r in groups[k])}, {k[3]}, {k[2]} - {()},
                 {t for t in k[1] if re.fullmatch(r"spf\d+", t)}) for k in keys}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    by_gtin = defaultdict(set)
    store_keys = defaultdict(lambda: defaultdict(set))  # gtin -> tienda -> grupos de texto en que la tienda lo usa
    for k in keys:
        for r in groups[k]:
            if r[15]:
                by_gtin[r[15]].add(k)
                store_keys[r[15]][r[1]].add(k)
    seen, blocked, repeated = set(), {}, set()  # pares ya intentados; par bloqueado -> motivo; códigos que una tienda repite
    for g in sorted(by_gtin):
        if any(len(v) > 1 for v in store_keys[g].values()):  # una misma tienda lo pone en productos distintos (Unnie: dos bálsamos Banila Co): el código no identifica
            repeated.add(g)
            continue
        ks = sorted(by_gtin[g], key=sortkey)
        for k in ks[1:]:
            a, b = find(ks[0]), find(k)
            if a == b or (ks[0], k) in seen:
                continue
            seen.add((ks[0], k))
            (pa, ma, sa, fa), (pb, mb, sb, fb) = props[a], props[b]
            why = "pack" if pa != pb else "miniatura" if ma != mb else "tamaño" if len(sa | sb) > 1 else "spf" if len(fa | fb) > 1 else None
            if why:
                blocked[frozenset((ks[0], k))] = why
                continue
            parent[b] = a
            props[a] = (pa | pb, ma | mb, sa | sb, fa | fb)
    comps = defaultdict(list)
    for k in keys:
        comps[find(k)].append(k)
    out, merged = {}, {}
    stats = Counter(bloqueada_pack=0, bloqueada_miniatura=0, bloqueada_tamaño=0, bloqueada_codigo_repetido=len(repeated))
    for why in blocked.values():
        stats[f"bloqueada_{why}"] += 1
    win = {}
    for ks in comps.values():
        w = min(ks, key=lambda k: (-len(groups[k]), sortkey(k)))
        for k in ks:
            win[k] = w
        if len(ks) > 1:
            merged[w] = [k for k in ks if k != w]
            stats["uniones"] += len(ks) - 1
    for k, rows in groups.items():
        if win[k] == k:
            out[k] = rows + [r for o in merged.get(k, []) for r in groups[o]]
    return out, merged, stats


# Palabras que, si solo las tiene uno de los dos nombres, indican otra variante u otro formato ("Fluid" contra "Fluid Color", "Serum" contra
# "Serum Cream"): sobrar una de ellas impide la unión por nombre parecido. Sin tildes ni mayúsculas (ver words()).
VARIANT = set("""light ligera ligero rich riche rica color tinted tinte tono toque plus forte intense intensive intensivo max ultra extra night noche
nocturna nocturno day dia diurna kids kid ninos nino infantil baby bebe men hombre man oil aceite spray gel crema cream serum suero fluid fluido
mist bruma stick barra mousse espuma balm balsamo lotion locion toner tonico mask mascarilla ampoule ampolla essence esencia eye ojos contorno
lip labios body corporal cuerpo hand manos foot pies pad pads patch patches parches cleanser limpiador limpiadora foam wash water agua micelar
micellar refill recarga repuesto sensitive sensible oily grasa grasas dry seca secas mixta normal pump capsule capsulas cushion powder polvo
milk leche emulsion emulsión jelly sheet tablet tabletas peeling exfoliante scrub soap jabon shampoo champu acondicionador
rose english unscented fragrance aroma perfume lavender cherry musk jasmine""".split())


SPF = re.compile(r"\b(?:spf|fps|f\.p\.s)")


def merge_similar(groups, pesos):
    """Tercer criterio, después del texto y el GTIN: un grupo cuyas palabras están TODAS en el nombre de otro grupo de la misma marca y tamaño
    es el mismo producto escrito más corto (Ahumada: "Ampoule Tone Brightening 100 mL" de SKIN1004, frente a "SKIN1004 Madagascar Centella Tone
    Brightening Capsule Ampoule 100ml"). Une solo si no hay motivo para dudar; cada motivo se cuenta en `stats`:
    - ambiguo: el nombre corto cabe en 2 o más grupos;
    - misma tienda: una tienda vende los dos (para ella son productos distintos);
    - variante: al nombre corto le falta una palabra de variante o formato (VARIANT), un número o una sigla de 1 o 2 letras ("Duo+ M"),
      o solo uno de los dos menciona un filtro solar (parse() descarta "SPF50", así que "Crema Bariéderm-CICA" y "Crema SPF50+ Bariéderm-CICA"
      se verían iguales);
    - precio: los precios no se parecen (±30%; entre monedas, 0,4 a 2,5 veces).
    Exige marca, tamaño declarado igual en ambos, misma condición de pack y miniatura, y al menos 2 palabras en el nombre corto.
    No es transitivo: un grupo se une a lo más con uno. La clave del unido es la del grupo con más listings (como en merge_gtin).
    -> (grupos, {clave ganadora: [claves absorbidas]}, stats)"""
    stats = Counter(similar_uniones=0, similar_ambiguo=0, similar_misma_tienda=0, similar_variante=0, similar_precio=0)
    pack = {k: any(is_pack(f"{r[2]} {r[3] or ''}") for r in rows) for k, rows in groups.items()}
    spf = {k: any(SPF.search(words(f"{r[2]} {r[3] or ''}")) for r in rows) for k, rows in groups.items()}
    bucket = defaultdict(list)  # (marca, tamaños, miniatura, pack) -> claves
    for k in sorted(groups, key=sortkey):
        if k[0] and k[2]:
            bucket[(k[0], k[2], k[3], pack[k])].append(k)
    target = {}  # grupo corto -> grupo largo
    for ks in bucket.values():
        for a in ks:
            if len(a[1]) < 2:
                continue
            sup = [b for b in ks if b != a and a[1] < b[1]]
            if not sup:
                continue
            if len(sup) > 1:
                stats["similar_ambiguo"] += 1
                continue
            b = sup[0]
            extra = b[1] - a[1]
            pa, pb = [pesos(r) for r in groups[a] if pesos(r) > 0], [pesos(r) for r in groups[b] if pesos(r) > 0]
            cross = {r[12] for r in groups[a] + groups[b]} != {"CLP"}
            lo, hi = (0.4, 2.5) if cross else (0.7, 1 / 0.7)
            if {r[1] for r in groups[a]} & {r[1] for r in groups[b]}:
                stats["similar_misma_tienda"] += 1
            elif extra & VARIANT or any(len(t) <= 2 or t.isdigit() for t in extra) or spf[a] != spf[b]:
                stats["similar_variante"] += 1
            elif not pa or not pb or not all(lo <= p / statistics.median(pb) <= hi for p in pa):
                stats["similar_precio"] += 1
            else:
                target[a] = b
    out, merged, where = dict(groups), {}, {}  # where: grupo absorbido -> grupo que lo contiene ahora
    for a, b in sorted(target.items(), key=lambda x: sortkey(x[0])):
        if b in target:  # sin cadenas: si el largo también cabe en otro, no se une nada
            continue
        b = where.get(b, b)
        if {r[1] for r in out[a]} & {r[1] for r in out[b]}:
            stats["similar_misma_tienda"] += 1
            continue
        w, l = (a, b) if (-len(out[a]), sortkey(a)) < (-len(out[b]), sortkey(b)) else (b, a)
        out[w] = out[w] + out.pop(l)
        merged[w] = merged.pop(l, []) + merged.get(w, []) + [l]
        for k, v in list(where.items()):
            if v == l:
                where[k] = w
        where[l] = w
        stats["similar_uniones"] += 1
    return out, merged, stats


def gtin_conflicts(groups):
    """Productos con 2 o más GTIN distintos: [(clave, {gtin: [(tienda, título)]})]. Pueden ser una unión errónea del texto o un envase
    renovado con código nuevo; no se separan solos, se revisan a mano (python match.py --gtin-conflictos)."""
    out = []
    for k, rows in groups.items():
        codes = defaultdict(list)
        for r in rows:
            if r[15]:
                codes[r[15]].append((r[1], r[2]))
        if len(codes) > 1:
            out.append((k, dict(codes)))
    return sorted(out, key=lambda x: sortkey(x[0]))


def first_price(db, lid):
    return db.execute("SELECT price FROM price WHERE listing_id=? ORDER BY ts, rowid LIMIT 1", (lid,)).fetchone()[0]


def clp(n):
    return f"${n:,}".replace(",", ".")


def compare(groups, db, query):
    """Productos vendidos en >=2 tiendas (precio > 0, al menos una con stock), ordenados por diferencia de precio.

    Cada resultado es (diferencia, nombre, con_stock, agotados); la diferencia solo mira las tiendas con stock."""
    out = []
    for (brand, toks, sizes, mini), rows in groups.items():
        best = {}  # tienda -> listing más barato, prefiriendo los que tienen stock
        for r in rows:
            if r[12] == "CLP" and r[6] > 0 and (r[1] not in best or (r[8], -r[6]) > (best[r[1]][8], -best[r[1]][6])):
                best[r[1]] = r
        ranked = sorted(best.values(), key=lambda r: r[6])
        stock, out_of = [r for r in ranked if r[8]], [r for r in ranked if not r[8]]
        if len(best) < 2 or not stock:
            continue
        name = f"{' '.join(brand)} {ranked[0][2]}"
        if not all(q in words(name) for q in query):
            continue
        spread = (stock[-1][6] - stock[0][6]) / stock[-1][6]
        out.append((spread, stock[0][2], stock, out_of))
    return sorted(out, key=lambda x: -x[0])


def show(results, db, limit=15):
    for spread, name, stock, out_of in results[:limit]:
        print(f"\n{name}  -  " + (f"hasta {spread:.0%} de diferencia" if len(stock) > 1 else "solo 1 tienda con stock"))
        for i, r in enumerate(stock + out_of):
            first = first_price(db, r[0])
            trend = "" if first == r[6] else f"  [{'bajo' if r[6] < first else 'subio'} desde {clp(first)}]"
            tag = "  <- mejor" if i == 0 else "  (sin stock)" if not r[8] else ""
            print(f"  {clp(r[6]):>9}  {r[1]:<28}{tag}{trend}")


def show_conflicts(groups):
    found = gtin_conflicts(groups)
    print(f"{len(found)} productos con 2+ GTIN distintos (no se separan solos)")
    for k, codes in found:
        print(f"\n{' '.join(k[0]) or '(sin marca)'} | {' '.join(sorted(k[1]))} | {', '.join(k[2]) or 'sin tamaño'}")
        for g, items in sorted(codes.items()):
            print(f"  {g}: " + "; ".join(f"{store} - {title}" for store, title in items))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    db = sqlite3.connect(DB)
    if sys.argv[1:] == ["--gtin-conflictos"]:
        show_conflicts(load(db))
        sys.exit()
    results = compare(load(db), db, [words(a) for a in sys.argv[1:]])
    print(f"{len(results)} productos en 2+ tiendas")
    show(results, db)
