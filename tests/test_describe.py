import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

import re

from describe import attributes, contents, describe, facts, norm, short_names

QUECOREANA = ("El Pine Calming Cica Trial Kit de ROUND LAB contiene los 4 pasos esenciales de su línea calmante a base de extracto de pino rojo coreano "
              "y centella asiática. Diseñado especialmente para pieles sensibles o reactivas, este kit proporciona una rutina completa en tamaño mini para "
              "hidratar, calmar rojeces y fortalecer la piel. Las fórmulas suaves están libres de ingredientes agresivos.")
BOJ = ("A lightweight sunscreen with rice and probiotics for all skin types. Niacinamide and rice bran water brighten dull skin. "
       "No white cast. Non-oily finish, SPF50+ PA++++.")


def build(name, *texts):
    return norm(name + " " + " ".join(texts))


def test_facts_from_spanish_text():
    f = facts("Pine Calming Cica Cream", build("Pine Calming Cica Cream", QUECOREANA))
    assert f["type"][0] == "crema" and "centella asiática" in f["actives"] and "extracto de pino" in f["actives"]
    assert "calmar la piel" in f["benefits"] and f["skin"] == ["Piel sensible"]


def test_facts_from_english_text_with_spf_and_negation():
    f = facts("Relief Sun Rice + Probiotics", build("Relief Sun Rice + Probiotics", BOJ))
    assert f["type"][0] == "protector solar" and f["spf"] == "50"
    assert "niacinamida" in f["actives"] and "arroz" in f["actives"] and f["skin"] == ["Todo tipo de piel"]
    assert "Piel grasa" not in f["skin"]  # "non-oily" no significa piel grasa


def test_negated_active_is_not_listed():
    f = facts("Calming Toner", build("Calming Toner", "Toner suave sin retinol y libre de zinc, con pantenol."))
    assert "retinol" not in f["actives"] and "zinc" not in f["actives"] and "pantenol (vitamina B5)" in f["actives"]


def test_written_text_is_not_a_copy_of_the_source():
    d = describe("Pine Calming Cica Cream", "Round Lab", "50 ml", build("Pine Calming Cica Cream", QUECOREANA))
    assert d and d["text"].startswith("Una crema de Round Lab de 50 ml")
    src, out = QUECOREANA.lower().split(), d["text"].lower().split()
    grams = lambda w: {" ".join(w[i:i + 4]) for i in range(len(w) - 3)}
    assert not grams(src) & grams(out), grams(src) & grams(out)  # ninguna secuencia de 4 palabras seguidas coincide con la tienda


def test_grammar_agreement_and_missing_brand():
    txt = build("Spot Cover Patch", "Parches que ayudan con el acné y las imperfecciones. Con acné.")
    assert describe("Spot Cover Patch", "SKIN1004", "", txt)["text"].startswith("Unos parches de SKIN1004, pensados para")
    amp = describe("Relief Ampoule", "SKIN1004", "30 ml", build("Relief Ampoule", "Ampolla calmante y calmante para irritación, con centella."))
    assert amp["text"].startswith("Una ampolla de SKIN1004 de 30 ml, pensada para calmar la piel")
    assert "destaca centella asiática." in amp["text"] or "incluye centella asiática." in amp["text"] or "Contiene centella asiática." in amp["text"]  # un solo compuesto: singular
    no_brand = describe("Facial Cream", "", "", build("Facial Cream", "Crema hidratante que hidrata."))
    assert no_brand["text"].startswith("Una crema, pensada para hidratar") and " de ," not in no_brand["text"]
    assert facts("Vitamin E Bloqueador Solar", build("Vitamin E Bloqueador Solar", "x"))["type"][0] == "protector solar"


def test_free_of_something_does_not_cancel_what_follows():
    a = attributes("Oil-Free Calming Gel Moisturizer", norm("Oil-Free Calming Gel Moisturizer. Fragrance-free, con niacinamida y ácido hialurónico para piel seca."))
    assert a["kind"] == "crema" and a["group"] == "facial"  # "Oil-Free" no niega "moisturizer"
    assert "niacinamida" in a["actives"] and "Piel seca" in a["skin"]  # "Fragrance-free" tampoco niega lo que sigue
    b = attributes("Serum", norm("Sérum libre de zinc, sin retinol."))
    assert "zinc" not in b["actives"] and "retinol" not in b["actives"]  # pero "libre de X" y "sin X" sí niegan X


