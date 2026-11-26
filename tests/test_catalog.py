import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz

from catalog import Catalog, clean, clp_estimate
from match import clp
from db import connect, save


def item(i, title, price, vendor="Cosrx", available=1, **kw):
    return dict(ext_id=str(i), sku=None, title=title, variant=None, vendor=vendor, url=f"https://x/{i}",
                price=price, compare_at=None, available=available, **kw)


def build():
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "COSRX Advanced Snail 96 Mucin Power Essence 100ml", 28900, image="https://img/1.jpg"),
                      item(2, "Low pH Good Morning Gel Cleanser 150ml", 15000)])
    save(db, "b.cl", [item(3, "Cosrx Advanced Snail 96 Mucin Power Essence 100ml", 27000, rating=4.6, reviews=30)])
    save(db, "c.cl", [item(4, "Advanced Snail 96 Mucin Power Essence 100ml", 25000, available=0)])
    return Catalog(db)


def test_grouping_and_display():
    cat = build()
    assert len(cat.products) == 2
    p = next(p for p in cat.products if "Snail" in p.name)
    assert (p.brand, p.name, p.size) == ("Cosrx", "Advanced Snail 96 Mucin Power Essence", "100 ml")
    assert [(o.store, o.price) for o in p.offers] == [("b.cl", 27000), ("a.cl", 28900), ("c.cl", 25000)]  # sin stock al final
    assert p.min_price == 27000 and p.image == "https://img/1.jpg" and p.offers[0].rating == 4.6


def test_search_and_filters():
    cat = build()
    assert cat.search("snail cosrx")[1] == 1 and cat.search("gel")[1] == 1 and cat.search("nada")[1] == 0
    assert cat.search(multi=True)[1] == 1  # solo el Snail está en 2+ tiendas
    assert cat.search(stores=["b.cl"])[1] == 1
    assert cat.search(pmax=20000)[1] == 1
    assert [p.min_price for p in cat.search(sort="precio_asc")[0]] == [15000, 27000]


def test_card_rating_uses_store_with_most_reviews():
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Anua Toner 250ml", 20000, vendor="Anua", rating=5.0, reviews=2)])
    save(db, "b.cl", [item(2, "Anua Toner 250ml", 21000, vendor="Anua", rating=4.6, reviews=80)])
    save(db, "c.cl", [item(3, "Anua Toner 250ml", 22000, vendor="Anua")])
    p = Catalog(db).products[0]
    assert (p.rating.store, p.rating.rating) == ("b.cl", 4.6)
    assert next(p for p in build().products if "Gel" in p.name).rating is None  # sin nota en ninguna tienda: la card no muestra nada


def test_card_rating_needs_min_reviews():
    def rating_with(reviews):
        db = connect(":memory:")
        save(db, "a.cl", [item(1, "Anua Toner 250ml", 20000, vendor="Anua", rating=5.0, reviews=reviews)])
        return Catalog(db).products[0].rating

    assert rating_with(4) is None  # 4 reseñas: no se muestra
    assert rating_with(5).reviews == 5  # 5: sí


def test_foreign_offers_stay_apart():
    db = connect(":memory:")
    db.execute("INSERT INTO fx VALUES('2026-09-21', 958.42)")
    save(db, "a.cl", [item(1, "Anua Toner 250ml", 20000, vendor="Anua")])
    save(db, "yes.com", [item(2, "anua toner 250ml", 1732, vendor="Anua", currency="USD")])
    cat = Catalog(db)
    p = cat.products[0]
    assert len(cat.products) == 1 and p.min_price == 20000 and len(p.offers) == 1  # el dólar no entra al mejor precio
    assert [(o.store, o.cents) for o in p.intl] == [("yes.com", 1732)] and set(cat.stores) == {"a.cl"}
    assert clp_estimate(1732, cat.usd_clp) == 19754  # 17,32 USD x 958,42 x 1,19
    solo_afuera = connect(":memory:")  # sin fila en `fx`: no hay dólar del día
    save(solo_afuera, "yes.com", [item(3, "solo afuera 30ml", 999, vendor="Otra", currency="USD")])
    cat_afuera = Catalog(solo_afuera)
    assert len(cat_afuera.products) == 1  # entra igual al catálogo, aunque ninguna tienda chilena lo venda
    only = cat_afuera.products[0]
    assert not only.domestic and only.offers == [] and len(only.intl) == 1
    assert only.display_price is None  # sin dólar del día no se puede estimar (caso raro): mejor no mostrar un precio inventado que uno falso


def test_intl_only_product_is_findable_and_priced_with_an_estimate():
    db = connect(":memory:")
    db.execute("INSERT INTO fx VALUES('2026-09-21', 958.42)")
    save(db, "cosrx.com", [item(1, "COSRX Snail Essence 100ml", 2500, vendor="Cosrx", currency="USD")])
    cat = Catalog(db)
    assert len(cat.products) == 1  # antes se descartaba por completo: ahora aparece
    p = cat.products[0]
    assert not p.domestic and p.min_price is None and p.offers == []
    assert p.display_is_estimate and p.display_price == clp_estimate(2500, cat.usd_clp)
    assert p.best_intl.store == "cosrx.com"
    # se puede buscar y filtrar como cualquier otro producto
    assert cat.search("snail")[1] == 1
    assert cat.search(stock=True)[1] == 1  # "con stock" también cuenta el stock internacional
    assert cat.search(pmin=p.display_price - 1, pmax=p.display_price + 1)[1] == 1
    assert cat.search(pmax=p.display_price - 1000)[1] == 0
    # el id no depende de tener o no precio chileno: si mañana una tienda de Chile lo suma, sigue siendo el mismo producto
    db.execute("INSERT INTO fx VALUES('2026-09-22', 960)")
    save(db, "a.cl", [item(2, "COSRX Snail Essence 100ml", 20000, vendor="Cosrx")])
    p2 = Catalog(db).by_id[p.id]
    assert p2.domestic and p2.min_price == 20000 and p2.best_intl.store == "cosrx.com"


def test_packs_stay_out_of_single_comparison_and_link_to_their_products():
    db = connect(":memory:")
    save(db, "a.cl", [
        item(1, "Glow Serum Propolis Niacinamide 30ml", 20000, vendor="Beauty of Joseon"),
        item(2, "Ginseng Essence Water 150ml", 18000, vendor="Beauty of Joseon"),
        item(3, "Glow Boosting Duo", 35000, vendor="Beauty of Joseon",
             description="A duo of serums. Includes our Glow Serum: Propolis + Niacinamide and Ginseng Essence Water. Save more."),
        item(4, "Glow Serum Propolis Niacinamide 30ml 2-Pack", 38000, vendor="Beauty of Joseon"),
        item(5, "Kit misterioso", 9000, vendor="Beauty of Joseon", description="Un kit muy lindo."),
    ])
    cat = Catalog(db)
    singles, n_singles = cat.search()
    assert n_singles == 2 and not any(p.is_pack for p in singles)  # los packs no aparecen en el catálogo de productos
    packs, n_packs = cat.search(packs=True)
    assert n_packs == 3 and all(p.is_pack for p in packs)
    glow = next(p for p in singles if "Glow Serum" in p.name)
    essence = next(p for p in singles if "Ginseng" in p.name)
    by_name = {p.name: p for p in packs}
    duo = by_name["Glow Boosting Duo"]
    assert {i for i, _ in duo.includes} == {glow.id, essence.id}  # el set nombra a sus dos productos en la descripción
    twin = next(p for p in packs if "2" in p.name)
    assert twin.includes == [(glow.id, 2)]  # el mismo producto x2: enlace exacto con cantidad
    assert {i for i, _ in glow.included_in} == {duo.id, twin.id} and [i for i, _ in essence.included_in] == [duo.id]
    assert by_name["Kit misterioso"].includes == []  # la descripción no nombra productos: no se inventa el enlace
    assert glow.min_price == 20000 and len(glow.offers) == 1  # el pack no entra en la comparación del producto


def test_pack_does_not_guess_between_sizes_or_shades():
    db = connect(":memory:")
    save(db, "a.cl", [
        item(1, "Glowing Color Lip Balm 01 Coral", 8000, vendor="Nolahour"),  # dos tonos con el mismo nombre base
        item(2, "Glowing Color Lip Balm 02 Berry", 8000, vendor="Nolahour"),
        item(3, "Hydra Serum Calming 50ml", 15000, vendor="Nolahour"),
        item(4, "Hydra Serum Calming Mini 10ml", 5000, vendor="Nolahour"),
        item(5, "Trio de prueba", 20000, vendor="Nolahour", description="Incluye Glowing Color Lip Balm y Hydra Serum Calming."),
        item(6, "Travel Kit", 9000, vendor="Nolahour", description="Incluye Hydra Serum Calming en formato viaje."),
    ])
    cat = Catalog(db)
    by = {p.name: p for p in cat.products if p.is_pack}
    names = lambda pack: sorted(cat.by_id[i].name for i, _ in pack.includes)
    assert names(by["Trio de prueba"]) == ["Hydra Serum Calming"]  # el lip balm existe en 2 tonos: ambiguo, no se enlaza
    assert names(by["Travel Kit"]) == ["Hydra Serum Calming Mini"]  # el pack de viaje contiene la miniatura, no el tamaño normal


def test_trial_kit_shows_the_smaller_size_inside_the_pack():
    from server import pack_note

    db = connect(":memory:")
    save(db, "a.cl", [
        item(1, "Pine Calming Cica Cleanser 150ml", 18000, vendor="Round Lab"),
        item(2, "Pine Calming Cica Toner 250ml", 24000, vendor="Round Lab"),
        item(3, "Pine Calming Cica Ampoule 30ml", 24000, vendor="Round Lab"),
        item(4, "Pine Calming Cica Trial Kit", 19980, vendor="Round Lab",
             description="Rutina en tamaño mini. El kit incluye: Pine Calming Cica Cleanser 30ml Pine Calming Cica Toner 20 ml Pine Calming Cica Ampoule 30ml."),
    ])
    cat = Catalog(db)
    kit = next(p for p in cat.products if p.is_pack)
    by = {cat.by_id[i].name: cat.by_id[i] for i, _ in kit.includes}
    assert kit.small_format and set(by) == {"Pine Calming Cica Cleanser", "Pine Calming Cica Toner", "Pine Calming Cica Ampoule"}
    assert kit.pack_sizes[by["Pine Calming Cica Cleanser"].id] == "30 ml"  # el kit trae 30 ml, el suelto es de 150
    assert kit.pack_sizes[by["Pine Calming Cica Toner"].id] == "20 ml"  # "20 ml" con espacio también se entiende
    assert pack_note(kit, by["Pine Calming Cica Cleanser"]) == "En el pack: 30 ml · suelto: 150 ml"
    assert pack_note(kit, by["Pine Calming Cica Ampoule"]) == "En el pack: 30 ml (igual al suelto)"


