"""Textos legales de Yumori (privacidad, cookies, términos), en HTML listo para insertar en una página.

IMPORTANTE: son textos de buena fe, escritos para lo que el sitio hace HOY. Deben revisarse con un abogado antes de publicar
el sitio en internet, y actualizarse cuando cambie lo que el sitio hace (cuentas, alertas por correo, publicidad, afiliados).
"""
from html import escape as e

UPDATED = "17 de octubre de 2026"

# COMPLETAR antes de publicar el sitio: son los datos de quien opera Yumori.
OPERATOR = {"Nombre o razón social": "", "RUT": "", "Correo de contacto": "", "Domicilio en Chile": ""}


def missing():
    return [k for k, v in OPERATOR.items() if not v.strip()]


def email():
    return OPERATOR["Correo de contacto"].strip()


def contact_block():
    rows = "".join(f"<li><strong>{e(k)}:</strong> {e(v) if v.strip() else '<em>por completar</em>'}</li>" for k, v in OPERATOR.items())
    warn = ('<div class="callout"><strong>Antes de publicar el sitio:</strong> faltan datos del titular. '
            'Complétalos en <code>OPERATOR</code> (archivo <code>legal.py</code>).</div>') if missing() else ""
    return f"{warn}<ul>{rows}</ul>"


def mail_link():
    return f'<a class="link" href="mailto:{e(email())}">{e(email())}</a>' if email() else "el correo de contacto indicado arriba"


def wrap(title, body):
    return (f'<div class="container legal"><div class="page-head"><h1>{e(title)}</h1>'
            f'<p class="muted">Última actualización: {UPDATED}</p></div>{body}</div>')


def privacy():
    return wrap("Política de privacidad", f"""
<h2>Quién es responsable</h2>
<p>Yumori es un sitio que compara precios de productos de belleza y cuidado personal en tiendas de Chile y del extranjero. Lo opera:</p>
{contact_block()}
<h2>Qué datos recogemos</h2>
<p><strong>Hoy, ningún dato que te identifique por nombre o correo.</strong> Yumori no tiene cuentas de usuario, no te pide nombre ni correo, y no usa herramientas de publicidad. Si aceptas las cookies de analítica, Google Analytics mide cómo se usa el sitio (ver «Servicios de terceros»).
Lo que buscas o filtras se usa solo para mostrarte los resultados y no se guarda.</p>
<p>Tus productos favoritos se guardan <strong>únicamente en tu navegador</strong> (almacenamiento local). Para mostrar sus precios, el navegador solicita al catálogo sus identificadores de producto. La lista se guarda únicamente en tu navegador; no almacenamos una lista de favoritos en el servidor. Si la exportas para trasladarla a otra dirección del sitio, el archivo queda en tu dispositivo.</p>
<h2>Registros técnicos</h2>
<p>En su configuración actual, el servidor de Yumori no guarda registros de las visitas. Cuando el sitio se publique en internet, el proveedor de alojamiento podría registrar direcciones IP con fines de seguridad y funcionamiento; lo indicaremos aquí.</p>
<h2>Servicios de terceros</h2>
<ul>
<li><strong>Imágenes de productos:</strong> se cargan directamente desde los servidores de las tiendas (por ejemplo <code>cdn.shopify.com</code> y los sitios de cada tienda). Al mostrarlas, tu navegador se conecta a esos servidores, que pueden ver tu dirección IP y datos técnicos del navegador, como en cualquier página web. No les enviamos la dirección de Yumori como referencia.</li>
<li><strong>Enlaces «Ver en tienda»:</strong> te llevan a sitios de terceros, con sus propias políticas de privacidad. La tienda puede saber que llegaste desde Yumori (solo el dominio, no la página que veías).</li>
<li><strong>Google Analytics (solo si lo aceptas):</strong> mide visitas y páginas vistas. Si aceptas, tu navegador envía a Google datos de uso (páginas visitadas, dispositivo, navegador, ubicación aproximada y tu dirección IP) y se guardan cookies de Google. Si rechazas o no eliges, no se carga nada de Google. Puedes cambiar tu elección en «Preferencias de cookies», al pie de cada página.</li>
<li>No usamos fuentes tipográficas, mapas, videos, botones de redes sociales ni otros contenidos incrustados de terceros.</li>
</ul>
<h2>Cookies y almacenamiento local</h2>
<p>Yumori solo usa cookies de analítica si las aceptas. Encuentras el detalle en la <a class="link" href="/cookies">política de cookies</a>.</p>
<h2>Si esto cambia</h2>
<p>Si más adelante agregamos cuentas, alertas por correo u otras funciones que traten datos personales, actualizaremos esta política antes de activarlas y te pediremos tu consentimiento cuando corresponda. Solo pediremos los datos estrictamente necesarios para cada función.</p>
<h2>Tus derechos</h2>
<p>La ley chilena de protección de datos personales (Ley 19.628, que será reemplazada por la Ley 21.719 desde el 1 de diciembre de 2026) reconoce derechos como acceder a tus datos, rectificarlos, suprimirlos u oponerte a su tratamiento. Como hoy no tratamos datos personales tuyos, no tenemos información para entregar o borrar. Si tienes dudas, escríbenos a {mail_link()}.</p>
""")


