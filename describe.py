"""Descripción propia de un producto a partir de DATOS extraídos del texto de las tiendas.

No copia ni parafrasea frases de las tiendas: solo detecta hechos (tipo de producto, compuestos, beneficios, tipos de piel,
factor solar) y escribe un texto nuevo con plantillas. Si el texto no trae un dato, no se inventa.
Sin dependencias ni red: solo procesa texto.
"""
import re

from match import words

MINI_WORDS = {"mini", "minis", "miniatura", "miniaturas"}  # se quitan de los nombres de los productos del pack
NEGATIONS = {"sin", "no", "non", "libre", "without", "evitar", "evita"}  # "sin retinol", "libre de zinc", "non oily": no cuentan

# (etiqueta que se muestra, frases en minúsculas y sin tildes, en español e inglés)
ACTIVES = [
    ("niacinamida", ["niacinamida", "niacinamide", "vitamina b3"]),
    ("ácido hialurónico", ["acido hialuronico", "hyaluronic acid", "hialuronato", "sodium hyaluronate", "hyaluronic"]),
    ("retinol", ["retinol"]),
    ("retinal", ["retinal", "retinaldehido", "retinaldehyde"]),
    ("bakuchiol", ["bakuchiol"]),
    ("centella asiática", ["centella", "cica", "madecassoside", "madecasosido", "asiaticoside"]),
    ("vitamina C", ["vitamina c", "vitamin c", "acido ascorbico", "ascorbic acid", "ascorbyl"]),
    ("vitamina E", ["vitamina e", "vitamin e", "tocoferol", "tocopherol"]),
    ("PDRN", ["pdrn", "polydeoxyribonucleotide", "polideoxirribonucleotido", "adn de salmon", "salmon dna"]),
    ("péptidos", ["peptido", "peptidos", "peptide", "peptides", "matrixyl"]),
    ("ceramidas", ["ceramida", "ceramidas", "ceramide", "ceramides"]),
    ("ácido salicílico (BHA)", ["acido salicilico", "salicylic acid", "bha", "betaine salicylate"]),
    ("AHA", ["aha", "acido glicolico", "glycolic acid", "acido lactico", "lactic acid", "acido mandelico", "mandelic acid"]),
    ("ácido azelaico", ["acido azelaico", "azelaic acid"]),
    ("ácido tranexámico", ["acido tranexamico", "tranexamic acid", "txa"]),
    ("arbutina", ["arbutina", "arbutin"]),
    ("glutatión", ["glutation", "glutathione"]),
    ("escualano", ["escualano", "squalane", "squalene", "escualeno"]),
    ("mucina de caracol", ["mucina de caracol", "snail mucin", "secrecion de caracol", "snail secretion", "mucina", "snail"]),
    ("propóleo", ["propoleo", "propolis"]),
    ("miel", ["miel", "honey"]),
    ("arroz", ["arroz", "rice"]),
    ("té verde", ["te verde", "green tea"]),
    ("árbol de té", ["arbol de te", "tea tree"]),
    ("artemisa", ["artemisa", "mugwort", "artemisia"]),
    ("heartleaf (Houttuynia)", ["heartleaf", "houttuynia", "hoja de corazon"]),
    ("extracto de pino", ["pino", "pine"]),
    ("pantenol (vitamina B5)", ["pantenol", "panthenol", "vitamina b5"]),
    ("colágeno", ["colageno", "collagen"]),
    ("ginseng", ["ginseng"]),
    ("aloe vera", ["aloe"]),
    ("alantoína", ["alantoina", "allantoin"]),
    ("adenosina", ["adenosina", "adenosine"]),
    ("cafeína", ["cafeina", "caffeine"]),
    ("coenzima Q10", ["coenzima q10", "coenzyme q10"]),
    ("soja", ["soja", "soybean", "soy"]),
    ("yuzu", ["yuzu", "yuja"]),
    ("zinc", ["zinc"]),
]