def test_small_format_without_sizes_is_still_flagged():
    from server import pack_note

    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Calming Toner Deluxe 200ml", 20000, vendor="Anua"),
                      item(2, "Calming Toner Deluxe Trial Kit", 9000, vendor="Anua", description="Incluye Calming Toner Deluxe.")])
    cat = Catalog(db)
    kit = next(p for p in cat.products if p.is_pack)
    single = next(p for p in cat.products if not p.is_pack)
    assert kit.small_format and pack_note(kit, single) == "En el pack viene en formato mini (tamaño no informado)"


def test_gallery_takes_up_to_four_distinct_images_from_the_best_store_first():
    import json

    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Anua Toner 250ml", 20000, vendor="Anua", image="a1",
                           images=json.dumps(["a1", "a2", "a3", "a4", "a5"]))])
    save(db, "b.cl", [item(2, "Anua Toner 250ml", 21000, vendor="Anua", image="b1", images=json.dumps(["b1", "a2"]))])
    p = Catalog(db).products[0]
    assert p.images == ["a1", "a2", "a3", "a4"] and p.image == "a1"  # tope de 4, de la tienda más barata primero, sin repetir
    db2 = connect(":memory:")
    save(db2, "a.cl", [item(1, "Anua Toner 250ml", 20000, vendor="Anua", image="a1", images=json.dumps(["a1"]))])
    save(db2, "b.cl", [item(2, "Anua Toner 250ml", 21000, vendor="Anua", image="b1", images=json.dumps(["b1", "b2", "b3"]))])
    assert Catalog(db2).products[0].images == ["a1", "b1", "b2", "b3"]  # si la mejor tienda trae pocas, se completa con las otras


def test_categories_filters_and_bilingual_search():
    cat = categories_catalog()
    by = {p.name: p for p in cat.products}
    assert (by["Relief Sun Rice Probiotics"].kind, by["Relief Sun Rice Probiotics"].group) == ("protector solar", "facial")
    assert by["Juicy Lasting Tint"].group == "maquillaje" and by["Relief Sun Rice Probiotics"].skin == ["Piel sensible"]
    assert cat.search(group="maquillaje")[1] == 1 and cat.search(group="facial")[1] == 3
    assert cat.search(kinds=["sérum"])[1] == 1 and cat.search(skins=["Piel seca"])[1] == 1 and cat.search(actives=["propóleo"])[1] == 1
    assert cat.search(q="sunscreen")[1] == 1  # buscar en inglés encuentra "Relief Sun" (protector solar)
    assert cat.search(q="niacinamida")[1] == 1 and cat.search(q="piel sensible")[1] == 1  # busca también por compuesto y tipo de piel


def test_explorer_hides_out_of_stock_by_default_and_shows_filters():
    import server
    cat = categories_catalog()
    server.get_catalog = lambda: cat
    _, html = server.explore(cat, {})
    assert "Agotado Cream" not in html  # sin stock en todas las tiendas: oculto por defecto
    for name in ("tipo", "piel", "ing", "sinstock"):
        assert f'name="{name}"' in html
    assert 'href="/explorar?cat=maquillaje' in html and "Incluir productos sin stock" in html
    _, html = server.explore(cat, {"sinstock": ["1"]})
    assert "Agotado Cream" in html and "checked" in html.split("Incluir productos sin stock")[0][-80:]
    _, html = server.explore(cat, {"cat": ["maquillaje"]})
    assert "Juicy Lasting Tint" in html and "Relief Sun" not in html


def test_facet_counts_match_the_list_shown():
    cat = categories_catalog()
    for stock in (True, False):
        f = cat.facets(stock)
        for slug, n in f["groups"].items():
            assert n == cat.search(group=slug, stock=stock)[1], (stock, slug)  # el número del chip = los productos de la lista
        assert sum(f["skin"].values()) == sum(len(p.skin) for p in f["singles"])
    assert cat.facets(True)["groups"]["facial"] == 2 and cat.facets(False)["groups"]["facial"] == 3  # el agotado solo cuenta si se incluye
    assert cat.facets(True, "maquillaje")["skin"] == {} and cat.facets(True, "facial")["skin"]["Piel sensible"] == 1  # piel/ingredientes: dentro de la categoría


def test_pack_contents_link_minis_to_loose_products_and_keep_unlisted_ones():
    from server import pack_note

    db = connect(":memory:")
    save(db, "a.cl", [
        item(1, "Madagascar Centella Tea-Trica Purifying Toner 210ml", 25990, vendor="SKIN1004"),
        item(2, "Madagascar Centella Tea-Trica Relief Ampoule 50ml", 22000, vendor="SKIN1004"),
        item(3, "Madagascar Centella Tea-Trica Travel Kit", 24980, vendor="SKIN1004",
             description="Set de viaje. El set incluye: Madagascar Centella Tea-trica BHA Foam Mini 20ml Madagascar Centella Tea-Trica Purifying Toner Mini 30ml "
                         "Madagascar Centella Tea-Trica Relief Ampoule Mini 30ml *Beneficios: Set de viaje 4 productos"),
    ])
    cat = Catalog(db)
    kit = next(p for p in cat.products if p.is_pack)
    assert [(n, s, bool(i)) for n, s, i in kit.content_rows] == [
        ("Madagascar Centella Tea-trica BHA Foam Mini", "20 ml", False),  # no está suelto en el catálogo: igual se muestra
        ("Madagascar Centella Tea-Trica Purifying Toner Mini", "30 ml", True), ("Madagascar Centella Tea-Trica Relief Ampoule Mini", "30 ml", True)]
    toner = next(p for p in cat.products if p.name.endswith("Purifying Toner"))
    assert kit.pack_sizes[toner.id] == "30 ml" and pack_note(kit, toner) == "En el pack: 30 ml · suelto: 210 ml"  # ya no dice "tamaño no informado"


def test_pack_contents_render_as_clickable_image_cards():
    import server

    db = connect(":memory:")
    save(db, "a.cl", [
        item(1, "Purifying Toner 210ml", 25990, vendor="SKIN1004", image="https://img/toner.jpg"),
        item(2, "Travel Kit", 24980, vendor="SKIN1004",
             description="El set incluye: Purifying Foam Mini 20ml Purifying Toner Mini 30ml Relief Ampoule Mini 30ml"),
    ])
    cat = Catalog(db)
    kit = next(p for p in cat.products if p.is_pack)
    linked = cat.by_id[next(i for _, _, i in kit.content_rows if i)]
    _, html = server.product(cat, kit.id)
    section = html.split("Este pack incluye")[1].split("Historial")[0]
    # el producto enlazado: toda la tarjeta (imagen + texto) es un solo <a>, no un link de texto suelto
    assert f'<a class="card-link" href="/p/{linked.id}">' in section
    assert "Ver el producto suelto" not in section and 'class="link"' not in section
    # el que no está en el catálogo: misma tarjeta cuadrada, sin imagen y sin enlace
    assert '<div class="card-img done"><span class="no-img">Sin imagen</span></div>' in section
    assert "No lo tenemos suelto en el catálogo" in section


def test_tied_price_does_not_pick_a_favorite_store():
    import server

    # caso real reportado por el usuario: Kosmeticos y Vierose al mismo precio, Rakuen más caro (hoy con Moonbow: Kosmeticos se retiró)
    db = connect(":memory:")
    save(db, "moonbow.cl", [item(1, "Producto X 50ml", 24980, vendor="Marca")])
    save(db, "vierosecosmetics.cl", [item(2, "Producto X 50ml", 24980, vendor="Marca")])
    save(db, "rakuencosmeticacoreana.cl", [item(3, "Producto X 50ml", 29900, vendor="Marca")])
    cat = Catalog(db)
    p = cat.products[0]
    _, html = server.product(cat, p.id)
    assert "Mismo precio en 2 tiendas" in html and "Mejor precio en" not in html
    # un botón "Ver en X" por cada tienda empatada, en orden alfabético (no el orden en que se leyeron)
    assert html.index("Ver en Moonbow") < html.index("Ver en Vierose")
    assert html.count("Ver en Moonbow") + html.count("Ver en Vierose") == 2  # solo 1 botón por tienda, sin duplicar
    # en la lista de abajo, las DOS tiendas empatadas llevan la etiqueta, no solo la primera
    top = html.split("Precios por tienda")[1].split("Historial")[0]
    assert top.count("Mejor precio</span>") == 2

    # sin empate: sigue funcionando como antes (una sola tienda recomendada)
    db2 = connect(":memory:")
    save(db2, "moonbow.cl", [item(1, "Producto Y 50ml", 19900, vendor="Marca")])
    save(db2, "vierosecosmetics.cl", [item(2, "Producto Y 50ml", 24980, vendor="Marca")])
    cat2 = Catalog(db2)
    _, html2 = server.product(cat2, cat2.products[0].id)
    assert "Mejor precio en <strong>Moonbow</strong>" in html2 and "Mismo precio" not in html2
    assert html2.count('class="btn btn-primary btn-lg"') == 1  # un solo botón principal


def test_tie_breaks_dynamically_when_a_store_raises_its_price():
    """Nada queda fijo: si mañana una tienda sube de precio, el empate se rompe solo en la próxima lectura,
    sin tocar código ni datos aparte de correr scrape.py de nuevo (aquí, un segundo save() con el precio nuevo)."""
    import server

    db = connect(":memory:")
    save(db, "moonbow.cl", [item(1, "Producto Z 50ml", 24980, vendor="Marca")])
    save(db, "vierosecosmetics.cl", [item(2, "Producto Z 50ml", 24980, vendor="Marca")])
    pid = Catalog(db).products[0].id
    _, before = server.product(Catalog(db), pid)
    assert "Mismo precio en 2 tiendas" in before  # hoy: empatados

    save(db, "vierosecosmetics.cl", [item(2, "Producto Z 50ml", 27990, vendor="Marca")])  # mañana: Vierose sube de precio
    _, after = server.product(Catalog(db), pid)  # mismo id de producto: se sigue reconociendo como el mismo
    assert "Mismo precio" not in after
    assert "Mejor precio en <strong>Moonbow</strong>" in after
    assert after.count('class="btn btn-primary btn-lg"') == 1 and "Ver en Vierose" not in after.split("Precios por tienda")[0]