def cookies():
    return wrap("Política de cookies", f"""
<h2>Resumen</h2>
<p><strong>Yumori no usa cookies propias</strong> ni de publicidad o redes sociales. Solo, si lo aceptas, usa las cookies de Google Analytics. Si rechazas, no se instala ninguna.</p>
<h2>Lo único que guardamos en tu navegador</h2>
<div class="table-wrap"><table>
<thead><tr><th scope="col">Nombre</th><th scope="col">Dónde</th><th scope="col">Para qué</th><th scope="col">Cuánto dura</th><th scope="col">¿Se envía a Yumori?</th></tr></thead>
<tbody><tr><td><code>yumori:fav</code></td><td>Almacenamiento local del navegador</td><td>Recordar los productos que marcas como favoritos</td><td>Hasta que lo borres</td><td>No</td></tr>
<tr><td><code>yumori:consent</code></td><td>Almacenamiento local del navegador</td><td>Recordar si aceptaste o rechazaste la analítica</td><td>Hasta que lo borres</td><td>No</td></tr></tbody>
</table></div>
<p>Solo guarda los identificadores de los productos que tú marcas. Puedes quitar cada favorito con el mismo botón o borrar los datos del sitio desde la configuración de tu navegador.</p>
<h2>Cookies de analítica (Google Analytics)</h2>
<p>Al entrar por primera vez te preguntamos si aceptas la analítica; «Rechazar» pesa lo mismo que «Aceptar», y no se carga nada de Google hasta que aceptes. Si aceptas, Google Analytics guarda cookies que empiezan con <code>_ga</code> (hasta 2 años) para distinguir visitas y medir el uso del sitio. Puedes cambiar tu elección cuando quieras con «Preferencias de cookies», al pie de la página; al rechazar, borramos esas cookies.</p>
<h2>Cookies de terceros</h2>
<p>Las imágenes de productos vienen de los servidores de las tiendas. Yumori no controla si esos servidores usan cookies propias. Más detalle en la <a class="link" href="/privacidad">política de privacidad</a>.</p>
""")


