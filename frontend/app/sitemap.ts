import type { MetadataRoute } from 'next';
import { sitemapProducts, site } from '../lib/api';
import { INDEXABLE, abs } from '../lib/seo';
import { LEGAL_VISIBLE } from './legal-page';
export const dynamic = 'force-dynamic';

// Las páginas indexables: listados, marcas, categorías, legales, eventos vigentes y los productos que alguna tienda chilena aún
// lista, con el día de su último cambio de precio o stock (ver api.sitemap_products).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  if (!INDEXABLE) return [];
  const [data, map] = await Promise.all([site(), sitemapProducts()]).catch(() => [null, null] as const);
  if (!data || !map) return [];
  const q = (base: string, key: string, value: string) => `${base}?${new URLSearchParams({ [key]: value })}`;
  const derm = data.home.section_counts.dermocosmetica > 0;
  const paths = ['/', '/explorar', '/packs', '/marcas', '/tiendas', '/bot', ...(LEGAL_VISIBLE ? Object.keys(data.legal).map(slug => `/${slug}`) : []),
    ...(data.live_event ? [`/${data.live_event.slug}`] : []),
    ...data.categories.filter(c => c.count).map(c => q('/explorar', 'cat', c.slug)),
    ...data.brands.asiatica.filter(b => b.slug !== 'sin-marca').map(b => q('/explorar', 'marca', b.slug)),
    ...(derm ? ['/dermocosmetica', ...data.brands.dermocosmetica.filter(b => b.slug !== 'sin-marca').map(b => q('/dermocosmetica', 'marca', b.slug))] : [])];
  return [...paths.map(url => ({ url: abs(url) })), ...map.products.map(p => ({ url: abs(`/p/${p.id}`), ...(p.lastmod && { lastModified: p.lastmod }) }))];
}