def test_stores_page_lists_international_separately():
    import server

    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Anua Toner 250ml", 20000, vendor="Anua")])
    save(db, "www.yesstyle.com", [item(2, "anua toner 250ml", 1732, vendor="Anua", currency="USD")])
    cat = Catalog(db)
    _, html = server.stores(cat)
    domestic, intl = html.split("Tiendas internacionales")
    assert 'href="/explorar?tienda=a.cl"' in domestic and "1 productos de belleza asiática con stock" in domestic
    # la internacional no linkea a Explorar (ahí no se puede filtrar por tienda extranjera): va directo al sitio
    assert 'href="https://www.yesstyle.com/" target="_blank"' in intl and "YesStyle" in intl and "Internacional" in intl
    assert '/explorar?tienda=www.yesstyle.com' not in intl
    assert "1 tiendas chilenas y 1 internacionales" in html


def test_intl_only_product_page_renders_without_domestic_sections():
    import server

    db = connect(":memory:")
    db.execute("INSERT INTO fx VALUES('2026-09-21', 958.42)")
    save(db, "cosrx.com", [item(1, "COSRX Snail Essence 100ml", 2500, vendor="Cosrx", currency="USD",
                                image="https://img/1.jpg", description="Serum calmante con mucina de caracol.")])
    cat = Catalog(db)
    p = cat.products[0]
    _, html = server.product(cat, p.id)
    assert "Precios por tienda" not in html and "Historial de precios" not in html  # no hay nada chileno que listar
    assert "Desde el extranjero" in html and "Por ahora ninguna tienda chilena lo vende" in html
    assert f"≈ {clp(p.display_price)}" in html and "Estimado, en" in html and "COSRX oficial" in html
    assert html.count('class="btn btn-primary btn-lg"') == 1  # un solo botón, hacia la tienda internacional
    assert f'data-fav="{p.id}"' in html  # favoritos sigue funcionando igual


def test_intl_only_product_without_fx_shows_no_invented_price():
    import server

    db = connect(":memory:")  # sin fila en `fx`
    save(db, "cosrx.com", [item(1, "COSRX Snail Essence 100ml", 2500, vendor="Cosrx", currency="USD")])
    cat = Catalog(db)
    p = cat.products[0]
    assert p.display_price is None
    _, html = server.product(cat, p.id)  # no debe reventar aunque no haya dólar del día
    assert "Ver precio en la tienda" in html and "≈ $" not in html


def categories_catalog():
    db = connect(":memory:")
    save(db, "a.cl", [
        item(1, "Relief Sun Rice Probiotics 50ml", 20000, vendor="Beauty of Joseon", description="Protector solar para piel sensible con niacinamida."),
        item(2, "Glow Serum Propolis 30ml", 22000, vendor="Beauty of Joseon", description="Sérum para piel seca con propóleo."),
        item(3, "Juicy Lasting Tint 4g", 15000, vendor="Romand"),
        item(4, "Agotado Cream 50ml", 9000, vendor="Anua", available=0),
    ])
    return Catalog(db)


def test_clean():
    assert clean("DR. ALTHEA «345 Relief Cream Mist 60ml»", "Dr. Althea", "60 ml") == "345 Relief Cream Mist"
    assert clean("Vitamin C Serum – Dr. Althea", "Dr. Althea", "") == "Vitamin C Serum"


def test_last_update_does_not_hide_a_store_that_never_reports_success():
    # caso real: YesStyle se bloquea (429) en cada corrida desde su única lectura exitosa, así que nunca escribe
    # "scraped:<tienda>" en meta. Antes esa tienda quedaba afuera del cálculo y su atraso quedaba oculto tras la
    # fecha (más nueva) de las tiendas que sí reportan a diario.
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Producto A", 10000)])
    save(db, "yesstyle.example", [item(2, "Producto B", 20000)])
    db.execute("UPDATE price SET ts='2020-01-01T00:00:00+00:00' WHERE listing_id=2")  # yesstyle: nunca se volvió a confirmar
    db.execute("INSERT INTO meta VALUES('scraped:a.cl', '2026-01-01T00:00:00+00:00')")  # a.cl sí reporta a diario
    db.execute("INSERT INTO meta VALUES('run:done', '2025-12-31T23:00:00+00:00')")  # inicio de la última corrida completa
    db.commit()
    cat = Catalog(db)
    assert "yesstyle.example" in cat.stale  # no desaparece: queda marcada "sin conexión" con su fecha real
    assert cat.stale["yesstyle.example"].startswith("2020-01-01")
    assert cat.last_update == "2026-01-01T00:00:00+00:00"  # y el pie muestra la fecha de las que sí están al día


def test_offline_store_is_flagged_not_hidden_and_never_the_best_price():
    # caso real: el dominio de kbelleza.cl dejó de existir. Su último precio se sigue mostrando, marcado "sin conexión", pero no
    # puede ser el mejor precio ni el "desde $X" (no se puede confirmar y el enlace puede no funcionar)
    import server
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 20000)])
    save(db, "caida.cl", [item(2, "Cosrx Snail Mucin Essence 100ml", 15000),  # la más barata, pero sin conexión
                          item(3, "Cosrx Aloe Sun Cream 50ml", 9000)])  # solo la vende la tienda sin conexión
    db.execute("UPDATE price SET ts='2026-01-01T00:00:00+00:00' WHERE listing_id IN (2, 3)")
    db.execute("INSERT INTO meta VALUES('scraped:a.cl', '2026-01-03T00:00:00+00:00')")
    db.commit()
    assert Catalog(db).stale == {}  # sin una corrida completa que lo respalde (ej. la primera va a medias) no se marca a nadie
    db.execute("INSERT INTO meta VALUES('run:done', '2026-01-02T23:00:00+00:00')")  # terminó una corrida y caida.cl no se pudo leer
    db.commit()
    cat = Catalog(db)
    p = next(p for p in cat.products if "Snail" in p.name)
    assert set(cat.stale) == {"caida.cl"}
    solo = next(p for p in cat.products if "Aloe" in p.name)
    _, html_solo = server.product(cat, solo.id)
    assert "Tienda sin conexión: último precio visto el 1 ene 2026" in html_solo and "Sin stock por ahora" not in html_solo
    assert "sin confirmar" in server.card(solo) and "sin stock" not in server.card(solo)  # la tarjeta tampoco dice "sin stock"
    assert p.min_price == 20000 and [o.store for o in p.in_stock] == ["a.cl"]
    off = next(o for o in p.offers if o.store == "caida.cl")
    assert off.price == 15000 and off.stale.startswith("2026-01-01")  # sigue visible, con el último precio que vimos
    _, html = server.product(cat, p.id)
    assert "Sin conexión" in html and "Último precio visto el 1 ene 2026" in html
    assert "En <strong>a.cl</strong>" in html and "<strong>caida.cl</strong>" not in html  # el precio destacado es el confirmado
    assert "Sin stock" not in html  # el aviso de conexión reemplaza al de stock: no se muestran ambos


def test_listing_the_store_stopped_returning_is_flagged_not_hidden():
    # la tienda sí respondió, pero sin este producto (borrado o despublicado): mismo trato que una tienda sin conexión, con su propio aviso
    import server
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 20000), item(2, "Cosrx Aloe Sun Cream 50ml", 9000)])
    save(db, "b.cl", [item(3, "Cosrx Snail Mucin Essence 100ml", 15000)])  # la más barata, pero b.cl la dejará de listar
    db.execute("UPDATE price SET ts='2026-01-01T00:00:00+00:00'")
    db.execute("UPDATE listing SET last_seen=NULL")  # base de antes de la columna: sin dato no se marca nada
    db.commit()
    assert Catalog(db).missing == {}
    save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 20000)])  # a.cl respondió sin el Aloe
    save(db, "b.cl", [item(4, "Cosrx Centella Toner 200ml", 12000)])  # b.cl respondió sin el Snail
    cat = Catalog(db)
    assert cat.stale == {} and set(cat.missing) == {2, 3}
    p = next(p for p in cat.products if "Snail" in p.name)
    assert p.min_price == 20000 and [o.store for o in p.in_stock] == ["a.cl"]
    off = next(o for o in p.offers if o.store == "b.cl")
    assert off.price == 15000 and off.gone.startswith("2026-01-01") and not off.stale  # sin last_seen: vale su último precio
    _, html = server.product(cat, p.id)
    assert "No aparece en la tienda" in html and "Último precio visto el 1 ene 2026" in html
    assert "En <strong>a.cl</strong>" in html and "Sin conexión" not in html and "Sin stock" not in html
    aloe = next(p for p in cat.products if "Aloe" in p.name)
    _, html = server.product(cat, aloe.id)
    assert "Ya no aparece en la tienda: último precio visto el 1 ene 2026" in html and "Sin stock por ahora" not in html


def test_yesstyle_listing_is_missing_only_after_its_brand_is_read_again():
    # YesStyle y Stylevana (db.BY_BRAND) se leen por marca: que un producto de Anua no venga en una corrida que no leyó Anua no dice nada
    from db import BY_BRAND, RETIRED
    for ys, pre in BY_BRAND.items():
        if ys in RETIRED:  # retirada (Stylevana): no se muestra
            continue
        db = connect(":memory:")
        save(db, ys, [item(1, "Anua Heartleaf Toner 250ml", 2000, vendor="Anua", currency="USD"),
                      item(2, "Anua Peach Niacinamide Serum 30ml", 1800, vendor="Anua", currency="USD"),
                      item(3, "Skin1004 Centella Ampoule 100ml", 1500, vendor="SKIN1004", currency="USD")])
        db.execute("UPDATE listing SET last_seen='2026-01-01T00:00:00+00:00'")
        db.execute("INSERT INTO meta VALUES(?, '2026-01-02T00:00:00+00:00')", (f"{pre}:skin1004",))
        db.commit()
        save(db, ys, [item(3, "Skin1004 Centella Ampoule 100ml", 1500, vendor="SKIN1004", currency="USD")])  # corrida que solo leyó SKIN1004
        assert Catalog(db).missing == {}
        db.execute("INSERT INTO meta VALUES(?, '2026-01-03T00:00:00+00:00')", (f"{pre}:anua",))  # Anua leída, pero la corrida no alcanzó a guardarse
        db.commit()
        assert Catalog(db).missing == {}
        save(db, ys, [item(1, "Anua Heartleaf Toner 250ml", 2000, vendor="Anua", currency="USD")])  # ahora sí se guardó, sin el serum
        cat = Catalog(db)
        assert set(cat.missing) == {2}
        serum = next(p for p in cat.products if "Serum" in p.name)
        assert serum.intl[0].gone.startswith("2026-01-01") and not serum.intl[0].available
        # YesStyle se lee solo en parte (1 página por marca): que no lo volvamos a ver no significa que lo hayan sacado
        import server
        _, html = server.product(cat, serum.id)
        assert "Sin actualizar" in html and "Precio sin actualizar: último precio visto el 1 ene 2026" in html
        assert "No aparece en la tienda" not in html


