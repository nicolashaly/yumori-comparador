// Página para las tiendas y para el registro de Web Bot Auth en Shopify (ADR-010); el User-Agent de scrapers/http.py la enlaza.
// Las cifras deben seguir a scrapers/http.py (DELAY) y ratings.py (DELAY, JUDGEME).
const CONTACT = 'contacto@yumori.cl';
export const metadata = { title: 'YumoriBot', description: 'Qué es YumoriBot, el lector de precios de Yumori, qué pide a las tiendas y cómo pedir que no lea tu tienda.', alternates: { canonical: '/bot' } };
export default function Page() {
  const mail = <a className="link" href={`mailto:${CONTACT}`}>{CONTACT}</a>;
  return <article className="container legal">
    <div className="page-head"><h1>YumoriBot</h1><p className="muted">El programa que lee los precios que muestra Yumori</p></div>
    <p>Si ves <code>YumoriBot/0.1 (+https://yumori.cl/bot)</code> en los registros de tu tienda, somos nosotros. Yumori compara precios de cosmética asiática y dermocosmética en tiendas chilenas. Es un proyecto personal, sin publicidad ni venta de datos.</p>
    <h2>Qué lee</h2>
    <ul>
      <li>Una vez al día, el catálogo público de cada tienda: nombre, variantes, precio, precio antes del descuento, stock e imágenes. En Shopify es <code>/products.json</code>, entre 1 y 7 peticiones por tienda al día.</li>
      <li>Una vez por semana, en cuatro tiendas Shopify que usan Judge.me, la ficha de cada producto, para leer la nota de las reseñas y el código de barras.</li>
    </ul>
    <h2>Cómo lo lee</h2>
    <ul>
      <li>Al menos 10 segundos entre peticiones a una misma tienda en la lectura diaria, y 5 segundos en la semanal. Nunca hay peticiones en paralelo a una misma tienda.</li>
      <li>Revisamos el robots.txt antes de agregar una tienda y solo pedimos rutas permitidas. Si fija un <code>Crawl-delay</code> mayor, lo respetamos.</li>
      <li>Ante un error 403 o 429 dejamos de pedir a esa tienda, sin reintentar ni cambiar de identidad.</li>
      <li>En Shopify firmamos las peticiones con Web Bot Auth. Nuestras claves públicas están en <a className="link" href="/.well-known/http-message-signatures-directory">/.well-known/http-message-signatures-directory</a>.</li>
      <li>Leemos desde una sola conexión residencial en Chile.</li>
    </ul>
    <h2>Qué hacemos con los datos</h2>
    <p>Mostramos el precio actual, su historial y un enlace a la ficha del producto en tu tienda. Las imágenes se muestran desde tu propio sitio. No vendemos ni compartimos los datos.</p>
    <h2>Si no quieres que leamos tu tienda</h2>
    <p>Escríbenos a {mail} o bloquea <code>YumoriBot</code> en tu robots.txt. Dejamos de leerla y la quitamos del sitio.</p>
    <h2>In English</h2>
    <p>YumoriBot reads public product catalogs (on Shopify, <code>/products.json</code>) of Chilean beauty stores once a day, and product pages of four stores once a week, to show price comparisons and price history on yumori.cl. It waits at least 10 seconds between requests to the same store (5 seconds on the weekly pass), honors robots.txt, stops on any 403 or 429, and signs Shopify requests with Web Bot Auth (keys at <code>/.well-known/http-message-signatures-directory</code>). To opt out, email {mail} or disallow <code>YumoriBot</code> in robots.txt.</p>
  </article>;
}