# (frase completa, con objeto explícito, para "pensado para ..."; frases que lo indican).
# Un verbo suelto sin objeto ("pensado para calmar") queda ambiguo: calmar ¿qué? Por eso cada frase dice a qué se aplica.
BENEFITS = [
    ("hidratar la piel", ["hidrata", "hidratacion", "hidratante", "hidratar", "hydrating", "hydration", "hydrate", "moisturizing", "moisturizer", "humecta"]),
    ("calmar la piel", ["calma", "calmante", "calmar", "calming", "soothing", "soothe", "alivia", "aliviar", "irritacion", "rojeces", "enrojecimiento", "redness"]),
    ("dar luminosidad a la piel", ["ilumina", "iluminar", "iluminador", "luminosidad", "brightening", "radiance", "radiante", "glow"]),
    ("prevenir los signos de la edad", ["antiedad", "anti edad", "antienvejecimiento", "anti aging", "antiaging", "arrugas", "wrinkle", "wrinkles", "fine lines"]),
    ("unificar el tono de la piel y reducir la apariencia de manchas",
     ["manchas", "hiperpigmentacion", "dark spots", "dark spot", "pigmentation", "discoloration", "tono desigual", "uneven tone"]),
    ("cuidar los poros", ["poros", "pore", "pores", "sebo", "sebum"]),
    ("controlar las imperfecciones", ["acne", "imperfecciones", "blemish", "blemishes", "espinillas", "puntos negros", "blackheads"]),
    ("reforzar la barrera cutánea", ["barrera cutanea", "skin barrier", "moisture barrier"]),
    # "uva" suelta no: en español es la fruta ("extracto de uva" hacía que un bálsamo labial dijera "proteger la piel del sol")
    ("proteger la piel del sol", ["spf", "protector solar", "sunscreen", "sun protection", "proteccion solar", "rayos uva", "uvb"]),
    ("limpiar la piel", ["limpia", "limpiar", "limpieza", "limpiador", "cleansing", "cleanser", "desmaquilla"]),
    ("exfoliar la piel con suavidad", ["exfolia", "exfoliante", "exfoliar", "exfoliating", "exfoliation", "peeling"]),
    ("nutrir la piel", ["nutre", "nutritivo", "nutrir", "nourishing", "nourish", "nutricion", "nutrition"]),
    ("aportar firmeza a la piel", ["firmeza", "reafirma", "reafirmante", "firming", "lifting"]),
]

# (etiqueta, frases). En este orden se muestran.
SKIN_TYPES = [
    ("Piel grasa", ["piel grasa", "pieles grasas", "piel oleosa", "pieles oleosas", "oily skin", "oily"]),
    ("Piel mixta", ["piel mixta", "pieles mixtas", "combination skin"]),
    ("Piel seca", ["piel seca", "pieles secas", "dry skin", "piel deshidratada", "pieles deshidratadas", "dehydrated skin"]),
    ("Piel sensible", ["piel sensible", "pieles sensibles", "sensitive skin", "sensitive", "piel reactiva", "pieles reactivas"]),
    ("Piel normal", ["piel normal", "pieles normales", "normal skin"]),
    ("Piel con tendencia acneica", ["piel acneica", "pieles acneicas", "tendencia acneica", "acne prone", "piel con acne", "pieles con acne", "propensa al acne"]),
    ("Piel madura", ["piel madura", "pieles maduras", "mature skin"]),
]
ALL_SKIN = ["todo tipo de piel", "todo tipo de pieles", "todos los tipos de piel", "todos los tipos de pieles", "all skin types", "all skin type"]

