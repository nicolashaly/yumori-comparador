import Explorer from '../explorer';
import { ApiError, Query, site } from '../../lib/api';
import { Failure } from '../components';
import { listingMeta } from '../../lib/seo';
export const generateMetadata = listingMeta('Cyber: rebajas reales en belleza', 'Cyber: productos de belleza que bajaron de precio en tiendas de Chile, medido contra el historial de precios de Yumori.', '/cyber', 'Cyber');
export default async function Page({ searchParams }: { searchParams: Promise<Query> }) {
  let data; try { data = await site(); } catch (error) { if (error instanceof ApiError) return <Failure message={error.message} />; throw error; }
  const event = data.events.find(e => e.slug === 'cyber');
  return <Explorer searchParams={searchParams} base='/cyber' title={event ? event.name + "" : 'cyber'} forced={{evento: 'cyber', seccion: 'todas', packs: '0'}} intro={<p>Rebajas detectadas en nuestro historial durante el evento. No implica participación oficial de Yumori. {event && `${event.start} al ${event.end} · Chile`}{event?.early && ` · Contamos rebajas desde ${event.early}`}</p>} />;
}