def test_categories_by_product_name():
    cases = {"Bean Sunstick SPF50+": ("protector solar", "facial"), "Waterism Glow Tint 29 Eveny": ("producto para labios", "maquillaje"),
             "Stay Blushin Cute Dare Me": ("rubor o iluminador", "maquillaje"), "Keratin Hair Treatment": ("producto para el cabello", "cabello"),
             "Peach Hand Cream": ("producto para cuerpo o manos", "cuerpo"), "Pep!Balm bálsamo multiuso": ("bálsamo", "facial"),
             "Ginseng Cleansing Oil": ("aceite limpiador", "facial"), "Handheld Mirror Coquette": ("accesorio", "accesorios"),
             "Compacto Oil Capture Setting Pact": ("base o cushion", "maquillaje")}
    for name, (kind, group) in cases.items():
        a = attributes(name, norm(name))
        assert (a["kind"], a["group"]) == (kind, group), (name, a["kind"], a["group"])
    assert attributes("Cosa rara sin tipo", norm("x"))["group"] is None  # lo que no se reconoce no se inventa


KOSMETICOS = ("Descripción extracto de Arbol de te que ayuda a balancear. Paso 3: Madagascar Centella Tea-Trica Relief Ampoule: Una ampolla concentrada. "
              "El set incluye: Madagascar Centella Tea-trica BHA Foam Mini 20ml Madagascar Centella Tea-Trica Purifying Toner Mini 30ml "
              "Madagascar Centella Tea-Trica Relief Ampoule Mini 30ml Madagascar Centella Tea-Trica B5 Cream Mini 30ml *Beneficios: Set de viaje 4 productos")


def test_contents_lists_each_product_with_its_size():
    items = contents(KOSMETICOS)
    assert items == [("Madagascar Centella Tea-trica BHA Foam Mini", "20 ml"), ("Madagascar Centella Tea-Trica Purifying Toner Mini", "30 ml"),
                     ("Madagascar Centella Tea-Trica Relief Ampoule Mini", "30 ml"), ("Madagascar Centella Tea-Trica B5 Cream Mini", "30 ml")]
    assert contents("El kit incluye: Pine Cleanser 30ml Pine Toner 20ml Pine Ampoule 10ml.") == [("Pine Cleanser", "30 ml"), ("Pine Toner", "20 ml"), ("Pine Ampoule", "10 ml")]
    assert contents("Includes: Glow Serum 30ml, Ginseng Water 150ml") == [("Glow Serum", "30 ml"), ("Ginseng Water", "150 ml")]
    assert contents("Este set incluye 4 pasos para tu rutina de 50ml diaria.") == []  # sin lista de productos con tamaño: no se inventa
    assert contents("Incluye: Un solo producto 30ml") == []  # una lista necesita al menos 2 productos


VIEROSE = ("Consigue la piel de cristal que siempre soñaste. Contenido del set: Bean Essence (50 ml) – esencia hidratante que suaviza la piel "
           "y regula el sebo. Bean Cream (50 ml) – crema que sella la hidratación, fortalece la barrera cutánea y aporta elasticidad. "
           "Beneficios: Efecto Glass Skin: logra un acabado translúcido.")


def test_contents_understands_a_sentence_per_product_not_just_a_bare_list():
    # caso real reportado por el usuario: Vierose describe cada producto con una frase de marketing entre medio,
    # no como una lista pegada; antes esto hacía que contents() devolviera vacío y el producto no se enlazara
    assert contents(VIEROSE) == [("Bean Essence", "50 ml"), ("Bean Cream", "50 ml")]
    assert contents("El kit incluye: Toner (150 ml) – hidrata. Cream (50 ml) – nutre. Modo de uso: aplicar de noche.") == \
        [("Toner", "150 ml"), ("Cream", "50 ml")]
    # el nombre nunca se traga el punto de la frase anterior (ese era el bug): sin la protección, "Cream" habría
    # salido como " nutre la piel. Cream" en vez de "Cream"
    assert all(not re.search(r"[.!?]", n) for n, _ in contents(VIEROSE))
    # sin una frase de intro real (kit/set/pack/incluye/contiene), un paréntesis con tamaño no cuenta como lista
    assert contents("Precio regular (30 ml) más IVA. No incluye envío.") == []


def test_pack_description_lists_items_and_sizes_in_our_own_words():
    items = contents(KOSMETICOS)
    assert short_names([n for n, _ in items]) == ["BHA Foam", "Purifying Toner", "Relief Ampoule", "B5 Cream"]
    d = describe("Tea-Trica Travel Kit", "SKIN1004", "", norm(KOSMETICOS), is_pack=True, items=items, small=True)
    assert "Incluye 4 productos en formato mini: BHA Foam (20 ml), Purifying Toner (30 ml), Relief Ampoule (30 ml) y B5 Cream (30 ml)." in d["text"]


def test_benefits_are_never_a_dangling_verb_like_calmar_alone():
    # caso real reportado por el usuario: "pensada para calmar" no decía calmar qué
    f = facts("Ampoule Mask", build("Ampoule Mask", "Mascarilla que calma la piel irritada. Fórmula calmante."))
    assert f["benefits"] == ["calmar la piel"]