# (etiqueta, artículo, frases). El primero que coincida con el NOMBRE del producto gana: los más específicos van primero.
TYPES = [
    ("contorno de ojos", "un", ["eye cream", "eye serum", "eye gel", "eye balm", "contorno de ojos"]),
    ("protector solar", "un", ["sun", "sunscreen", "suncream", "protector solar", "bloqueador solar", "bloqueador", "filtro solar", "sunstick", "sun stick", "spf"]),
    ("parches", "unos", ["patch", "patches", "parche", "parches"]),
    ("accesorio", "un", ["brush", "brushes", "pincel", "pinceles", "roller", "rodillo", "gua sha", "sponge", "esponja", "puff", "tweezer", "pinzas", "mirror", "espejo", "bolsa", "bag", "gift card"]),
    ("producto para el cabello", "un", ["hair", "shampoo", "champu", "conditioner", "acondicionador", "scalp", "cuero cabelludo"]),
    ("producto para cuerpo o manos", "un", ["hand cream", "crema de manos", "hand", "body", "corporal", "shower", "ducha", "foot", "pies", "deodorant", "desodorante", "bath", "soap", "jabon"]),
    ("fragancia", "una", ["perfume", "fragrance", "fragancia", "colonia", "eau de"]),
    ("producto para cejas", "un", ["brow", "brows", "eyebrow", "ceja", "cejas"]),
    ("sombra o paleta", "una", ["eyeshadow", "shadow", "palette", "paleta", "sombra", "sombras", "glitter"]),
    ("delineador o máscara de pestañas", "un", ["eyeliner", "liner", "mascara", "lash", "lashes", "pestanas"]),
    ("rubor o iluminador", "un", ["blush", "blushin", "rubor", "highlighter", "bronzer", "contour"]),
    ("base o cushion", "una", ["cushion", "foundation", "concealer", "corrector", "primer", "bb cream", "cc cream", "makeup base", "base de maquillaje", "setting powder", "pressed powder", "polvo compacto", "compacto", "pact"]),
    ("producto para labios", "un", ["lip", "lips", "labial", "labiales", "tint", "gloss", "lipstick"]),
    ("producto para uñas", "un", ["nail", "nails", "unas", "esmalte"]),
    ("mascarilla de noche", "una", ["sleeping mask", "sleeping pack", "sleeping"]),
    ("mascarilla", "una", ["mask", "masks", "mascarilla", "mascarillas"]),
    ("desmaquillante", "un", ["makeup remover", "desmaquillante", "micellar", "micelar"]),
    ("aceite limpiador", "un", ["cleansing oil", "aceite limpiador", "cleansing balm"]),
    ("limpiador", "un", ["cleanser", "cleansing", "limpiador", "foam", "espuma", "face wash"]),
    ("bálsamo", "un", ["balm", "balsamo"]),
    ("tónico", "un", ["toner", "tonico", "toning"]),
    ("ampolla", "una", ["ampoule", "ampolla"]),
    ("sérum", "un", ["serum", "booster", "shot"]),
    ("esencia", "una", ["essence", "esencia"]),
    ("crema", "una", ["cream", "crema", "moisturizer"]),
    ("emulsión", "una", ["lotion", "emulsion", "locion"]),
    ("bruma", "una", ["mist", "bruma"]),
    ("exfoliante", "un", ["peeling", "exfoliating", "exfoliante", "scrub", "gommage"]),
    ("pads", "unos", ["pad", "pads"]),
]

GROUPS = {"facial": "Cuidado facial", "maquillaje": "Maquillaje", "cabello": "Cabello", "cuerpo": "Cuerpo y manos", "accesorios": "Accesorios"}
KIND_GROUP = {
    **{k: "facial" for k in ("contorno de ojos", "protector solar", "parches", "mascarilla de noche", "mascarilla", "desmaquillante", "aceite limpiador",
                             "limpiador", "bálsamo", "tónico", "ampolla", "sérum", "esencia", "crema", "emulsión", "bruma", "exfoliante", "pads")},
    **{k: "maquillaje" for k in ("producto para cejas", "sombra o paleta", "delineador o máscara de pestañas", "rubor o iluminador", "base o cushion",
                                 "producto para labios", "producto para uñas")},
    "producto para el cabello": "cabello", "producto para cuerpo o manos": "cuerpo", "fragancia": "cuerpo", "accesorio": "accesorios",
}