def test_cut_short_read_does_not_mark_half_the_store_as_gone():
    # riesgo real: jumpseller() guarda lo ya leído si la tienda lo bloquea a mitad de camino; sin esta protección, todo lo que no
    # alcanzó a leer quedaría marcado "No aparece en la tienda"
    from db import short_read
    db = connect(":memory:")
    full = [item(i, f"Cosrx Producto {i} 50ml", 10000 + i) for i in range(10)]  # listings 1..10
    save(db, "a.cl", full)
    db.execute("UPDATE listing SET last_seen='2026-01-01T00:00:00+00:00'")
    db.commit()
    at = short_read(db, "a.cl", 5)  # 5 de 10: lectura cortada
    assert at == "2026-01-01T00:00:00+00:00"
    save(db, "a.cl", full[:5], seen_at=at)
    assert Catalog(db).missing == {}  # no se marca nada por una lectura cortada
    assert short_read(db, "a.cl", 9) is None  # 9 de 10: lectura normal
    save(db, "a.cl", full[:9])
    assert set(Catalog(db).missing) == {10}  # solo el que de verdad dejó de venir
    assert short_read(db, "www.yesstyle.com", 0) is None  # YesStyle se lee por marca: tiene su propia regla


def test_filter_counts_respect_every_other_active_filter():
    # caso real: con la marca COSRX elegida, "Piel grasa" decía 166 y al marcarlo salían 11 (el número ignoraba la marca)
    cat = categories_catalog()
    for brand in ("", "beauty-of-joseon", "romand"):
        for stock in (True, False):
            n = cat.counts(brand=brand, stock=stock)
            for facet, key in (("cat", "group"), ("tipo", "kinds"), ("piel", "skins"), ("ing", "actives"), ("tienda", "stores")):
                for v, c in n[facet].items():
                    assert c == cat.search(brand=brand, stock=stock, **{key: v if key == "group" else [v]})[1], (brand, stock, facet, v)
    assert cat.counts(brand="romand")["piel"] == {}  # el labial de Romand no menciona tipo de piel: ninguna opción, no las de otra marca


def test_clear_link_keeps_the_search_intact():
    # caso real: "Limpiar" volvía con la búsqueda "1+1" convertida en "1 1", y "a&b" cortada en "a"
    import html
    import re
    from urllib.parse import parse_qs, urlparse
    import server
    cat = categories_catalog()
    for q in ("1+1", "a&b #2"):
        _, page = server.explore(cat, {"q": [q]})
        href = html.unescape(re.search(r'href="([^"]*)">Limpiar', page).group(1))
        assert parse_qs(urlparse(href).query)["q"] == [q]


def test_price_history_does_not_repeat_the_same_price():
    # la tabla price guarda una fila también cuando solo cambia el stock: el historial de PRECIO no debe decir "$20.000 → $20.000"
    import tempfile
    from pathlib import Path
    from unittest import mock
    import server
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.db"  # product() lee el historial abriendo la base por su ruta, no sirve una en memoria
        db = connect(path)
        save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 20000)])
        save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 20000, available=0)])  # mismo precio, cambia el stock
        save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 18000)])
        cat = Catalog(db)
        with mock.patch.object(server, "DB", path):
            _, page = server.product(cat, cat.products[0].id)
        db.close()
    assert "$20.000 → $18.000" in page and "$20.000 → $20.000" not in page


def test_search_suggestions_are_product_cards_with_image_and_link_to_explore():
    import server
    cat = build()
    assert [p.name for p in cat.suggest("snail")] == ["Advanced Snail 96 Mucin Power Essence"] and cat.suggest("") == []
    html = server.suggestions(cat, "snail")
    assert 'href="/p/' in html and "https://img/1.jpg" in html and "Cosrx" in html and "desde" in html and "$27.000" in html
    assert 'href="/explorar?q=snail"' in html and "Ver el resultado en Explorar" in html
    html = server.suggestions(cat, "gel")
    assert "Sin imagen" in html  # sin foto: el recuadro se mantiene para que la lista no quede desalineada
    assert "No encontramos productos" in server.suggestions(cat, "<b>nada</b>") and "<b>" not in server.suggestions(cat, "<b>nada</b>")

def test_shades_with_the_same_name_show_their_variant():
    import server
    db = connect(":memory:")
    save(db, "a.cl", [{**item(1, "Peripera Ink Velvet", 9000, vendor="Peripera"), "variant": "001 Good Brick"},
                      {**item(2, "Peripera Ink Velvet", 9000, vendor="Peripera"), "variant": "002 Celeb Deep Rose"},
                      {**item(3, "Peripera Ink Mood Glowy Tint", 9000, vendor="Peripera"), "variant": "Default Title"}])
    cat = Catalog(db)
    names = sorted(server.full_name(p) for p in cat.products)
    assert names == ["Peripera Ink Mood Glowy Tint", "Peripera Ink Velvet 001 Good Brick", "Peripera Ink Velvet 002 Celeb Deep Rose"]
    assert all("Default Title" not in server.card(p) for p in cat.products)  # un nombre único no lleva variante


def test_seo_meta_canonical_structured_data_and_sitemap():
    import json
    import re
    import server
    cat = build()
    server.get_catalog = lambda: cat
    route = lambda path, **qs: server.route(path, {k: [v] for k, v in qs.items()}, base="https://yumori.cl")
    snail = next(p for p in cat.products if "Snail" in p.name)

    _, _, html = route(f"/p/{snail.id}")
    html = html.decode()
    assert "<title>Cosrx Advanced Snail 96 Mucin Power Essence 100 ml: precio en Chile · Yumori</title>" in html
    assert f'<link rel="canonical" href="https://yumori.cl/p/{snail.id}">' in html and 'name="robots"' not in html
    assert ('<meta name="description" content="Cosrx Advanced Snail 96 Mucin Power Essence 100 ml: desde $27.000 en 2 tiendas de Chile '
            'con stock. Compara precios, stock e historial antes de comprar.">') in html
    assert '<meta property="og:image" content="https://img/1.jpg">' in html
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html)]
    product = next(b for b in blocks if b["@type"] == "Product")
    # solo las tiendas con stock confirmado (c.cl está agotada) y sin la nota de las tiendas
    assert product["offers"] == {"@type": "AggregateOffer", "priceCurrency": "CLP", "lowPrice": 27000, "highPrice": 28900,
                                 "offerCount": 2, "availability": "https://schema.org/InStock"}
    assert "aggregateRating" not in product and product["brand"]["name"] == "Cosrx"
    assert [i["name"] for i in next(b for b in blocks if b["@type"] == "BreadcrumbList")["itemListElement"]][0] == "Inicio"

    # listados: marca y categoría se indexan; búsquedas, filtros y orden no
    brand = route("/explorar", marca=snail.brand_slug)[2].decode()
    assert 'name="robots"' not in brand and f'href="https://yumori.cl/explorar?marca={snail.brand_slug}"' in brand
    for qs in ({"q": "snail"}, {"marca": snail.brand_slug, "orden": "precio_asc"}, {"multi": "1"}, {"marca": "no-existe"}):
        assert '<meta name="robots" content="noindex, follow">' in route("/explorar", **qs)[2].decode(), qs
    assert 'content="noindex' in route("/favoritos")[2].decode() and 'content="noindex' in route("/no-existe")[2].decode()

    robots = route("/robots.txt")[2].decode()
    assert "Disallow: /fragmento/" in robots and "Sitemap: https://yumori.cl/sitemap.xml" in robots
    status, ctype, xml = route("/sitemap.xml")
    assert status == 200 and ctype.startswith("application/xml")
    assert f"<loc>https://yumori.cl/p/{snail.id}</loc>" in xml.decode() and "<loc>https://yumori.cl/marcas</loc>" in xml.decode()


def test_deals_are_measured_against_our_own_history_not_the_stores_strikethrough():
    # el descuento sale de la tabla price (precio más alto de los últimos 14 días), nunca del precio tachado de la tienda
    def at(name, i, price, **kw):
        x = item(i, f"Cosrx Producto {name} 50ml", price)
        x.update(kw)
        return x
    db = connect(":memory:")
    names = [f"N{chr(97 + i)}" for i in range(25)]  # nombres distintos: un producto cada uno
    save(db, "big.cl", [at(n, i, 10000) for i, n in enumerate(names)] + [at("Falso", 100, 10000, compare_at=20000), at("Regalo", 101, 10000),
                                                                           at("Viejo", 102, 10000), at("Compartido", 103, 10000)])
    save(db, "small.cl", [at(n, 200 + i, 10000) for i, n in enumerate(names[:5])] + [at("Compartido", 300, 6000)])
    save(db, "big.cl", [at(n, i, 7000) for i, n in enumerate(names)] + [at("Falso", 100, 10000, compare_at=20000), at("Regalo", 101, 500),
                                                                          at("Viejo", 102, 7000), at("Compartido", 103, 7000)])
    save(db, "small.cl", [at(n, 200 + i, 7000) for i, n in enumerate(names[:5])] + [at("Compartido", 300, 6000)])
    db.execute("UPDATE price SET ts='2025-12-01T00:00:00+00:00' WHERE listing_id=(SELECT id FROM listing WHERE ext_id='102') AND price=10000")
    db.execute("UPDATE price SET ts='2025-12-10T00:00:00+00:00' WHERE listing_id=(SELECT id FROM listing WHERE ext_id='102') AND price=7000")  # bajó hace meses
    db.commit()
    cat = Catalog(db)
    drop = lambda n: next(p for p in cat.products if p.name.endswith(f"Producto {n}")).drop
    off = lambda n, store: next(o for p in cat.products if p.name.endswith(f"Producto {n}") for o in p.offers if o.store == store)
    assert off("Na", "big.cl").drop == 30 and drop("Na") == 30
    assert drop("Falso") == 0  # tachado a 20.000 pero el historial nunca lo vio más caro
    assert drop("Regalo") == 0  # baja de 95%: error de carga o regalo, se ignora
    assert drop("Viejo") == 0  # bajó hace más de 14 días: ya no es una oferta
    assert off("Compartido", "big.cl").drop == 30 and drop("Compartido") == 0  # el mejor precio es de otra tienda que no bajó
    assert [(d["store"], d["count"], d["median"], d["max"]) for d in cat.deals] == [("big.cl", 26, 30, 30)]  # 25 + Compartido (su oferta bajó aunque otra tienda sea más barata); small.cl (5) no llega al mínimo
    assert cat.deals[0]["name"] == "big.cl"
    f = dict(deals=True, stock=True)
    assert cat.search(**f)[1] == 25  # small.cl comparte 5 de esos productos: no se cuentan dos veces
    assert cat.search(stores=("big.cl",), **f)[1] == cat.counts(**f)["tienda"]["big.cl"] == 26  # con la tienda elegida cuenta su propia baja, también en "Compartido"
    assert cat.search(stores=("small.cl",), **f)[1] == cat.counts(**f)["tienda"]["small.cl"]
    import server  # el precio "antes" tachado de la card es la referencia de nuestro historial, no el tachado de la tienda
    card = lambda n: server.card(next(p for p in cat.products if p.name.endswith(f"Producto {n}")))
    assert '<s class="was"><span class="sr-only">Antes: </span>$10.000</s>' in card("Na") and "−30%" in card("Na")
    assert 'class="was"' not in card("Falso") and "$20.000" not in card("Falso")  # tachado a 20.000 por la tienda: no se muestra
    top = cat.search(sort="descuento")[0]
    assert [p.drop for p in top] == sorted((p.drop for p in top), reverse=True) and top[0].drop == 30
    for d in cat.deals:  # el número del banner es exactamente lo que muestra Explorar al entrar con tienda=X y el filtro de ofertas
        assert d["count"] == cat.search(stores=(d["store"],), deals=True, stock=True)[1], d
    # la fila vale hasta la siguiente: el 10.000 de hace años que se cambió a 8.000 hoy es una baja de hoy; si el cambio fue hace 20 días, ya no
    from datetime import datetime, timedelta, timezone
    db2 = connect(":memory:")
    save(db2, "x.cl", [item(1, "Cosrx Solo Producto 50ml", 10000)])
    save(db2, "x.cl", [item(1, "Cosrx Solo Producto 50ml", 8000)])
    db2.execute("UPDATE price SET ts='2025-01-01T00:00:00+00:00' WHERE price=10000")
    db2.commit()
    assert Catalog(db2).products[0].drop == 20
    db2.execute("UPDATE price SET ts=? WHERE price=8000", ((datetime.now(timezone.utc) - timedelta(days=20)).isoformat(timespec="seconds"),))
    db2.commit()
    assert Catalog(db2).products[0].drop == 0


