import Explorer from '../explorer';
import { Query } from '../../lib/api';
import { listingMeta } from '../../lib/seo';
export const generateMetadata = listingMeta('Packs y sets de belleza asiática', 'Sets, kits, duos y packs de belleza asiática: compara precios entre tiendas de Chile.', '/packs', 'packs y sets');
export default function Page({ searchParams }: { searchParams: Promise<Query> }) { return <Explorer searchParams={searchParams} base='/packs' title='Packs' forced={{packs: '1', seccion: 'asiatica'}} />; }