# Rasgos de maquillaje (y de algunos faciales). Misma regla que los beneficios: 2 o más menciones en el texto, o estar en el nombre.
# (etiqueta que se muestra, frases). El "acabado" se escribe siempre como "Tiene un acabado <etiqueta>" (acabado es masculino: la etiqueta no cambia de género, y sirve también
# para "con destellos" o para dos acabados juntos).
FINISHES = [
    ("mate", ["mate", "mates", "matte"]),
    ("satinado", ["satinado", "satinada", "satinados", "satinadas", "satin"]),
    ("aterciopelado", ["aterciopelado", "aterciopelada", "aterciopelados", "aterciopeladas", "velvet", "velvety", "terciopelo"]),
    ("glossy", ["glossy", "acabado brillante", "acabado glossy", "efecto glossy", "acabado de brillo"]),
    ("luminoso", ["acabado luminoso", "dewy", "glowy", "acabado radiante", "luminous finish"]),
    ("natural", ["acabado natural", "natural finish", "efecto natural"]),
    ("con destellos", ["glitter", "shimmer", "destellos", "metalico", "metalica", "metalizado", "perlado", "perlada", "holografico"]),
]
FINISH_MIX = ["brillante", "brillantes", "acabados"]  # no son un acabado por sí solos, pero delatan que la página describe varios ("mate, satinados o brillantes según el tono")
FINISH_KINDS = {"protector solar"}  # además del maquillaje y de lo que no tiene tipo: "velvet" en una bruma corporal no es un acabado
# (etiqueta que se muestra en "Las tiendas mencionan ...", frases). Solo maquillaje o sin tipo: en un sérum "larga duración" ya tiene otro sentido.
CLAIMS = [
    ("larga duración", ["larga duracion", "alta duracion", "long lasting", "long wear", "long wearing", "larga permanencia", "duradero", "duradera"]),
    ("resistencia al agua", ["waterproof", "resistente al agua", "a prueba de agua", "water resistant", "waterresistant"]),
    ("alta pigmentación", ["alta pigmentacion", "altamente pigmentado", "altamente pigmentada", "high pigment", "highly pigmented", "pigmentacion intensa"]),
]
COVERAGES = [
    ("cobertura ligera", ["cobertura ligera", "cobertura baja", "baja cobertura", "light coverage", "sheer coverage"]),
    ("cobertura media", ["cobertura media", "media cobertura", "medium coverage"]),
    ("cobertura alta", ["cobertura alta", "alta cobertura", "full coverage", "high coverage", "cobertura total", "cobertura completa"]),
    ("cobertura modulable", ["cobertura modulable", "buildable coverage"]),
]
# Sin detalles que no podamos sostener: "vegano" y "no probado en animales" son lo que informa la tienda, y se dicen como tales.
VEGAN = ["vegano", "vegana", "veganos", "veganas", "vegan"]
CRUELTY = ["cruelty free", "libre de crueldad", "sin crueldad animal", "libre de testeo animal", "libre de testeo en animales", "no testeado en animales", "sin testeo en animales", "no probado en animales", "not tested on animals"]
NONMAKEUP = {"facial", "cabello", "cuerpo"}
MAKEUP_CONTEXT = ["maquillaje", "makeup", "labios", "labial", "lip", "lips", "ojos", "parpados", "mejillas", "rubor", "sombra", "sombras", "gloss", "tint",
                  "pestanas", "cejas", "eyeshadow", "blush", "cushion", "foundation", "base de maquillaje", "delineador", "mascara de pestanas"]  # un producto sin tipo solo es maquillaje si el texto lo dice
WATER_NOISE = ["remover", "desmaquillante", "desmaquillar", "remueve", "remueven", "quita", "elimina"]  # un producto que QUITA maquillaje waterproof no lo es
SHADE_MARKS = {"tono", "shade"}  # "tone" no: es "Tone Up" / "Tone Brightening", un efecto del producto
NOT_A_SHADE = {"type", "types", "tipo", "tipos", "color", "colors", "colores", "colours", "size", "sizes", "pcs", "pc", "piece", "pieces", "ea", "set", "pack",
               "in", "step", "pasos", "unidades", "ml", "g"}  # "2 Types", "18 Colors", "3 in 1": cuenta de opciones, no el nombre de un tono