def test_deals_banner_card_pill_and_explorer_filter_render():
    import html
    import re
    from unittest import mock
    from urllib.parse import parse_qs
    import server
    from catalog import PAGE_SIZE
    def at(i, price):
        return item(i, f"Cosrx Producto N{chr(97 + i % 26)}{i // 26} 50ml", price)
    db = connect(":memory:")
    save(db, "big.cl", [at(i, 10000) for i in range(25)] + [at(100, 10000)])
    save(db, "big.cl", [at(i, 7000) for i in range(25)] + [at(100, 10000)])  # 25 productos bajaron 30%; el 100 no
    cat = Catalog(db)
    assert [d["store"] for d in cat.deals] == ["big.cl"]
    with mock.patch.object(server, "get_catalog", lambda: cat):
        home = server.home(cat)[1]
        link = re.search(r'<a class="link deals-all" href="([^"]*)">Ver las 25 ofertas</a>', home)
        href = html.unescape(link.group(1))
        assert href == "/explorar?oferta=1&orden=descuento"
        assert "Ofertas detectadas" in home and "No es publicidad" in home and 'class="deals-track"' in home
        strip = home.split('class="deals-track"', 1)[1].split("</section>", 1)[0]
        assert 0 < strip.count('<article class="card">') <= 24 and strip.count("−30%") == strip.count('<article class="card">')  # tarjetas de productos, todas con su baja
        assert "CyberDay" not in home and "Black Friday" not in home  # los datos no traen eventos: no se inventan
        assert 'class="deal-pill"' in home and "−30%" in home  # las cards de "Bajaron de precio" llevan la etiqueta
        # el número del banner es exactamente el total que se ve al hacer clic
        qs = parse_qs(href.split("?")[1])
        page = server.explore(cat, qs)[1]
        assert "25 productos</p>" in page and "Productos con descuento" in page  # el número del enlace es el total que se ve al hacer clic
        assert re.search(r'name="oferta" value="1" checked>Solo con descuento', page) and 'value="descuento"' in page
        assert "Mayor descuento" in page and 'aria-label="Quitar filtro de descuento"' in page
        assert page.count('class="deal-pill"') == min(25, PAGE_SIZE)
        plain = server.explore(cat, {})[1]
        assert "26 productos</p>" in plain and not re.search(r'name="oferta" value="1" checked', plain) and "Solo con descuento" in plain
        clear = html.unescape(re.search(r'href="([^"]*)">Limpiar', server.explore(cat, {**qs, "q": ["producto"]})[1]).group(1))
        assert "oferta" not in clear and "q=producto" in clear  # Limpiar quita el filtro y conserva la búsqueda
        # sin tiendas con 20+ rebajados no hay banner (ni un hueco)
        none = Catalog(connect(":memory:"))
        assert none.deals == [] and "deals" not in server.home(none)[1] and "Ofertas detectadas" not in server.home(none)[1]
    assert 'class="deal-pill"' in server.suggestions(cat, "producto na0")  # y las sugerencias del buscador


def test_placeholder_price_is_not_the_best_price_nor_a_deal():
    # caso real: Vierose publicó productos a $1.000.000 (relleno para "no disponible") y días después los corrigió a su precio real
    import server
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Numbuzin No5 Vitamin Serum 30ml", 28990)])
    save(db, "vierose.cl", [item(2, "Numbuzin No5 Vitamin Serum 30ml", 1000000), item(3, "Misucka Hair Oil 60ml", 1000000)])
    cat = Catalog(db)
    p = next(p for p in cat.products if "Vitamin" in p.name)
    off = next(o for o in p.offers if o.store == "vierose.cl")
    assert off.suspect == "fuera de rango" and not off.available and p.min_price == 28990
    _, html = server.product(cat, p.id)
    assert "Precio por confirmar" in html
    solo = next(p for p in cat.products if "Hair Oil" in p.name)
    assert "sin confirmar" in server.card(solo) and "Precio por confirmar" in server.product(cat, solo.id)[1]
    save(db, "vierose.cl", [item(2, "Numbuzin No5 Vitamin Serum 30ml", 27990), item(3, "Misucka Hair Oil 60ml", 4990)])  # lo corrigen
    cat = Catalog(db)
    p = next(p for p in cat.products if "Vitamin" in p.name)
    off = next(o for o in p.offers if o.store == "vierose.cl")
    assert off.suspect is None and off.available and p.min_price == 27990
    assert off.drop == 0  # la corrección del relleno no es una oferta de 97%
    assert not cat.deals and not cat.search(deals=True)[1]


def _alias_db(code_a=None, code_b=None):
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Anua Heartleaf Toner 250ml", 20000, vendor="Anua", gtin=code_a)])
    save(db, "b.cl", [item(2, "Heartleaf 77 Soothing Toner Calming 250 ml", 21000, vendor="Anua", gtin=code_b)])
    return db


def test_an_id_that_changes_keeps_an_alias_and_resolve_follows_it():
    G = "08809640734526"
    db = _alias_db()
    first = Catalog(db)
    old = sorted(p.id for p in first.products)
    assert len(old) == 2 and first.alias == {} and first.resolve(old[0]) == old[0]  # línea base: nada que anotar
    assert db.execute("SELECT COUNT(*) FROM listing WHERE pid IS NOT NULL").fetchone()[0] == 2
    save(db, "a.cl", [item(1, "Anua Heartleaf Toner 250ml", 20000, vendor="Anua", gtin=G)])  # las tiendas empiezan a publicar el código
    save(db, "b.cl", [item(2, "Heartleaf 77 Soothing Toner Calming 250 ml", 21000, vendor="Anua", gtin=G)])
    cat = Catalog(db)
    (p,) = cat.products
    assert p.matched_by == "gtin" and p.id in old and len(p.offers) == 2
    (dead,) = [i for i in old if i != p.id]
    assert cat.alias == {dead: p.id} and cat.resolve(dead) == p.id and cat.resolve(p.id) == p.id
    assert dict(db.execute("SELECT old_id, new_id FROM product_alias")) == {dead: p.id}
    assert Catalog(db).alias == {dead: p.id}  # un armado más no cambia nada
    import server  # el sitio: un enlace viejo redirige al id actual y los favoritos guardados con el id viejo se siguen viendo
    orig, server.get_catalog = server.get_catalog, lambda: cat
    try:
        status, _, _, headers = server.route(f"/p/{dead}", {})
        assert status == 301 and headers == {"Location": f"/p/{p.id}"}
        cards = server.route("/fragmento/cards", {"ids": [f"{dead},{p.id},ya-no-existe"]})[2].decode()
        assert cards.count('<article class="card"') == 1 and f"/p/{p.id}" in cards  # sin repetir y sin el que ya no existe
        assert server.route("/p/ya-no-existe", {})[0] == 404
    finally:
        server.get_catalog = orig
    assert Catalog(_alias_db("08809640734526", None), sync=False).alias == {}  # sync=False no escribe ni anota


def test_first_fill_of_pid_notes_the_ids_the_gtin_merge_changes():
    G = "08809640734526"
    db = _alias_db(G, G)  # base existente: listing.pid vacío y el GTIN ya cambia el agrupamiento
    text_only = {p.id for p in Catalog(_alias_db(), sync=False).products}
    cat = Catalog(db)
    (p,) = cat.products
    assert all(cat.resolve(i) == p.id for i in text_only)  # los ids de antes del GTIN (favoritos guardados) siguen funcionando
    assert len(cat.alias) == 1


def test_alias_chains_resolve_and_cycles_or_unknown_ids_do_not():
    db = _alias_db()
    live = Catalog(db).products[0].id
    db.executemany("INSERT INTO product_alias VALUES(?,?,'x')", [("a", "b"), ("b", live), ("x", "y"), ("y", "x")])
    cat = Catalog(db)
    assert cat.resolve("a") == live and cat.resolve("b") == live and cat.resolve(live) == live  # a -> b -> vigente
    assert cat.resolve("x") is None and cat.resolve("y") is None and cat.resolve("nunca-existio") is None  # ciclo y desconocido


def test_sync_aliases_flattens_chains_and_a_live_id_never_has_an_alias():
    from db import sync_aliases
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "X 10ml", 1000)])
    assert sync_aliases(db, {1: "b"}, lambda l: "a") == {"a": "b"}  # a ya no existe: ahora es b
    assert sync_aliases(db, {1: "c"}, lambda l: None) == {"a": "c", "b": "c"}  # b -> c aplana a -> b -> c
    assert sync_aliases(db, {1: "a"}, lambda l: None) == {"b": "a", "c": "a"}  # a vuelve a ser vigente: pierde su alias y nada queda en ciclo
    assert dict(db.execute("SELECT old_id, new_id FROM product_alias")) == {"b": "a", "c": "a"}


