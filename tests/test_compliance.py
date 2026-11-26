"""Garantías de privacidad, accesibilidad y transparencia del sitio. Si una falla, algo cambió en lo que el sitio promete al público."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # módulos de la raíz
import glob
import re
from pathlib import Path

import legal
import server
from catalog import Catalog
from db import connect, save

ROOT = Path(__file__).resolve().parent.parent


def make_catalog():
    def item(i, title, price, **kw):
        return dict(ext_id=str(i), sku=None, title=title, variant=None, vendor="Anua", url=f"https://tienda{i}.cl/p", price=price,
                    compare_at=None, available=1, **kw)

    db = connect(":memory:")
    save(db, "a.cl", [item(1, "Heartleaf Toner 250ml", 20000, images='["https://img/1.jpg", "https://img/2.jpg"]')])
    save(db, "b.cl", [item(2, "Heartleaf Toner 250ml", 21000)])
    cat = Catalog(db)
    server.get_catalog = lambda: cat  # el pie de página y el menú piden el catálogo
    return cat


def test_layout_has_no_third_party_content_and_is_navigable():
    make_catalog()
    html = server.layout("Prueba", "<p>x</p>")
    assert not re.findall(r'<script[^>]+src="https?:', html) and not re.findall(r'<link(?![^>]*rel="canonical")[^>]+href="https?:', html)  # la canónica es del propio sitio, no carga nada
    assert not re.search(r"<iframe|<embed|<object", html)  # sin contenido incrustado de terceros
    assert 'class="skip" href="#main"' in html and '<main id="main"' in html and 'lang="es"' in html
    for path in ("/privacidad", "/terminos", "/cookies"):
        assert f'href="{path}"' in html  # el pie enlaza las tres páginas legales


def test_product_page_alt_text_and_button_labels():
    cat = make_catalog()
    p = cat.products[0]
    _, html = server.product(cat, p.id)
    assert re.search(r'<img id=main-img[^>]* alt="[^"]*Heartleaf Toner[^"]*imagen 1 de 2"', html)  # la foto principal describe el producto
    assert 'data-alt="Anua Heartleaf Toner, imagen 2 de 2"' in html
    assert re.findall(r'aria-label="Ver Heartleaf Toner en [^"]+ \(se abre en otra pestaña\)"', html)  # botones con contexto, no "Ver en tienda" suelto
    for tag in re.findall(r"<a [^>]*target=\"_blank\"[^>]*>", html):
        assert "noopener" in tag  # los enlaces a otras pestañas no comparten contexto con Yumori


def test_security_headers_are_strict():
    csp = server.SECURITY_HEADERS["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "script-src 'self'" in csp
    assert "unsafe-eval" not in csp and "script-src 'self' 'unsafe" not in csp
    assert server.SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"


def test_no_cookies_no_trackers_no_analytics():
    trackers = ("google-analytics", "googletagmanager", "gtag(", "facebook.net", "fbq(", "hotjar", "doubleclick", "clarity.ms", "mixpanel", "segment.com")
    code = [f for f in glob.glob(str(ROOT / "*.py")) + glob.glob(str(ROOT / "scrapers" / "*.py")) + glob.glob(str(ROOT / "tests" / "*.py")) + glob.glob(str(ROOT / "static" / "*"))
            if not f.endswith("test_compliance.py") and Path(f).is_file()]  # static/fonts es una carpeta
    for f in code:
        text = Path(f).read_text(encoding="utf-8", errors="replace")
        assert not [t for t in trackers if t in text], f
        assert "document.cookie" not in text and "Set-Cookie" not in text, f  # el sitio no usa cookies
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert set(re.findall(r'const KEY = "([^"]+)"', js)) == {"yumori:fav"}  # lo único que se guarda en el navegador: favoritos


def test_legal_pages_say_what_the_site_really_does():
    priv, cook, terms = legal.privacy(), legal.cookies(), legal.terms()
    assert "ningún dato que te identifique" in priv and "Google Analytics (solo si lo aceptas)" in priv
    assert "Yumori no usa cookies propias" in cook and "yumori:fav" in cook and "_ga" in cook
    assert "No vende productos" in terms or "no vende productos" in terms.lower()
    assert "Retiro de contenido" in terms and "estimaciones" in terms and "no son consejo médico" in terms
    for text in (priv, cook, terms):
        assert "Última actualización" in text


def test_missing_owner_data_is_flagged_and_filled_data_removes_the_warning():
    saved = dict(legal.OPERATOR)
    try:
        for k in legal.OPERATOR:
            legal.OPERATOR[k] = ""
        assert legal.missing() and "Antes de publicar el sitio" in legal.privacy()
        for k in legal.OPERATOR:
            legal.OPERATOR[k] = "dato"
        assert not legal.missing() and "Antes de publicar el sitio" not in legal.privacy()
    finally:
        legal.OPERATOR.update(saved)


if __name__ == "__main__":
    test_layout_has_no_third_party_content_and_is_navigable()
    test_product_page_alt_text_and_button_labels()
    test_security_headers_are_strict()
    test_no_cookies_no_trackers_no_analytics()
    test_legal_pages_say_what_the_site_really_does()
    test_missing_owner_data_is_flagged_and_filled_data_removes_the_warning()
    print("ok")