def test_join_benefits_merges_shared_object_instead_of_repeating():
    from describe import join_benefits
    assert join_benefits(["hidratar la piel", "calmar la piel", "limpiar la piel"]) == "hidratar, calmar y limpiar la piel"
    assert join_benefits(["dar luminosidad a la piel", "aportar firmeza a la piel"]) == "dar luminosidad y aportar firmeza a la piel"
    assert join_benefits(["calmar la piel"]) == "calmar la piel"  # un solo beneficio: nada que fusionar
    assert join_benefits(["cuidar los poros", "calmar la piel"]) == "cuidar los poros y calmar la piel"  # objetos distintos: no se fusiona
    # caso real que rompía: "hidratar, dar luminosidad a, limpiar y calmar la piel" (preposición colgando)
    mixed = join_benefits(["hidratar la piel", "dar luminosidad a la piel", "limpiar la piel", "calmar la piel"])
    assert ", a," not in mixed and " a," not in mixed  # no debe quedar una preposición colgando
    assert mixed == "hidratar la piel, dar luminosidad a la piel, limpiar la piel y calmar la piel"


def test_sun_protection_only_when_it_really_protects():
    sun = "proteger la piel del sol"
    # casos reales: "uva" (la fruta) y un limpiador que QUITA el protector solar no son protección solar
    lip = facts("Grape Honey Chu Lip Essence", build("Grape Honey Chu Lip Essence", "Bálsamo con extracto de uva. La uva aporta vitalidad."))
    assert sun not in lip["benefits"]
    oil = facts("Collagen Cleansing Oil", build("Collagen Cleansing Oil", "Remueve maquillaje y protector solar. Limpia incluso el protector solar resistente al agua."))
    assert sun not in oil["benefits"]
    advice = facts("Péptidos Serum", build("Péptidos Serum", "Sérum reafirmante. Usa protector solar durante el día. Siempre aplica protector solar."))
    assert sun not in advice["benefits"]  # el consejo de usar protector no convierte al sérum en protector
    real = facts("Relief Sun Rice SPF50+", build("Relief Sun Rice SPF50+", "Protector solar ligero. Protege de los rayos UVA y UVB."))
    assert sun in real["benefits"]  # un protector de verdad lo sigue diciendo
    cushion = facts("Glow Fit Cushion", build("Glow Fit Cushion", "Cushion con protección solar SPF50+. Protector solar y cobertura."))
    assert sun in cushion["benefits"]  # y lo que trae un SPF propio, también


def test_makeup_finish_needs_two_mentions_or_the_name():
    two = describe("Soft Lip Tint", "Peri", "", build("Soft Lip Tint", "Tinte labial con acabado mate. Un look mate para todo el día."))
    assert "Tiene un acabado mate." in two["text"]
    one = describe("Soft Lip Tint", "Peri", "", build("Soft Lip Tint", "Tinte labial con acabado mate."))
    assert one is None  # una sola mención no basta: no se afirma
    named = describe("Matte Lip Tint", "Peri", "", build("Matte Lip Tint", "Tinte labial."))
    assert "Tiene un acabado mate." in named["text"]  # el nombre pesa más que una mención suelta


def test_makeup_traits_respect_negations_and_do_not_pick_between_finishes():
    neg = describe("Soft Lip Tint", "Peri", "", build("Soft Lip Tint", "Tinte labial sin acabado mate. No es mate, tampoco sin destellos."))
    assert neg is None  # "sin acabado mate" y "no es mate" no cuentan como mención
    mixed = facts("Slide Single Shadow", build("Slide Single Shadow", "Sombra de ojos en acabados mate, satinados o brillantes según el tono. Un tono mate y otro mate."))
    assert mixed["traits"]["finish"] == []  # la página nombra varios acabados: no se elige uno
    both = facts("Zero Velvet Tint", build("Zero Velvet Tint", "Tinte labial de acabado mate. Labios con look mate de larga duración y larga duración real."))
    assert both["traits"]["finish"] == ["aterciopelado", "mate"] or both["traits"]["finish"] == ["mate", "aterciopelado"]
    assert "larga duración" in both["traits"]["claims"]