def test_backup_images_from_other_stores_when_one_is_down():
    # caso real: kosmeticos.cl dejó de responder y sus fotos (las 4 de la galería, por ser la tienda más barata) no cargaban, aunque
    # el mismo producto tenía fotos en otras 3 tiendas
    import json
    import server
    db = connect(":memory:")
    save(db, "tienda-ejemplo.cl", [item(1, "Nida Youthful Formula Cream 100ml", 12360, vendor="NIDA",
                                    images=json.dumps([f"https://tienda-ejemplo.cl/{n}.jpg" for n in range(4)]))])
    save(db, "rakuen.cl", [item(2, "Nida Youthful Formula Cream 100ml", 19990, vendor="NIDA", images=json.dumps(["https://cdn.shopify.com/r1.jpg", "https://cdn.shopify.com/r2.jpg"]))])
    save(db, "unnie.cl", [item(3, "Nida Youthful Formula Cream 100ml", 18990, vendor="NIDA", image="https://unnie.cl/u1.jpg")])
    (p,) = Catalog(db).products
    assert p.image == "https://tienda-ejemplo.cl/0.jpg" and all("tienda-ejemplo" in u for u in p.images)  # la galería sigue priorizando la más barata
    assert p.alts == ["https://unnie.cl/u1.jpg", "https://cdn.shopify.com/r1.jpg"]  # una por cada OTRA tienda, la más barata primero
    assert 'data-alts="[&quot;https://unnie.cl/u1.jpg&quot;, &quot;https://cdn.shopify.com/r1.jpg&quot;]"' in server.card(p)


def sections_db():
    from catalog import PHARMACY_STORES
    farm = "www.farmaciasahumada.cl"  # los textos de las pruebas nombran a Ahumada
    assert farm in PHARMACY_STORES
    db = connect(":memory:")
    save(db, farm, [item(1, "Eucerin DermatoCLEAN Gel Limpiador 200ml", 12000, vendor="Eucerin"),  # marca de la lista, solo en farmacia
                    item(2, "Isispharma Ruboril Expert 40ml", 20000, vendor="Isispharma"),  # marca desconocida, solo en farmacia
                    item(3, "SKIN1004 Madagascar Centella Ampoule 100ml", 17000, vendor="SKIN1004")])  # asiática también en farmacia
    save(db, "a.cl", [item(4, "SKIN1004 Madagascar Centella Ampoule 100ml", 19000, vendor="SKIN1004"),
                      item(5, "Cosrx Snail Mucin Essence 100ml", 20000)])
    save(db, "yes.com", [item(6, "La Roche-Posay Cicaplast Baume B5 40ml", 1500, vendor="La Roche Posay", currency="USD")])  # lista manda aunque la venda una tienda asiática
    return db, farm


def test_section_is_decided_by_brand_not_by_store():
    db, farm = sections_db()
    cat = Catalog(db)
    sec = lambda word: next(p.section for p in cat.products if word in p.name)
    assert sec("DermatoCLEAN") == "dermocosmetica"  # de la lista
    assert sec("Ruboril") == "dermocosmetica"  # desconocida y solo en farmacia
    assert sec("Cicaplast") == "dermocosmetica"  # de la lista, aunque YesStyle (no farmacia) la venda
    assert sec("Snail") == "asiatica"
    sk = next(p for p in cat.products if "Centella" in p.name)
    assert sk.section == "asiatica" and {o.store for o in sk.offers} == {farm, "a.cl"}  # el precio chileno de la farmacia se suma a la comparación
    assert [o.store for o in sk.offers] == [farm, "a.cl"] and sk.min_price == 17000
    assert cat.section_counts == {"asiatica": 2, "dermocosmetica": 3}
    assert farm in cat.stores and farm in cat.derm_stores  # la farmacia aparece en las dos secciones, cada una con lo suyo
    assert cat.stores[farm] == 1 and cat.derm_stores[farm] == 2 and "a.cl" not in cat.derm_stores
    assert "la-roche-posay" in cat.derm_brands and "la-roche-posay" not in cat.brands and "eucerin" not in cat.brands


def test_section_filter_default_is_asian_and_counts_match_search():
    db, farm = sections_db()
    cat = Catalog(db)
    assert {p.section for p in cat.search()[0]} == {"asiatica"} and cat.search()[1] == 2
    assert cat.search(section="dermocosmetica")[1] == 3 and cat.search(section="")[1] == 5
    assert cat.search("eucerin")[1] == 0 and cat.search("eucerin", section="dermocosmetica")[1] == 1
    assert {x[0] for x in cat.top_brands(10)} == {"skin1004", "cosrx"}
    assert {x[0] for x in cat.top_brands(10, "dermocosmetica")} == {"eucerin", "isispharma", "la-roche-posay"}
    assert cat.top_spread(section="dermocosmetica") == [] and [p.section for p in cat.suggest("cicaplast")] == []
    assert len(cat.suggest("cicaplast", section="dermocosmetica")) == 1
    for sect in ("asiatica", "dermocosmetica", ""):
        for stock in (False, True):
            n = cat.counts(stock=stock, section=sect)
            for key, slug in (("tienda", farm), ("tienda", "a.cl")):
                assert n[key].get(slug, 0) == cat.search(stores=[slug], stock=stock, section=sect)[1], (sect, stock, slug)
            f = cat.facets(stock, section=sect)
            assert sum(f["groups"].values()) <= len(f["singles"])
    assert cat.counts(stock=True)["tienda"] == {farm: 1, "a.cl": 2}  # por defecto, /tiendas igual que antes: solo asiática


def test_card_price_is_shown_apart_and_never_counts_as_a_price():
    db, farm = sections_db()
    cols = {r[1] for r in db.execute("PRAGMA table_info(listing)")}
    for c, t in (("card_price", "INTEGER"), ("card_name", "TEXT")):
        if c not in cols:
            db.execute(f"ALTER TABLE listing ADD COLUMN {c} {t}")
    # la farmacia vende SKIN1004 a 17000 normal; con tarjeta, 9000
    base = Catalog(db)
    ref = next(p for p in base.products if "Centella" in p.name)
    assert ref.card_offers == [] and all(o.card_price is None for o in ref.offers)
    db.execute("UPDATE listing SET card_price=9000, card_name='CMR Falabella' WHERE id=3")
    db.execute("UPDATE listing SET card_price=19500, card_name='Mayor que el normal' WHERE id=4")  # no es ahorro: no entra a card_offers
    db.commit()
    cat = Catalog(db)
    p = next(p for p in cat.products if "Centella" in p.name)
    assert [(o.store, o.card_price, o.card_name) for o in p.card_offers] == [(farm, 9000, "CMR Falabella")]
    assert (p.min_price, p.display_price, p.drop) == (ref.min_price, ref.display_price, ref.drop) == (17000, 17000, 0)
    assert [o.price for o in p.offers] == [17000, 19000] and cat.search(pmax=9500)[1] == 0 and cat.search(pmax=17000)[1] == 1
    assert cat.deals == base.deals
    # sin stock (o sin conexión) no se ofrece
    db.execute("INSERT INTO price(listing_id, ts, price, compare_at, available) VALUES(3, '2999-01-01T00:00:00+00:00', 17000, NULL, 0)")
    db.commit()
    assert next(p for p in Catalog(db).products if "Centella" in p.name).card_offers == []