def terms():
    return wrap("Términos y condiciones", f"""
<h2>1. Qué es Yumori</h2>
<p>Yumori es un comparador de precios informativo. <strong>No vende productos, no recibe pagos ni intermedia compras.</strong> Cuando decides comprar, lo haces directamente en la tienda a la que te lleva el enlace «Ver en tienda».</p>
<h2>2. Precios e información</h2>
<ul>
<li>Los precios, el stock y los descuentos se obtienen automáticamente de las páginas públicas de las tiendas y se muestran según la <strong>última revisión</strong> (la fecha aparece al pie de cada página). Pueden cambiar en cualquier momento y contener errores o desfases.</li>
<li>«Mejor precio» significa el precio más bajo entre las tiendas revisadas con stock al momento de la última revisión. No incluye despacho ni otros costos, y no significa que sea el más bajo del mercado.</li>
<li><strong>Confirma siempre el precio, el stock y las condiciones en la tienda</strong> antes de comprar. Si hay diferencias, vale lo que indique la tienda.</li>
<li>Los precios «Desde el extranjero» son <strong>estimaciones</strong>: el precio en dólares convertido al dólar observado del día más 19% de IVA. No incluyen el envío internacional ni otros posibles cobros (por ejemplo del courier), que pueden cambiar el total.</li>
</ul>
<h2>3. Valoraciones</h2>
<p>Las notas y la cantidad de reseñas provienen de las propias tiendas y de sus compradores. Yumori no las crea, no las modifica ni verifica su autenticidad. Se muestran para orientar, no como una recomendación de Yumori.</p>
<h2>4. Descripciones de productos</h2>
<p>Son resúmenes elaborados por Yumori a partir de lo que informan las tiendas. Pueden estar incompletos o contener errores, y <strong>no son consejo médico ni dermatológico</strong>. Revisa la lista completa de ingredientes en la tienda y en el envase, y consulta a un profesional si tienes alergias, condiciones de la piel o dudas.</p>
<h2>5. Compras, despachos, devoluciones y garantías</h2>
<p>Yumori no cobra ni recibe pagos, por lo que no gestiona reembolsos, devoluciones, cambios ni garantías. Eso lo resuelve la tienda donde compres, según sus condiciones y la ley (por ejemplo, la Ley 19.496 sobre Protección de los Derechos de los Consumidores, que en ciertos casos reconoce un derecho de retracto en compras a distancia). Lee las condiciones de la tienda antes de comprar. Las compras al extranjero pueden estar afectas a IVA y otros cobros de importación.</p>
<h2>6. Enlaces y sitios de terceros</h2>
<p>Yumori enlaza a tiendas y a otros sitios que no controla ni respalda. No somos responsables de su contenido, sus productos ni sus prácticas. A la fecha, Yumori <strong>no recibe comisiones ni pagos</strong> de las tiendas por los enlaces. Si eso cambia, lo indicaremos de forma visible.</p>
<h2>7. Propiedad intelectual, marcas e imágenes</h2>
<p>Los nombres de tiendas, marcas y productos pertenecen a sus dueños y se usan solo para identificarlos. Las imágenes de productos pertenecen a sus titulares y se muestran desde los servidores de las tiendas; Yumori no las almacena. Los textos de descripción son elaboración propia.</p>
<p><strong>Retiro de contenido:</strong> si eres titular de derechos sobre una imagen, marca o contenido y quieres que lo retiremos o lo corrijamos, escríbenos a {mail_link()} indicando el enlace. Lo revisaremos con prontitud.</p>
<h2>8. Uso del sitio</h2>
<p>Puedes usar Yumori libremente para informarte, siempre de forma lícita y sin afectar su funcionamiento.</p>
<h2>9. Sin garantías y límite de responsabilidad</h2>
<p>El sitio se entrega «tal como está», sin garantía de que la información sea exacta, completa o esté siempre disponible. En la medida que la ley lo permita, Yumori no responde por pérdidas derivadas de decisiones de compra tomadas con esta información, sin perjuicio de los derechos irrenunciables que la ley reconoce a las personas consumidoras.</p>
<h2>10. Cambios</h2>
<p>Podemos actualizar estos términos. La fecha de la última actualización aparece arriba.</p>
<h2>11. Ley aplicable</h2>
<p>Estos términos se rigen por las leyes de la República de Chile. Cualquier diferencia se someterá a los tribunales competentes de Chile, sin perjuicio de los derechos que la Ley 19.496 reconoce a las personas consumidoras.</p>
<h2>12. Contacto y titular</h2>
{contact_block()}
""")