def shade_of(title, makeup=True):
    """Frase (normalizada, con espacios a los lados) del tono o variante que lleva el nombre, o "".
    "Plumping Oil 11 Glam Max Honey Lemon" -> " glam max honey lemon "; "Lip Oil Tono 01 Chill Red" -> " 01 chill red ".
    Dos formas: tras la palabra "tono"/"shade" seguida de un número o código ("Tono 23 Honey"; "Tono Uniforme" no), o tras el ÚLTIMO número suelto del nombre (solo en maquillaje o sin tipo: en un
    sérum "Niacinamide 10 Zinc 1" el número es la concentración y lo que sigue es un compuesto real). Si lo que sigue al número nombra un
    tipo de producto no se toma por tono. "Fecha corta ..." y lo que viene después no es parte del nombre del tono."""
    toks = title.split()
    if "fecha" in toks:
        toks = toks[:toks.index("fecha")]
    for i, t in enumerate(toks):
        if t in SHADE_MARKS and 0 < i and 1 <= len(toks) - i - 1 <= 6 and re.search(r"[0-9]", toks[i + 1]):
            return " " + " ".join(toks[i + 1:]) + " "
    if makeup:
        nums = [i for i, t in enumerate(toks) if re.fullmatch(r"[0-9]{1,3}", t)]
        if nums and nums[-1] >= 1:
            tail = toks[nums[-1] + 1:]
            tail_text = " " + " ".join(tail) + " "
            names_a_benefit = any(mentions(tail_text, phrases) for _, phrases in BENEFITS) or any(t.startswith(("spf", "uv", "pa")) for t in tail)
            if 1 <= len(tail) <= 4 and tail[0] not in NOT_A_SHADE and not names_a_benefit and not any(mentions(tail_text, phrases) for _, _, phrases in TYPES):
                return tail_text
    return ""


def without_shade(text, shade):
    while shade and shade in text:
        text = text.replace(shade, " ")
    return text


def prepare(name, text):
    """-> (título normalizado, texto) sin el nombre del tono: "Honey" en "... 11 Glam Max Honey Lemon" es un color, no miel."""
    title = norm(name)
    coded = norm(re.sub(r"([A-Za-z])-([0-9])", lambda m: m.group(1) + m.group(2), name))  # "Cer-100" es un código, no un número suelto seguido de un tono
    hit = next(((l, a, p) for l, a, p in TYPES if mentions(title, p)), None)
    shade = shade_of(coded, makeup=(KIND_GROUP.get(hit[0]) if hit else None) not in NONMAKEUP)
    return without_shade(title, shade), without_shade(text, shade)


CONTENT_INTRO = re.compile(
    r"(?:incluye|contiene|includes|contains|contenido\s+del\s+(?:set|kit|pack)|"
    r"(?:el|este|la|esta)\s+(?:set|kit|pack|d[uú]o|trio|combo)\s+incluye)\s*:\s*", re.I)
CONTENT_ITEM = re.compile(r"\s*(.+?)\s+([0-9]+(?:[.,][0-9]+)?)\s?(ml|gr|g)\b(?:\s*[,;/+]\s*|\s+)?", re.I)
CONTENT_ITEM_PAREN = re.compile(r"([^()\n.!?;]{1,45}?)\s*\(\s*([0-9]+(?:[.,][0-9]+)?)\s*(ml|gr|g)\s*\)", re.I)
CONTENT_STOP = re.compile(r"\b(?:Beneficios|Benefits|Modo de uso|Ingredientes|Ingredients|C[oó]mo usar|How to use)\b", re.I)

