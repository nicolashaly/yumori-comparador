import Explorer from '../../explorer';
import { Query } from '../../../lib/api';
import { listingMeta } from '../../../lib/seo';
export const generateMetadata = listingMeta('Packs de dermocosmética', 'Sets, kits y packs de dermocosmética: compara precios en farmacias y tiendas de Chile.', '/dermocosmetica/packs', 'packs de dermocosmética');
export default function Page({ searchParams }: { searchParams: Promise<Query> }) { return <Explorer searchParams={searchParams} base='/dermocosmetica/packs' title='Packs de dermocosmética' forced={{packs: '1', seccion: 'dermocosmetica'}} />; }