def test_dermocosmetica_section_and_card_price_render():
    import re
    from unittest import mock
    import server
    db, farm = sections_db()
    cat = Catalog(db)
    plain = build()  # solo asiática: la sección no existe todavía (Ahumada sin leer)
    with mock.patch.object(server, "get_catalog", lambda: plain):
        d0 = server.explore(plain, {}, section=server.DERM)[1]
        assert "Estamos sumando farmacias" in d0 and 'content="noindex, follow"' in d0 and 'id="ff"' not in d0  # aviso honesto, sin explorador roto
        assert 'class="home-more"' not in server.home(plain)[1] and "<loc>" in server.sitemap(plain) and "/dermocosmetica" not in server.sitemap(plain)
        assert server.route("/dermocosmetica", {})[0] == 200 and server.route("/dermocosmetica/packs", {})[0] == 200
        assert 'href="/dermocosmetica"' in server.layout("x", "")  # el enlace de la barra existe igual (la página explica por qué está vacía)
        assert "dermocosm" not in server.explore(plain, {})[1].split("<main", 1)[1].lower()  # Explorar no cambia
    with mock.patch.object(server, "get_catalog", lambda: cat):
        home = server.home(cat)[1]
        assert 'class="home-more"' in home and "2 productos ·" in home  # el inicio cuenta solo lo asiático
        assert "Eucerin" not in server.explore(cat, {})[1] and "Eucerin" not in home
        _, derm = server.explore(cat, {}, section=server.DERM)
        assert "<h1>Dermocosmética</h1>" in derm and '<p class="muted">3 productos</p>' in derm and "DermatoCLEAN" in derm and "Snail" not in derm
        assert re.search(r'<link rel="canonical" href="[^"]*/dermocosmetica">', derm) and 'name="robots"' not in derm  # indexable, con su propia canónica
        assert "<title>Dermocosmética en farmacias de Chile: precios · Yumori</title>" in derm and 'content="Dermocosmética: Eucerin, ' in derm
        assert 'action="/dermocosmetica"' in derm  # el buscador de la barra busca dentro de la sección en que se está
        stores_html = derm.split("<summary>Tiendas</summary>")[1].split("</details>")[0]
        assert "Farmacias Ahumada" in stores_html and 'value="a.cl"' not in stores_html  # los filtros son de la sección, no de todo el catálogo
        assert re.search(r"Farmacias Ahumada<span class=\"n\">2</span>", stores_html)  # y su número es el de la lista (2 en la farmacia)
        assert server.explore(cat, {"tienda": [farm]}, section=server.DERM)[1].count('class="card"') == cat.search(stores=[farm], stock=True, section="dermocosmetica")[1] == 2
        assert 'content="noindex, follow"' in server.explore(cat, {"q": ["eucerin"]}, section=server.DERM)[1]
        # una búsqueda mira solo su sección y avisa si la otra tiene resultados
        _, asian_q = server.explore(cat, {"q": ["eucerin"]})
        assert "No encontramos productos" in asian_q and "Hay 1 producto de dermocosmética que coincide." in asian_q and 'class="btn btn-primary btn-sm" href="/dermocosmetica?q=eucerin"' in asian_q
        _, derm_q = server.explore(cat, {"q": ["snail"]}, section=server.DERM)
        assert "Hay 1 producto de belleza asiática que coincide." in derm_q and 'href="/explorar?q=snail"' in derm_q
        save(db, farm, [item(7, "Eucerin Snail Repair Cream 50ml", 15000, vendor="Eucerin")])  # ahora "snail" está en las dos secciones
        both = Catalog(db)
        _, asian_both = server.explore(both, {"q": ["snail"]})
        assert "También hay 1 producto de dermocosmética que coincide · " in asian_both and "Hay 1 producto" not in asian_both  # con resultados, una línea chica
        # sugerencias: lo asiático primero, dermocosmética con su etiqueta y su propio enlace
        sug = server.suggestions(cat, "eucerin")
        assert "Dermocosmética · Eucerin" in sug and 'href="/dermocosmetica?q=eucerin"' in sug and 'href="/explorar?q=eucerin"' not in sug
        sug = server.suggestions(cat, "snail")
        assert "Dermocosmética" not in sug and "/dermocosmetica" not in sug
        sug = server.suggestions(cat, "skin1004")  # asiática (también en la farmacia): sin etiqueta
        assert "Dermocosmética" not in sug and sug.count('id="sug-all') == 1
        # marcas y tiendas: segunda parte, de la A a la Z y sin ranking
        marcas = server.brands(cat)[1]
        assert "Belleza asiática" in marcas and 'href="/dermocosmetica?marca=eucerin"' in marcas and 'href="/explorar?marca=cosrx"' in marcas
        assert "Belleza asiática" not in server.brands(plain)[1] and "Dermocosmética" not in server.brands(plain)[1].split("<main")[-1]
        tiendas = server.stores(cat)[1]
        assert 'href="/dermocosmetica?tienda=' in tiendas and "Dermocosmética" in tiendas and "Dermocosmética" not in server.stores(plain)[1].split("<main")[-1]
        xml = server.sitemap(cat)
        assert re.search(r"<loc>[^<]*/dermocosmetica</loc>", xml) and "dermocosmetica?marca=eucerin" in xml
        # páginas de producto: crumbs de la sección
        eu = next(p for p in cat.products if "DermatoCLEAN" in p.name)
        assert 'href="/dermocosmetica">Dermocosmética</a>' in server.product(cat, eu.id)[1]
    # precio con tarjeta: bloque aparte, solo si hay oferta con tarjeta menor que la normal
    db.execute("UPDATE listing SET card_price=9000, card_name='CMR <b>Falabella</b>' WHERE id=3")
    db.execute("UPDATE listing SET card_price=19500, card_name='Mayor que el normal' WHERE id=4")  # no es ahorro: no se muestra
    db.commit()
    cat = Catalog(db)
    sk = next(p for p in cat.products if "Centella" in p.name)
    with mock.patch.object(server, "get_catalog", lambda: cat):
        _, page = server.product(cat, sk.id)
        assert "<h2>Con tarjeta de la tienda</h2>" in page and page.index("Precios por tienda") < page.index("Con tarjeta de la tienda")
        assert "Precio exclusivo con CMR &lt;b&gt;Falabella&lt;/b&gt;; no lo paga cualquier cliente, por eso no cuenta como mejor precio." in page and "<b>Falabella" not in page
        assert '<div class="offer-price">$9.000<small>Precio normal: $17.000</small></div>' in page
        assert re.search(r">Ver en Farmacias Ahumada<span class=\"sr-only\"> con CMR &lt;b&gt;Falabella&lt;/b&gt; \(se abre en otra pestaña\)</span>", page)
        assert "Mayor que el normal" not in page and '<strong>$17.000</strong>' in page and "Mejor precio en" in page  # el precio destacado sigue siendo el normal
        assert "$9.000" not in server.card(sk) and "tarjeta" not in server.card(sk).lower()  # la card no muestra el precio con tarjeta
        eu = next(p for p in cat.products if "DermatoCLEAN" in p.name)
        assert "Con tarjeta de la tienda" not in server.product(cat, eu.id)[1]  # sin oferta con tarjeta, no hay bloque


def test_partial_stores_say_not_updated_instead_of_gone():
    # Paris y Farmaloop (db.PARTIAL) solo muestran una parte de cada listado: que un producto no venga no dice que lo sacaron
    from types import SimpleNamespace
    import server
    gone = lambda store: server.gone_label(SimpleNamespace(stale=None, gone="2026-10-01", store=store))[0]
    assert gone("www.paris.cl") == gone("www.farmaloop.cl") == "Sin actualizar"
    assert gone("www.farmaciasahumada.cl") == "No aparece en la tienda"


def test_dermo_product_links_to_search_in_stores_we_do_not_read():
    from unittest import mock
    import server
    db, farm = sections_db()
    cat = Catalog(db)
    derm = next(p for p in cat.products if "DermatoCLEAN" in p.name)
    asian = next(p for p in cat.products if "Snail" in p.name)
    with mock.patch.object(server, "get_catalog", lambda: cat):
        page = server.product(cat, derm.id)[1]
        assert "Búscalo también en" in page and "https://salcobrand.cl/search_result?query=Eucerin+DermatoCLEAN" in page
        assert page.count('rel="noopener nofollow"') >= len(server.SEARCH_ELSEWHERE)  # sin "sponsored": no es una oferta
        block = page.split("Búscalo también en")[1].split("</section>")[0]
        assert "$" not in block  # sin precio: no se compara
        assert "Búscalo también en" not in server.product(cat, asian.id)[1]


def test_event_counts_only_drops_that_started_during_it():
    from datetime import date, datetime, timedelta, timezone
    import catalog
    import server
    day = date.today().isoformat()
    old = list(catalog.EVENTS)
    catalog.EVENTS[:] = [{"slug": "cyber", "name": "Cyber", "start": day, "end": day, "theme": "cyber"}]  # el evento es hoy
    try:
        ev = catalog.live_event()
        db = connect(":memory:")
        names = ["Durante", "Antes", "Poquito", "Igual"]
        save(db, "a.cl", [item(i, f"Cosrx Producto {n} 50ml", 10000) for i, n in enumerate(names)])
        db.execute("UPDATE price SET ts=?", ((datetime.now(timezone.utc) - timedelta(days=6)).isoformat(timespec="seconds"),))
        save(db, "a.cl", [item(1, "Cosrx Producto Antes 50ml", 7000)])  # bajó antes del evento...
        db.execute("UPDATE price SET ts=? WHERE price=7000", ((datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec="seconds"),))
        save(db, "a.cl", [item(0, "Cosrx Producto Durante 50ml", 7000), item(2, "Cosrx Producto Poquito 50ml", 9500),  # ...y estas, hoy
                          item(3, "Cosrx Producto Igual 50ml", 10000)])
        db.commit()
        cat = Catalog(db)
        by = {p.name.split()[-1]: p for p in cat.products}
        assert by["Durante"].event_drop(ev) == 30 and by["Durante"].drop == 30
        assert by["Antes"].drop == 30 and by["Antes"].event_drop(ev) == 0  # sigue en oferta, pero la rebaja no es del evento
        assert by["Poquito"].event_drop(ev) == 0 and by["Igual"].event_drop(ev) == 0  # 5% no llega al mínimo; sin cambio no hay baja
        assert [p.name for p in cat.search(section="", event=ev)[0]] == ["Producto Durante"]
        assert cat.counts(section="", event=ev)["tienda"]["a.cl"] == 1

        server.get_catalog = lambda: cat
        html = server.route("/cyber", {}, base="https://yumori.cl")[2].decode()
        assert "Producto Durante" in html and "Producto Antes" not in html and "rebajas que ya venían de antes no cuentan" in html
        nav = html.split('aria-label="Principal">', 1)[1]
        assert nav.startswith('<a class="nav-event" href="/cyber"')  # el evento en curso va primero, antes de "Categorías"
        assert 'class="ev-logo ev-cyber"' in nav
        assert "1 producto rebajado en 1 tienda" in server.route("/", {}, base="https://yumori.cl")[2].decode()
        catalog.EVENTS[:] = [{"slug": "cyber", "name": "Cyber", "start": "2000-01-01", "end": "2000-01-02", "theme": "cyber"}]
        home = server.route("/", {}, base="https://yumori.cl")[2].decode()  # terminado: la página sigue, pero ya no se promueve
        assert 'class="nav-event"' not in home and "event-callout" not in home
        assert server.route("/cyber", {}, base="https://yumori.cl")[0] == 200
    finally:
        catalog.EVENTS[:] = old


def test_black_friday_is_computed_every_year_and_pages_pick_the_right_edition():
    from datetime import date
    import catalog
    assert (catalog.black_friday(2026)["start"], catalog.black_friday(2026)["end"]) == ("2026-11-27", "2026-11-30")  # Acción de Gracias: 26 nov
    assert catalog.black_friday(2025)["start"] == "2025-11-28" and catalog.black_friday(2027)["start"] == "2027-11-26"
    assert catalog.live_event(date(2026, 11, 28))["name"] == "Black Friday" and catalog.live_event(date(2026, 11, 1)) is None
    assert catalog.event_for("black-friday", date(2026, 10, 4))["start"] == "2026-11-27"  # antes del evento: el próximo, no el del año pasado
    assert catalog.event_for("black-friday", date(2026, 12, 5))["start"] == "2026-11-27"  # recién terminado: sus rebajas pueden seguir
    assert catalog.event_for("no-existe") is None
    pre = {"slug": "x", "name": "X", "start": "2026-10-05", "end": "2026-10-07", "early": "2026-10-01", "theme": "cyber"}
    old = list(catalog.EVENTS)
    catalog.EVENTS[:] = [pre]
    try:  # con previa, la sección se activa y cuenta desde `early`, aunque las fechas del evento sigan siendo 5 al 7
        assert catalog.live_event(date(2026, 10, 2))["slug"] == "x" and catalog.live_event(date(2026, 9, 30)) is None

        class O:
            available, drop, since = True, 20, "2026-10-02"
        assert catalog.in_event(O, pre) and not catalog.in_event(O, {**pre, "early": None})
    finally:
        catalog.EVENTS[:] = old


def test_shipping_is_shown_as_store_info_never_added_to_the_price():
    import server
    from shipping import SHIPPING
    assert server.shipping_text("sokobox.cl").startswith("Despacho desde $3.990 · gratis sobre $59.990 en todo Chile")
    assert server.shipping_text("unniebeauty.cl") == "El costo se calcula al pagar (Starken o Bluexpress)"  # sin montos: solo su nota
    assert server.shipping_text("no-revisada.cl") == ""  # no revisada: no se muestra nada (no se inventa)
    db = connect(":memory:")
    save(db, "sokobox.cl", [item(1, "Anua Heartleaf Toner 250ml", 20000, vendor="Anua")])
    save(db, "otra.cl", [item(2, "Anua Heartleaf Toner 250ml", 21000, vendor="Anua")])
    cat = Catalog(db)
    _, html = server.product(cat, cat.products[0].id)
    assert "Despacho desde $3.990" in html and "Los precios no incluyen despacho" in html
    assert cat.products[0].min_price == 20000  # el despacho no cambia el precio ni el mejor precio
    assert "sokobox.cl" in SHIPPING and all(set(v) >= {"desde", "gratis", "donde", "fuente"} for v in SHIPPING.values())