INTROS = ["En su fórmula destacan", "Entre sus compuestos destacan", "Su fórmula incluye", "Contiene, entre otros,"]
INTROS_ONE = ["En su fórmula destaca", "Entre sus compuestos destaca", "Su fórmula incluye", "Contiene"]  # un solo compuesto: singular


def norm(s):
    """Texto en minúsculas, sin tildes ni símbolos, con espacios a los lados y "30 ml" pegado ("30ml")."""
    text = " ".join(re.findall(r"[a-z0-9]+", words(s).replace("&", " ")))
    return " " + re.sub(r"([0-9]) (ml|gr|g)(?= |$)", lambda m: m.group(1) + m.group(2), text) + " "


def mentions(text, phrases):
    """Cuántas veces aparece alguna de las frases sin estar negada ("sin retinol", "non oily")."""
    n = 0
    for phrase in phrases:
        needle = f" {phrase} "
        i = text.find(needle)
        while i >= 0:
            if not NEGATIONS & set(text[max(0, i - 24):i].split()[-3:]):
                n += 1
            i = text.find(needle, i + 1)
    return n


def join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


BENEFIT_OBJECTS = (" a la piel", " la piel")  # el más específico primero, para no cortar "a la piel" a mitad
DANGLING = {"a", "de", "del", "al", "para", "con"}  # si cortar el objeto deja una preposición suelta, no se fusiona


def join_benefits(items):
    """Como join(), pero si todos los beneficios elegidos terminan en el mismo objeto ("la piel"/"a la piel"),
    se menciona una sola vez al final en vez de repetirlo ("hidratar, calmar y limpiar la piel").
    " la piel" es sufijo también de " a la piel" (indirecto): se descarta la fusión si deja una preposición colgando
    (ej. "dar luminosidad a," al cortar solo " la piel" de "dar luminosidad a la piel")."""
    for obj in BENEFIT_OBJECTS:
        if len(items) < 2 or not all(i.endswith(obj) for i in items):
            continue
        heads = [i[:-len(obj)] for i in items]
        if not any(h.split() and h.split()[-1] in DANGLING for h in heads):
            return join(heads) + obj
    return join(items)


def attributes(name, text):
    """Lo que se puede afirmar de un producto: tipo (por su nombre), categoría, tipos de piel y compuestos (por el texto de las tiendas).
    `terms` son las palabras (español e inglés) que lo identifican, para que la búsqueda las entienda."""
    title, text = prepare(name, text)  # sin el nombre del tono: "Honey" de un tono no es miel
    hit = next(((label, art, phrases) for label, art, phrases in TYPES if mentions(title, phrases)), None)
    skin = [(label, phrases) for label, phrases in SKIN_TYPES if mentions(text, phrases)]
    if not skin and mentions(text, ALL_SKIN):
        skin = [("Todo tipo de piel", ALL_SKIN)]
    found = sorted((-(mentions(text, p) + 3 * mentions(title, p)), n, label, p) for n, (label, p) in enumerate(ACTIVES) if mentions(text, p) + mentions(title, p))[:8]
    return {
        "type": (hit[0], hit[1]) if hit else None, "kind": hit[0] if hit else None, "group": KIND_GROUP.get(hit[0]) if hit else None,
        "skin": [label for label, _ in skin], "actives": [label for _, _, label, _ in found],
        "terms": (hit[2] if hit else []) + [t for _, phrases in skin for t in phrases] + [t for *_, phrases in found for t in phrases],
    }


CLEANSERS = {"limpiador", "aceite limpiador", "desmaquillante"}


