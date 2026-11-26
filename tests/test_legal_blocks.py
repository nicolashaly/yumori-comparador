"""El formato legal viaja como nodos seguros, conservando el texto del contrato v1."""
import unittest
from unittest.mock import patch

import api


def flatten(nodes):
    return "".join(node["text"] if "text" in node else flatten(node["children"]) for node in nodes)


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get("children", []))


class LegalBlocksTests(unittest.TestCase):
    def test_format_links_and_plain_text_are_preserved(self):
        html = ('<p>Guarda <strong>solo <em>favoritos</em></strong> en <code>yumori:fav</code>. '
                '<a class="link" href="/cookies">Cookies</a></p>')
        block = api.LegalBlocks(html).blocks[0]
        self.assertEqual(block["text"], "Guarda solo favoritos en yumori:fav. Cookies")
        self.assertEqual(flatten(block["inline"]), block["text"])
        nodes = list(walk(block["inline"]))
        self.assertEqual([node["tag"] for node in nodes if "tag" in node], ["strong", "em", "code", "a"])
        self.assertEqual(nodes[-2]["href"], "/cookies")

    def test_unclosed_format_and_active_html_fail_safely(self):
        html = ('<p>Inicio <strong>negrita <em>énfasis</strong> final '
                '<script>alert(1)</script><svg><script>evil</script></svg>'
                '<a href="javascript:alert(1)" onclick="evil()">texto</a>'
                '<img src="x" onerror="evil()"><p>Otro <code>bloque')
        blocks = api.LegalBlocks(html).blocks
        self.assertEqual([block["text"] for block in blocks], ["Inicio negrita énfasis final texto", "Otro bloque"])
        for block in blocks:
            for node in walk(block["inline"]):
                self.assertTrue(set(node) <= {"text", "tag", "children", "href"})
                self.assertNotIn("href", node)
                if "tag" in node:
                    self.assertIn(node["tag"], {"strong", "em", "code", "span"})

    def test_links_allow_only_safe_http_legal_routes_and_own_contact(self):
        urls = ["/cookies", "//evil.example", "/p/abcdef", "https://example.org/legal",
                "https://user:secret@example.org/", "https://example.org/ bad", "data:text/html,evil",
                "mailto:own@example.org", "mailto:other@example.org", "mailto:own@example.org?subject=evil"]
        html = "<p>" + " ".join(f'<a href="{url}">link</a>' for url in urls) + "</p>"
        with patch.dict(api.legal.OPERATOR, {"Correo de contacto": "own@example.org"}):
            nodes = list(walk(api.LegalBlocks(html).blocks[0]["inline"]))
        self.assertEqual([node["href"] for node in nodes if "href" in node],
                         ["/cookies", "https://example.org/legal", "mailto:own@example.org"])

    def test_escaped_operator_text_remains_literal(self):
        with patch.dict(api.legal.OPERATOR, {"Nombre o razón social": "<script>alert(1)</script>"}):
            blocks = api.LegalBlocks(api.legal.terms()).blocks
        row = next(block for block in blocks if "<script>" in block["text"])
        self.assertIn("<script>alert(1)</script>", flatten(row["inline"]))
        self.assertFalse(any(node.get("tag") == "script" for node in walk(row["inline"])))
