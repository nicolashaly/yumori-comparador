import Explorer from '../explorer';
import { ApiError, Query, site } from '../../lib/api';
import { Failure } from '../components';
import { listingMeta } from '../../lib/seo';
export const generateMetadata = listingMeta('Black Friday: rebajas reales en belleza', 'Black Friday: productos de belleza que bajaron de precio en tiendas de Chile, medido contra el historial de precios de Yumori.', '/black-friday', 'Black Friday');
export default async function Page({ searchParams }: { searchParams: Promise<Query> }) {
  let data; try { data = await site(); } catch (error) { if (error instanceof ApiError) return <Failure message={error.message} />; throw error; }
  const event = data.events.find(e => e.slug === 'black-friday');
  return <Explorer searchParams={searchParams} base='/black-friday' title={event ? event.name + "" : 'black-friday'} forced={{evento: 'black-friday', seccion: 'todas', packs: '0'}} intro={<p>Rebajas detectadas en nuestro historial durante el evento. No implica participación oficial de Yumori. {event && `${event.start} al ${event.end} · Chile`}{event?.early && ` · Contamos rebajas desde ${event.early}`}</p>} />;
}
