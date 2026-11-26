import { ApiError, site, safeUrl, money, Store, ChileStore } from '../../lib/api';
import { CatalogMetadata, Failure } from '../components';
export const metadata = { title: 'Tiendas', description: 'Las tiendas chilenas e internacionales cuyos precios de belleza asiática y dermocosmética comparamos.', alternates: { canonical: '/tiendas' } };
const count = (value: number) => new Intl.NumberFormat('es-CL').format(value);
const date = (value: string) => { const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value); return match ? new Intl.DateTimeFormat('es-CL', {day:'numeric', month:'short', year:'numeric', timeZone:'America/Santiago'}).format(new Date(`${match[1]}-${match[2]}-${match[3]}T12:00:00-03:00`)) : value; };
type Named = Pick<Store, 'name' | 'stale_since'>;
const stale = (store: Named) => store.stale_since && <span className="muted small">Sin conexión desde el {date(store.stale_since)}: mostramos el último precio que vimos, sin contarlo como mejor precio.</span>;
const head = (store: Named, international = false) => <span className="store-card-head"><b>{store.name}</b>{store.stale_since && <span className="tag tag-off">Sin conexión</span>}{international && <span className="tag tag-est">Internacional</span>}</span>;
function shippingText(shipping: Store['shipping']) {
  if (!shipping) return '';
  const parts = [shipping.desde ? `desde ${money({amount: shipping.desde, currency:'CLP', decimals:0})}` : '', shipping.gratis ? `gratis sobre ${money({amount: shipping.gratis, currency:'CLP', decimals:0})}${shipping.donde ? ` en ${shipping.donde}` : ''}` : ''].filter(Boolean);
  return [parts.length ? `Despacho ${parts.join(' · ')}` : shipping.nota ? '' : 'Despacho no informado', shipping.nota].filter(Boolean).join(' · ');
}
const LINE = { asiatica: { label: 'de belleza asiática', path: '/explorar', className: 't-rose' }, dermocosmetica: { label: 'de dermocosmética', path: '/dermocosmetica', className: 't-sage' } };
// Una tarjeta por tienda chilena con una franja por sección en la que vende; una franja en 0 se omite si la tienda tiene la otra (EcoFarmacias no vende belleza asiática).
function StoreCard({ store }: { store: ChileStore }) {
  const lines = (['asiatica', 'dermocosmetica'] as const).filter(section => section in store.counts).map(section => ({ section, count: store.counts[section] ?? 0 }));
  const shown = lines.filter(line => line.count > 0);
  const text = shippingText(store.shipping);
  const visible = shown.length ? shown : lines.slice(0, 1);
  const href = (section: keyof typeof LINE) => `${LINE[section].path}?tienda=${encodeURIComponent(store.domain)}`;
  const main = visible.reduce((a, b) => (b.count > a.count ? b : a)).section; // "Ver catálogo" lleva a la sección donde la tienda tiene más productos
  const site = safeUrl(store.url);
  return <article className="store-card store-card-wide" data-store-domain={store.domain}>{head(store)}
    <span className="store-lines">{visible.map(line => <a key={line.section} className={`store-line ${LINE[line.section].className}`} href={href(line.section)}><b>{count(line.count)}</b> productos {LINE[line.section].label} con stock</a>)}</span>
    {text && <span className="muted small">{text}</span>}{stale(store)}
    <span className="store-actions"><a className="btn btn-primary btn-sm" href={href(main)}>Ver catálogo</a>{site && <a className="btn btn-ghost btn-sm" href={site} target="_blank" rel="noopener nofollow" aria-label={`Ir al sitio de ${store.name} (se abre en otra pestaña)`}>Ir a la tienda</a>}</span></article>;
}
// Mismo formato que la chilena, sin "Ver catálogo": Explorar no filtra por tienda extranjera (Catalog._match solo mira las ofertas chilenas).
function IntlCard({ store }: { store: Store }) {
  const site = safeUrl(store.url);
  return <article className="store-card store-card-wide" data-store-domain={store.domain}>{head(store, true)}
    <span className="store-lines"><span className="store-line t-lav"><b>{count(store.count)}</b> productos en Yumori · <b>{count(store.matched_in_chile || 0)}</b> también en Chile</span></span>{stale(store)}
    {site && <span className="store-actions"><a className="btn btn-primary btn-sm" href={site} target="_blank" rel="noopener nofollow" aria-label={`Ir al sitio de ${store.name} (se abre en otra pestaña)`}>Ir a la tienda</a></span>}</article>;
}
export default async function Page() {
  let data; try { data = await site(); } catch (error) { if (error instanceof ApiError) return <Failure message={error.message} />; throw error; }
  const chile = data.stores.chile;
  return <div className="container"><div className="page-head"><h1>Tiendas</h1><p className="muted">Comparamos {chile.length} tiendas chilenas y {data.stores.international.length} internacionales</p></div><p className="muted small">Las condiciones de despacho las revisamos en el sitio de cada tienda el {date(data.shipping_reviewed)} y pueden cambiar. No se suman a los precios. La dermocosmética (marcas de farmacia, como Eucerin o La Roche-Posay) se compara aparte de la belleza asiática.</p>
    <div className="store-list store-list-wide">{chile.map(store => <StoreCard key={store.domain} store={store} />)}</div>
    {data.stores.international.length > 0 && <section className="section"><div className="section-head"><div><h2>Tiendas internacionales</h2><p className="muted small">Envían a Chile. Sus precios se muestran en pesos, estimados con el dólar del día y 19% de IVA, sin envío. Cuando el mismo producto también lo vende una tienda chilena, se compara directamente en su ficha. "Ir a la tienda" lleva directo a su sitio.</p></div></div><div className="store-list store-list-wide">{data.stores.international.map(store => <IntlCard key={store.domain} store={store} />)}</div></section>}
    <CatalogMetadata data={data} />
  </div>;
}