def facts(name, text):
    """Hechos que el texto de las tiendas (ya normalizado con `norm`) sostiene: dict con type, benefits, actives, skin, spf."""
    title, text = prepare(name, text)
    a = attributes(name, text)
    spf = re.search(r" spf ?([0-9]{2,3}) ", text)  # "SPF50+" -> " spf50 "; "SPF 50" -> " spf 50 "
    scored = []
    for label, phrases in BENEFITS:
        if label == "proteger la piel del sol":
            if a["kind"] in CLEANSERS:
                continue  # un limpiador menciona el protector solar porque lo QUITA ("remueve maquillaje y protector solar"), no porque proteja
            if not (spf or a["kind"] == "protector solar" or mentions(title, phrases)):
                continue  # sin SPF propio es un consejo ("usa protector solar durante el día", típico con AHA o retinol), no protección
        score = mentions(text, phrases) + 3 * mentions(title, phrases)  # lo que dice el nombre pesa más que una mención suelta
        if score >= 2:
            scored.append((-score, len(scored), label))
    return {"type": a["type"], "benefits": [label for _, _, label in sorted(scored)[:4]], "actives": a["actives"], "skin": a["skin"], "spf": spf.group(1) if spf else "",
            "traits": traits(a["kind"], a["group"], title, text)}


def traits(kind, group, title, text):
    """Acabado, duración, pigmentación, cobertura y "vegano"/"no probado en animales", con la regla de siempre: 2 o más menciones, o el nombre
    (que pesa 3). Los acabados solo en maquillaje, protectores solares y productos sin tipo; duración, agua, pigmentación y cobertura solo en
    maquillaje o sin tipo. -> {"finish": [...], "claims": [...], "vegan": bool, "cruelty": bool}"""
    score = lambda phrases: mentions(text, phrases) + 3 * mentions(title, phrases)
    makeup = group not in NONMAKEUP and (group is not None or bool(mentions(text, MAKEUP_CONTEXT)))
    out = {"finish": [], "claims": [], "vegan": False, "cruelty": False}
    if makeup or (kind in FINISH_KINDS):
        found = sorted((-score(p), n, label) for n, (label, p) in enumerate(FINISHES) if score(p) >= 2)
        others = [label for label, p in FINISHES if score(p) == 1] + (["?"] if mentions(text, FINISH_MIX) else [])
        # si la página nombra más acabados de los que sostiene (una paleta "mate, satinada o brillante según el tono"), no se elige uno: solo
        # se afirma lo que el nombre dice. Con 2 o más acabados bien sostenidos se listan todos ("Tiene un acabado mate y aterciopelado")
        if others:
            found = [f for f in found if mentions(title, dict(FINISHES)[f[2]])]
        out["finish"] = [label for _, _, label in found[:2]]
    if makeup:
        for label, phrases in CLAIMS:
            if label == "resistencia al agua" and (kind in CLEANSERS or mentions(text, WATER_NOISE)):
                continue
            if score(phrases) >= 2:
                out["claims"].append(label)
        cov = [label for label, p in COVERAGES if score(p) >= 2]
        if len(cov) == 1:  # dos coberturas distintas con 2 menciones cada una: la tienda habla de tonos o versiones distintas, no se elige
            out["claims"].append(cov[0])
    out["vegan"] = score(VEGAN) >= 2
    out["cruelty"] = score(CRUELTY) >= 2
    return out


def _contents_inline(rest):
    """Formato pegado: "A 20ml B 30ml C 30ml" (Kosmeticos). Los productos se listan uno tras otro, sin texto entre medio."""
    pos, items = 0, []
    while len(items) < 12:
        m = CONTENT_ITEM.match(rest, pos)
        if not m:
            break
        name = m.group(1).strip(" -•*·")
        if len(name.split()) > 10 or re.search(r"[.!?:*]", name):  # ya no es un nombre de producto: terminó la lista
            break
        items.append((name, f"{m.group(2).replace(',', '.')} {'ml' if m.group(3).lower() == 'ml' else 'g'}"))
        pos = m.end()
    return items


