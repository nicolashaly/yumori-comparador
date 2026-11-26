import Explorer from '../explorer';
import { Query } from '../../lib/api';
import { listingMeta } from '../../lib/seo';
export const generateMetadata = listingMeta('Explorar productos de belleza asiática', 'Explora productos de belleza coreana, japonesa y china y compara sus precios en tiendas de Chile.', '/explorar');
export default function Page({ searchParams }: { searchParams: Promise<Query> }) { return <Explorer searchParams={searchParams} forced={{seccion: 'asiatica', packs: '0'}} />; }