def test_related_products_are_similar_varied_and_never_the_same_product():
    import server
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 20000, description="Esencia con mucina de caracol y ácido hialurónico."),
                      item(2, "Cosrx Snail Mucin Essence 30ml", 9000, description="Esencia con mucina de caracol."),  # el mismo, otro tamaño
                      item(3, "Mizon Snail Repair Essence 50ml", 15000, vendor="Mizon", description="Esencia con mucina de caracol y ácido hialurónico."),
                      item(4, "Anua Heartleaf Essence 50ml", 18000, vendor="Anua", description="Esencia calmante."),
                      item(5, "Anua Heartleaf Toner 250ml", 21000, vendor="Anua", description="Tónico con mucina de caracol."),  # otro tipo
                      item(6, "Mizon Snail Agotada Essence 50ml", 15000, vendor="Mizon", available=0)])  # sin stock
    cat = Catalog(db)
    p = next(x for x in cat.products if x.size == "100 ml")
    names = [c.name for c in cat.related(p)]
    assert names[0] == "Snail Repair Essence"  # comparte más ingredientes: va primero
    assert "Heartleaf Essence" in names and "Heartleaf Toner" not in names  # mismo tipo sí; un tónico no
    assert not any("Agotada" in x or x == "Snail Mucin Essence" for x in names)  # ni sin stock ni el mismo en otro tamaño
    html = server.product(cat, p.id)[1]
    assert "También te podría interesar" in html and "Snail Repair Essence" in html


def test_deal_strip_mixes_stores_without_favoritism_and_rotates():
    db = connect(":memory:")
    big = [item(i, f"Marca{i} Producto Grande{i} 50ml", 10000, vendor=f"Marca{i}") for i in range(30)]
    small = [item(100 + i, f"Otra{i} Producto Chico{i} 50ml", 10000, vendor=f"Otra{i}") for i in range(3)]
    save(db, "grande.cl", big)
    save(db, "chica.cl", small)
    save(db, "grande.cl", [{**x, "price": 6000} for x in big])  # 30 bajas de 40% en una tienda...
    save(db, "chica.cl", [{**x, "price": 6000} for x in small])  # ...y 3 en otra
    cat = Catalog(db)
    picks = cat.deal_picks(n=6, seed="a")
    stores = [p.offers[0].store for p in picks]
    assert stores[:6] == ["chica.cl", "grande.cl"] * 3  # se intercalan en orden alfabético: la tienda grande no tapa a la chica
    assert [p.id for p in cat.deal_picks(n=6, seed="a")] == [p.id for p in picks]  # misma hora, misma franja
    assert {p.id for p in cat.deal_picks(n=10, seed="b")} != {p.id for p in cat.deal_picks(n=10, seed="a")}  # otra hora, otros productos
    assert all(p.drop >= 20 for p in picks)


def test_card_brand_links_to_all_its_products_without_nesting_links():
    import re
    import server
    cat = build()
    p = next(x for x in cat.products if "Snail" in x.name)
    html = server.card(p)
    assert f'<a class="card-link" href="/p/{p.id}">' in html  # toda la tarjeta lleva al producto...
    assert f'<a class="card-brand" href="/explorar?marca={p.brand_slug}">Cosrx</a>' in html  # ...y la marca, a todos los de su marca
    assert not re.search(r"<a [^>]*>(?:(?!</a>).)*<a ", html, re.S)  # nunca un enlace dentro de otro


def test_brand_site_text_feeds_the_description_only_when_one_product_matches():
    import server
    from datetime import datetime, timezone
    db = connect(":memory:")
    save(db, "yesstyle.com", [item(1, "Tocobo Glass Tinted Lip Balm 3.5g", 9000, vendor="Tocobo"),  # sin descripción en la tienda
                              item(2, "Tocobo Bio Watery Sun Cream 50ml", 12000, vendor="Tocobo"),
                              item(3, "Tocobo Cotton Soft Sun Stick Set", 20000, vendor="Tocobo")])
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    official = [("tocobo.us", "a", "Tocobo", "Glass Tinted Lip Balm", "Bálsamo labial con acabado glossy. Su acabado glossy dura todo el día.", "u", ts),
                ("tocobo.us", "b", "Tocobo", "Bio Watery Sun Cream SPF50+", "Protector solar hidratante. Su fórmula hidratante ayuda a mantener la piel hidratada.", "u", ts),
                ("tocobo.us", "c", "Tocobo", "Bio Watery Sun Cream Mini", "Otra versión.", "u", ts),  # miniatura: otro formato, no calza
                ("tocobo.us", "d", "Tocobo", "Cotton Soft Sun Stick", "Protector en barra.", "u", ts)]
    db.executemany("INSERT INTO brand_text VALUES(?,?,?,?,?,?,?)", official)
    cat = Catalog(db)
    balm = next(p for p in cat.products if "Lip Balm" in p.name)
    assert balm.brand_site == "tocobo.us" and "glossy" in balm.text  # el texto oficial se suma al de las tiendas...
    assert balm.offers == [] or all(o.store == "yesstyle.com" for o in balm.offers)  # ...pero no es una oferta
    html = server.product(cat, balm.id)[1]
    assert "Tiene un acabado glossy" in html and "y el sitio oficial de la marca" in html
    sun = next(p for p in cat.products if "Sun Cream" in p.name)
    assert sun.brand_site == "tocobo.us" and "hidratante" in sun.text  # la miniatura no compite: otro formato
    pack = next(p for p in cat.products if p.is_pack)
    assert pack.brand_site == "" and "barra" not in pack.text  # un set no recibe el texto de un producto suelto
    # dos productos oficiales distintos que calzan: no se adivina
    db.execute("INSERT INTO brand_text VALUES('tocobo.us','e','Tocobo','Glass Tinted Lip Balm Duo Refill','Otro texto.','u',?)", (ts,))
    assert next(p for p in Catalog(db).products if "Lip Balm" in p.name).brand_site == "tocobo.us"  # "Duo" es pack: no cuenta
    db.execute("INSERT INTO brand_text VALUES('tocobo.us','f','Tocobo','Glass Tinted Lip Balm Original',?,'u',?)",
               ("Texto distinto de la versión original, suficiente para identificar que la descripción pertenece a otro producto.", ts))
    assert next(p for p in Catalog(db).products if "Lip Balm" in p.name).brand_site == ""


def test_retired_store_is_not_shown():
    # Kosmeticos nos bloquea (403) y el dominio de K Belleza no existe: se sacaron de STORES. Sus datos quedan en la base, pero no se
    # muestran (ni como "Sin conexión", que diría que es pasajero) y no cuentan como tienda desactualizada.
    from db import RETIRED
    store = sorted(RETIRED)[0]
    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Cosrx Snail Mucin Essence 100ml", 20000)])
    save(db, store, [item(2, "Cosrx Snail Mucin Essence 100ml", 15000), item(3, "Cosrx Aloe Sun Cream 50ml", 9000)])
    db.execute("INSERT INTO meta VALUES('run:done', '2999-01-01T00:00:00+00:00')")
    db.commit()
    cat = Catalog(db)
    assert [p.name for p in cat.products] == ["Snail Mucin Essence"] or len(cat.products) == 1
    assert all(o.store == "a.cl" for p in cat.products for o in p.offers) and store not in cat.stale


if __name__ == "__main__":
    test_dermocosmetica_section_and_card_price_render()
    test_backup_images_from_other_stores_when_one_is_down()
    test_placeholder_price_is_not_the_best_price_nor_a_deal()
    test_grouping_and_display()
    test_search_and_filters()
    test_clean()
    test_card_rating_uses_store_with_most_reviews()
    test_card_rating_needs_min_reviews()
    test_foreign_offers_stay_apart()
    test_intl_only_product_is_findable_and_priced_with_an_estimate()
    test_packs_stay_out_of_single_comparison_and_link_to_their_products()
    test_pack_does_not_guess_between_sizes_or_shades()
    test_trial_kit_shows_the_smaller_size_inside_the_pack()
    test_small_format_without_sizes_is_still_flagged()
    test_gallery_takes_up_to_four_distinct_images_from_the_best_store_first()
    test_categories_filters_and_bilingual_search()
    test_explorer_hides_out_of_stock_by_default_and_shows_filters()
    test_facet_counts_match_the_list_shown()
    test_pack_contents_link_minis_to_loose_products_and_keep_unlisted_ones()
    test_pack_contents_render_as_clickable_image_cards()
    test_tied_price_does_not_pick_a_favorite_store()
    test_tie_breaks_dynamically_when_a_store_raises_its_price()
    test_stores_page_lists_international_separately()
    test_intl_only_product_page_renders_without_domestic_sections()
    test_intl_only_product_without_fx_shows_no_invented_price()
    test_last_update_does_not_hide_a_store_that_never_reports_success()
    test_offline_store_is_flagged_not_hidden_and_never_the_best_price()
    test_listing_the_store_stopped_returning_is_flagged_not_hidden()
    test_yesstyle_listing_is_missing_only_after_its_brand_is_read_again()
    test_cut_short_read_does_not_mark_half_the_store_as_gone()
    test_filter_counts_respect_every_other_active_filter()
    test_clear_link_keeps_the_search_intact()
    test_price_history_does_not_repeat_the_same_price()
    test_search_suggestions_are_product_cards_with_image_and_link_to_explore()
    test_deals_are_measured_against_our_own_history_not_the_stores_strikethrough()
    test_deals_banner_card_pill_and_explorer_filter_render()
    test_seo_meta_canonical_structured_data_and_sitemap()
    test_shades_with_the_same_name_show_their_variant()
    test_an_id_that_changes_keeps_an_alias_and_resolve_follows_it()
    test_first_fill_of_pid_notes_the_ids_the_gtin_merge_changes()
    test_alias_chains_resolve_and_cycles_or_unknown_ids_do_not()
    test_sync_aliases_flattens_chains_and_a_live_id_never_has_an_alias()
    test_section_is_decided_by_brand_not_by_store()
    test_section_filter_default_is_asian_and_counts_match_search()
    test_card_price_is_shown_apart_and_never_counts_as_a_price()
    test_partial_stores_say_not_updated_instead_of_gone()
    test_dermo_product_links_to_search_in_stores_we_do_not_read()
    test_retired_store_is_not_shown()
    print("ok")