def _contents_paren(rest):
    """Formato "Nombre (30 ml) – una frase de marketing. Otro nombre (50 ml) – otra frase." (Vierose y otras).
    A diferencia del pegado, tolera texto libre entre productos: busca cada "Nombre (tamaño)" sin exigir que se sigan."""
    stop = CONTENT_STOP.search(rest)
    window = rest[:stop.start()] if stop else rest[:1200]  # corta antes de "Beneficios:" / etc.; si no hay, una ventana razonable
    items = []
    for name, num, unit in CONTENT_ITEM_PAREN.findall(window)[:12]:
        name = name.strip(" -–—:•*").rstrip(".,;")
        if name and 1 <= len(name.split()) <= 8 and not re.search(r"[.!?]", name):  # no es una frase suelta con un número entre paréntesis
            items.append((name, f"{num.replace(',', '.')} {'ml' if unit.lower() == 'ml' else 'g'}"))
    return items


def contents(raw):
    """Productos que la descripción de un pack enumera tras una frase como "incluye:", "contenido del set:" o "el kit incluye:",
    cada uno con su tamaño. Recibe el texto sin normalizar. -> [(nombre, "30 ml")], o [] si no hay al menos 2 productos con tamaño."""
    for intro in CONTENT_INTRO.finditer(raw):
        rest = raw[intro.end():]
        items = _contents_inline(rest)
        if len(items) < 2:
            items = _contents_paren(rest)
        if len(items) >= 2:
            return items
    return []


def short_names(names):
    """Quita "Mini" y el comienzo que comparten todos los nombres ("Madagascar Centella Tea-Trica ...") para leerlos en una frase."""
    words_ = [[w for w in n.split() if w.lower() not in MINI_WORDS] for n in names]
    k = 0
    while len(words_) > 2 and all(len(w) > k + 1 for w in words_) and len({w[k].lower() for w in words_}) == 1:
        k += 1
    return [" ".join(w[k:]) if k >= 2 else " ".join(w) for w in words_]


def describe(name, brand, size, text, is_pack=False, items=(), small=False):
    """-> {"text": párrafo, "skin": [...]} o None si las tiendas no dan ningún dato para escribirla."""
    f = facts(name, text)
    if is_pack:
        f["type"] = ("set de productos", "un")
    # en un pack el texto junta a varios productos (y a veces esponjas o accesorios): un acabado o "vegano" no se sabe de cuál es
    t = {"finish": [], "claims": [], "vegan": False, "cruelty": False} if is_pack else f["traits"]
    if not (f["benefits"] or f["actives"] or f["skin"] or f["spf"] or items or t["finish"] or t["claims"] or t["vegan"] or t["cruelty"]):
        return None
    sentences = []
    goal = ""
    if f["benefits"]:
        ready = {"un": "pensado", "una": "pensada", "unos": "pensados"}[f["type"][1]] if f["type"] else "pensado"
        goal = f"{ready} para {join_benefits(f['benefits'])}"
    if f["type"]:
        label, art = f["type"]
        head = f"{art.capitalize()} {label}" + (f" de {brand}" if brand else "") + (f" de {size}" if size and not is_pack else "")
        sentences.append(f"{head}, {goal}." if goal else f"{head}.")
    elif goal:
        sentences.append(f"{goal[0].upper()}{goal[1:]}.")
    if f["actives"]:
        intros = INTROS_ONE if len(f["actives"]) == 1 else INTROS
        sentences.append(f"{intros[len(name) % len(intros)]} {join(f['actives'])}.")
    if t["finish"]:
        sentences.append(f"Tiene un acabado {join(t['finish'])}.")  # "Tiene un acabado mate", "...con destellos", "...aterciopelado y mate"
    mentioned = t["claims"] + (["fórmula vegana"] if t["vegan"] else []) + (["producción sin pruebas en animales (cruelty free)"] if t["cruelty"] else [])
    if mentioned:
        sentences.append(f"Las tiendas mencionan {join(mentioned)}.")
    if f["spf"]:
        sentences.append(f"Factor de protección solar SPF {f['spf']}.")
    if items:
        listed = [f"{short} ({size_})" for short, (_, size_) in zip(short_names([n for n, _ in items]), items)]
        sentences.append(f"Incluye {len(items)} productos{' en formato mini' if small else ''}: {join(listed)}.")
    return {"text": " ".join(sentences), "skin": f["skin"]}
