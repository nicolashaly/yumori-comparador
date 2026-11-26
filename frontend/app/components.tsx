import { type Metadata, type Money, type Product, money } from '../lib/api';

export function Price({ value, display = false }: { value: Money | null; display?: boolean }) {
  return <span data-display-price={display ? '' : undefined} data-price-amount={value?.amount} data-currency={value?.currency}>{money(value)}</span>;
}
export function ProductPrice({ p }: { p: Product }) {
  return <p className="price"><Price value={p.display_price} display />{p.display_is_estimate && <small>Estimado · incluye IVA, excluye envío</small>}{!p.display_price_confirmed && p.display_price && <small>Precio por confirmar</small>}</p>;
}
export function CatalogMetadata({ data }: { data: Metadata }) {
  return <aside className="metadata"><p>Última actualización del catálogo: {data.catalog_last_update ? <time dateTime={data.catalog_last_update}>{new Intl.DateTimeFormat('es-CL', {dateStyle:'medium',timeStyle:'short',timeZone:'America/Santiago'}).format(new Date(data.catalog_last_update))}</time> : 'Sin fecha confirmada'}</p><p>Referencia USD/CLP: {data.exchange_rate.usd_clp ?? 'Sin tasa disponible'} · {data.exchange_rate.date ? <time dateTime={data.exchange_rate.date}>{data.exchange_rate.date}</time> : 'Sin fecha confirmada'}. Estimaciones con IVA, sin envío.</p></aside>;
}
export { default as Card } from './product-card';
export function Failure({ message }: { message: string }) { return <section className="container empty" role="alert"><h1>No se pudo cargar el catálogo</h1><p>{message}</p><a href="/explorar">Volver a explorar</a></section>; }
