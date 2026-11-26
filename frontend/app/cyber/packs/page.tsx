import Explorer from '../../explorer';
import { ApiError, Query, site } from '../../../lib/api';
import { Failure } from '../../components';
import { listingMeta } from '../../../lib/seo';
export const generateMetadata = listingMeta('Cyber: packs con rebaja', 'Cyber: packs de belleza que bajaron de precio en tiendas de Chile, medido contra el historial de precios de Yumori.', '/cyber/packs', 'packs de Cyber');
export default async function Page({ searchParams }: { searchParams: Promise<Query> }) {
  let data; try { data = await site(); } catch (error) { if (error instanceof ApiError) return <Failure message={error.message} />; throw error; }
  const event = data.events.find(e => e.slug === 'cyber');
  return <Explorer searchParams={searchParams} base='/cyber/packs' title={event ? event.name + ": packs" : 'cyber'} forced={{evento: 'cyber', seccion: 'todas', packs: '1'}} intro={<p>Rebajas detectadas en nuestro historial durante el evento. No implica participación oficial de Yumori. {event && `${event.start} al ${event.end} · Chile`}{event?.early && ` · Contamos rebajas desde ${event.early}`}</p>} />;
}
