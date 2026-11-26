import Explorer from '../explorer';
import { Query } from '../../lib/api';
import { listingMeta } from '../../lib/seo';
export const generateMetadata = listingMeta('Dermocosmética en Chile: precios', 'Dermocosmética en farmacias y tiendas de Chile: compara precios de marcas como Eucerin, La Roche-Posay o CeraVe.', '/dermocosmetica', 'dermocosmética');
export default function Page({ searchParams }: { searchParams: Promise<Query> }) { return <Explorer searchParams={searchParams} base='/dermocosmetica' title='Dermocosmética' forced={{seccion: 'dermocosmetica', packs: '0'}} />; }