def test_makeup_claims_and_agreement_in_the_text():
    d = describe("Jelly Tattoo Tint", "Berrisom", "", build("Jelly Tattoo Tint", "Tinta labial de larga duración. Fórmula waterproof, de alta pigmentación y alta pigmentación. "
                 "Vegano y cruelty free. Fórmula vegana, libre de crueldad animal. Cobertura completa, cobertura total."))
    assert "Las tiendas mencionan larga duración" not in d["text"]  # larga duración solo una vez: no cuenta
    assert "alta pigmentación" in d["text"] and "cobertura alta" in d["text"] and "resistencia al agua" not in d["text"]  # waterproof una vez: no
    assert d["text"].endswith("Las tiendas mencionan alta pigmentación, cobertura alta, fórmula vegana y producción sin pruebas en animales (cruelty free)."), d["text"]
    sea = describe("Cleansing Oil", "X", "", build("Cleansing Oil", "Aceite limpiador que remueve maquillaje waterproof. Waterproof makeup remover."))
    assert sea is None or "resistencia al agua" not in sea["text"]  # quitar maquillaje waterproof no es ser resistente al agua
    sérum = facts("Vitamin Serum", build("Vitamin Serum", "Sérum de larga duración, larga duración. Vegano y vegano."))
    assert sérum["traits"]["claims"] == [] and sérum["traits"]["vegan"]  # larga duración es de maquillaje; lo vegano vale para cualquier producto


def test_packs_do_not_claim_makeup_traits():
    d = describe("Duo Set", "X", "", build("Duo Set", "Set mate y mate. Vegano. Vegano."), is_pack=True)
    assert d is None  # el texto de un pack junta varios productos: no se sabe de cuál es el acabado


def test_shade_name_is_not_an_ingredient():
    # caso real: "Honey" es el color, no miel
    name = "Juicy Berry Plumping Oil 11 Glam Max Honey Lemon"
    txt = build(name, "Aceite labial con color que proporciona un brillo radiante. Tono: 11 Glam Max Honey Lemon: amarillo cálido.")
    assert "miel" not in facts(name, txt)["actives"] and "miel" not in attributes(name, txt)["actives"]
    assert describe(name, "Tocobo", "", txt) is None
    tono = facts("Apple Dewy Fit Cushion Tono 23 Honey", build("Apple Dewy Fit Cushion Tono 23 Honey", "Cushion de cobertura ligera."))
    assert "miel" not in tono["actives"]
    # lo que NO es un tono se conserva: concentración de un activo, códigos y efectos del producto
    assert "zinc" in facts("Niacinamide 10 Zinc 1 Serum", build("Niacinamide 10 Zinc 1 Serum", "x"))["actives"]
    assert "colágeno" in facts("Cer-100 Collagen Fixer Spray", build("Cer-100 Collagen Fixer Spray", "x"))["actives"]
    assert "colágeno" in facts("Lip Mask 2 Types Collagen Boosting", build("Lip Mask 2 Types Collagen Boosting", "x"))["actives"]
    assert attributes("Centella Tone Up Cream", norm("Centella Tone Up Cream"))["kind"] == "crema"
    assert "vitamina C" in facts("Limpiador Tono Uniforme Vitamina C", build("Limpiador Tono Uniforme Vitamina C", "x"))["actives"]
    from describe import shade_of
    assert shade_of(norm("Lip Oil Tono 01 Chill Red - Fecha corta 04-07-2027")) == " 01 chill red "
    assert shade_of(norm("Juicy Berry Plumping Oil 11 Glam Max Honey Lemon")) == " glam max honey lemon "


def test_nothing_to_say_returns_none_and_pack_is_a_set():
    assert describe("Cosa", "Marca", "", build("Cosa", "Texto sin datos útiles.")) is None
    d = describe("Glow Duo", "BoJ", "", build("Glow Duo", "Includes niacinamide serum. Hydrating and brightening. Hydrating glow."), is_pack=True)
    assert d["text"].startswith("Un set de productos de BoJ")


if __name__ == "__main__":
    test_facts_from_spanish_text()
    test_facts_from_english_text_with_spf_and_negation()
    test_negated_active_is_not_listed()
    test_written_text_is_not_a_copy_of_the_source()
    test_contents_lists_each_product_with_its_size()
    test_contents_understands_a_sentence_per_product_not_just_a_bare_list()
    test_pack_description_lists_items_and_sizes_in_our_own_words()
    test_free_of_something_does_not_cancel_what_follows()
    test_categories_by_product_name()
    test_grammar_agreement_and_missing_brand()
    test_benefits_are_never_a_dangling_verb_like_calmar_alone()
    test_join_benefits_merges_shared_object_instead_of_repeating()
    test_sun_protection_only_when_it_really_protects()
    test_makeup_finish_needs_two_mentions_or_the_name()
    test_makeup_traits_respect_negations_and_do_not_pick_between_finishes()
    test_makeup_claims_and_agreement_in_the_text()
    test_packs_do_not_claim_makeup_traits()
    test_shade_name_is_not_an_ingredient()
    test_nothing_to_say_returns_none_and_pack_is_a_set()
    print("ok")
