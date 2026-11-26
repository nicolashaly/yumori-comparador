"""Condiciones de despacho de cada tienda chilena, revisadas a mano en su sitio (portada, barra superior o política de envíos).

No se suman al precio: el despacho se cobra por pedido, depende de la comuna y el envío gratis depende del total del carro.
Se muestran aparte, como dato de la tienda. Lo que una tienda no publica en texto queda en None ("No informado"): no se inventa.
Las tiendas que no aparecen aquí no se pudieron revisar (bloquean nuestras consultas o estaban caídas).

Campos: desde = despacho más barato publicado (CLP), gratis = compra mínima para envío gratis (CLP), donde = alcance de ese
mínimo, nota = otra condición relevante, fuente = página donde se leyó. Volver a revisar cada tanto y actualizar REVIEWED.
"""

REVIEWED = "2026-10-04"

SHIPPING = {
    "sokobox.cl": dict(desde=3990, gratis=59990, donde="todo Chile", fuente="https://sokobox.cl/"),
    "nooki.cl": dict(desde=2990, gratis=50000, donde="la Región Metropolitana", nota="Regiones desde $4.990",
                     fuente="https://nooki.cl/policies/shipping-policy"),
    "coreanachile.cl": dict(desde=None, gratis=50000, donde="la Región Metropolitana", fuente="https://coreanachile.cl/policies/shipping-policy"),
    "www.bombeauty.cl": dict(desde=None, gratis=50000, donde="todo Chile", nota="Bajo ese monto, el costo depende de la comuna",
                             fuente="https://www.bombeauty.cl/policies/shipping-policy"),
    "moonbow.cl": dict(desde=None, gratis=50000, donde="Santiago", fuente="https://moonbow.cl/"),
    "rakuencosmeticacoreana.cl": dict(desde=None, gratis=55000, donde="todo Chile", fuente="https://rakuencosmeticacoreana.cl/"),
    "quecoreana.cl": dict(desde=2300, gratis=50000, donde="todo Chile", fuente="https://quecoreana.cl/"),
    "arumi.cl": dict(desde=None, gratis=50000, donde="todo Chile", nota="Retiro gratis en tienda", fuente="https://arumi.cl/"),
    "dermotienda.cl": dict(desde=2990, gratis=49990, donde="todo Chile", nota="Regiones desde $3.990",
                           fuente="https://dermotienda.cl/policies/shipping-policy"),
    "www.koryobeauty.cl": dict(desde=None, gratis=15000, donde="comunas seleccionadas", fuente="https://www.koryobeauty.cl/"),
    "unniebeauty.cl": dict(desde=None, gratis=None, donde="", nota="El costo se calcula al pagar (Starken o Bluexpress)",
                           fuente="https://unniebeauty.cl/"),
    "www.farmaciasahumada.cl": dict(desde=None, gratis=34990, donde="", fuente="https://www.farmaciasahumada.cl/"),
    "www.ecofarmacias.cl": dict(desde=None, gratis=40000, donde="", fuente="https://www.ecofarmacias.cl/"),
    "www.farmaloop.cl": dict(desde=None, gratis=None, donde="", nota="Envío gratis en la primera compra", fuente="https://www.farmaloop.cl/"),
    "dbs.cl": dict(desde=2990, gratis=None, donde="todo Chile", fuente="https://dbs.cl/"),
}
