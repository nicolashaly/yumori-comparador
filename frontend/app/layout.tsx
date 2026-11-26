import type { Metadata } from 'next';
import './original.css';
import './style.css';
import SiteHeader from './site-header';
import { site } from '../lib/api';
import { LEGAL_VISIBLE } from './legal-page';
export const dynamic = 'force-dynamic';
import { INDEXABLE, SITE_DESC, SITE_URL } from '../lib/seo';
import Analytics from './analytics';
const verification = process.env.GOOGLE_SITE_VERIFICATION;
const gaId = process.env.GA_MEASUREMENT_ID;  // vacío = sin analítica (piloto y desarrollo)
export const metadata: Metadata = {
  ...(INDEXABLE && { metadataBase: new URL(SITE_URL) }),
  title: { default: INDEXABLE ? 'Yumori · Compara precios de skincare y belleza en Chile' : 'Yumori · Piloto', template: '%s · Yumori' },
  description: SITE_DESC,
  robots: INDEXABLE ? { index: true, follow: true } : { index: false, follow: false },
  openGraph: { siteName: 'Yumori', locale: 'es_CL', type: 'website' },
  twitter: { card: 'summary' },
  ...(verification && { verification: { google: verification } }),
};
export default async function Layout({ children }: { children: React.ReactNode }) {
  const data = await site().catch(() => null);
  const stamp = data?.catalog_last_update;
  return <html lang="es"><body><div className="sakura" aria-hidden="true" /><a className="skip" href="#main">Saltar al contenido</a><SiteHeader data={data} /><main id="main" tabIndex={-1}>{children}</main><footer><div className="container"><p>Yumori compara precios de tiendas chilenas y del extranjero; no vende productos. {stamp && <>Precios revisados por última vez el <time dateTime={stamp}>{new Intl.DateTimeFormat('es-CL', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Santiago' }).format(new Date(stamp))}</time>. </>}Confirma siempre el precio y el stock en la tienda antes de comprar.</p>{LEGAL_VISIBLE && <nav className="legal-links" aria-label="Información legal"><a href="/privacidad">Privacidad</a><a href="/terminos">Términos</a><a href="/cookies">Cookies</a></nav>}{gaId && <Analytics id={gaId} legal={LEGAL_VISIBLE} />}</div></footer></body></html>;
}
