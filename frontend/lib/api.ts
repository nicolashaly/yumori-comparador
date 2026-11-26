export type Money = { amount: number; currency: 'CLP' | 'USD'; decimals: number };
export type Metadata = { version: 1; catalog_last_update: string | null; exchange_rate: { usd_clp: number | null; date: string | null }; estimate_includes_vat: boolean; estimate_includes_shipping: boolean };
export type Product = {
  id: string; name: string; brand: string; brand_slug: string; section: string; size: string; variant: string; is_pack: boolean; mini: boolean;
  card_prefix: string; card_store_label: string; card_meta: string; has_deal: boolean; image_alternatives: string[]; drop_percent: number; drop_reference_price: Money | null;
  image: string | null; display_price: Money | null; display_is_estimate: boolean;
  display_price_confirmed: boolean; best_store_ids: string[];
  domestic_store_count: number; international_store_count: number;
  rating: { value: number; reviews: number; store: string } | null;
};
export type Shipping = { desde: number | null; gratis: number | null; donde: string; nota?: string; fuente: string | null; reviewed: string };
export type Offer = { store: string; store_name: string; url: string | null; price: Money; status: string; status_label: string; estimate?: Money | null; stale_since: string | null; missing_since: string | null; suspect_reason: string | null; shipping?: Shipping | null; rating?: number | null; reviews?: number | null; drop_percent?: number; reference_price?: Money | null; price_since_day?: string | null };
export type Detail = Product & { primary_offer_store_ids: string[]; category: string; category_label: string; small_format: boolean; pack_size_warning: boolean; search_elsewhere: { name: string; url: string | null }[]; price_spread_warning: boolean; images: string[]; related: Product[]; shipping_reviewed: string; description: { text: string; skin: string[] } | null; description_disclaimer: string; domestic_offers: Offer[]; international_offers: Offer[]; card_offers: { store: string; store_name: string; card_name: string; price: Money; normal_price: Money; url: string | null }[]; contents: { name: string; size: string; product_id: string | null; product: Product | null }[]; includes: { product_id: string; quantity: number; pack_size: string | null; product: Product | null }[]; included_in: { product_id: string; quantity: number; product: Product | null }[] };
export type Brand = { slug: string; name: string; count: number };
export type Store = { domain: string; name: string; count: number; matched_in_chile?: number; stale_since: string | null; url: string | null; shipping: Shipping | null };
export type ChileStore = Omit<Store, 'count' | 'matched_in_chile'> & { counts: Partial<Record<'asiatica' | 'dermocosmetica', number>> };
export type Event = { slug: string; name: string; start: string; end: string; early?: string; theme: string };
export type LegalInline = { text: string } | { tag: 'strong' | 'em' | 'code' | 'a' | 'span'; href?: string; children: LegalInline[] };
export type LegalDocument = { title: string; updated: string; blocks: { tag: string; text: string; inline?: LegalInline[] }[] };
export type SiteResponse = Metadata & {
  categories: { slug: string; name: string; count: number }[];
  home: { live_event_summary: { product_count: number; store_count: number } | null; product_count: number; store_count: number; section_counts: Record<string, number>; top_brands: Brand[]; spread: Product[]; drops: Product[]; deals: Product[]; deals_total: number; deal_days: number; deal_show_percent: number };
  brands: { asiatica: Brand[]; dermocosmetica: Brand[] };
  stores: { asiatica: Store[]; dermocosmetica: Store[]; chile: ChileStore[]; international: Store[] };
  events: Event[]; live_event: Event | null; shipping_reviewed: string;
  legal: Record<string, LegalDocument>; operator_missing_fields: string[];
};
export type FavoritesResponse = Metadata & { items: Product[]; resolutions: Record<string, string | null>; missing_ids: string[] };
export type SuggestionsResponse = Metadata & { query: string; items: Product[]; sections: { section: string; total: number; path: string }[] };
export type HistoryResponse = Metadata & { requested_id: string; canonical_id: string; page: number; limit: number; stores: { store: string; total: number; observations: { captured_at: string; price: Money; available: boolean }[] }[] };
export type Listing = Metadata & { category_counts: Record<string, number>; related_counts: { packs: number; other_section: number }; section_product_count: number; items: Product[]; total: number; page: number; pages: number; page_size: number; facets: Record<string, Record<string, number>> };
export type ProductResponse = Metadata & { product: Detail; requested_id: string; canonical_id: string };
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export type Query = Record<string, string | string[] | undefined>;
export function queryString(query: Query) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    for (const entry of Array.isArray(value) ? value : value === undefined ? [] : [value]) params.append(key, entry);
  }
  return params.toString();
}
export { safeUrl, money } from './display';
async function read<T>(path: string): Promise<T> {
  const origin = new URL(process.env.YUMORI_API_ORIGIN || 'http://127.0.0.1:8000');
  if (origin.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname) || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) throw new ApiError(503, 'Configuración de API local inválida');
  let response: Response;
  try { response = await fetch(new URL(`/api/v1/${path}`, origin), { cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10000) }); }
  catch { throw new ApiError(503, 'Sin conexión con el catálogo. Intenta nuevamente.'); }
  if (!response.ok) {
    if (response.status === 400) throw new ApiError(400, 'Filtros inválidos. Revisa los parámetros de búsqueda.');
    if (response.status === 404) throw new ApiError(404, 'Producto no encontrado');
    throw new ApiError(503, 'El catálogo no está disponible. Intenta nuevamente.');
  }
  let data;
  try { data = await response.json(); } catch { throw new ApiError(503, 'Respuesta del catálogo inválida'); }
  if (data.version !== 1) throw new ApiError(503, 'Versión del catálogo incompatible');
  return data as T;
}
export const products = (query: Query) => read<Listing>(`products?${queryString(query)}`);
export const product = (id: string) => read<ProductResponse>(`products/${encodeURIComponent(id)}`);
export const sitemapProducts = () => read<Metadata & { products: { id: string; lastmod: string | null }[] }>('sitemap');
export const site = () => read<SiteResponse>('site');
export const favorites = (ids: string[]) => read<FavoritesResponse>(`favorites?${queryString({ ids: ids.join(',') })}`);
export const suggestions = (q: string) => read<SuggestionsResponse>(`suggestions?${queryString({ q })}`);
export const history = (id: string, page: number) => read<HistoryResponse>(`products/${encodeURIComponent(id)}/history?pagina=${page}&limite=1000`);
