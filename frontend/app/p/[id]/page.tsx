import { notFound, permanentRedirect } from 'next/navigation';
import { ApiError, Detail, Offer, product, safeUrl } from '../../../lib/api';
import { Card, CatalogMetadata, Failure, Price } from '../../components';
import { FavoriteButton } from '../../favorites-client';
import ProductHistory from '../../product-history';
import ProductGallery from '../../product-gallery';
import { abs, clip, jsonLd } from '../../../lib/seo';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const data = await product(id);
    const p = data.product, name = fullName(p), stock = inStock(p);
    const lead = stock.length
      ? `${stock.length > 1 ? 'desde ' : ''}${clp(Math.min(...stock.map(o => o.price.amount)))} en ${stock.length} tienda${stock.length > 1 ? 's' : ''} de Chile con stock`
      : p.domestic_offers.length ? `sin stock por ahora en ${p.domestic_offers.length} tienda${p.domestic_offers.length > 1 ? 's' : ''} de Chile`
      : p.display_price ? `≈ ${clp(p.display_price.amount)} estimado desde el extranjero, con IVA y sin envío` : 'disponible en una tienda del extranjero';
    const description = `${name}: ${lead}. Compara precios, stock e historial antes de comprar.`;
    const title = `${name}: precio en Chile`, canonical = `/p/${data.canonical_id}`, image = safeUrl(p.image);
    return {
      title, description: clip(description), alternates: { canonical },
      openGraph: { title, description: clip(description, 200), url: canonical, type: 'website', ...(image && { images: [image] }) },
      twitter: { card: image ? 'summary_large_image' : 'summary' },
    };
  } catch { return { title: 'Producto' }; }
}

const clp = (amount: number) => `$${new Intl.NumberFormat('es-CL').format(amount)}`;
// Nombre único para títulos y buscadores: marca, nombre, variante y tamaño.
const fullName = (p: { brand: string; name: string; variant: string; size: string }) => [p.brand, p.name, p.variant, p.size].filter(Boolean).join(' ');
// Solo tiendas chilenas con stock confirmado: nunca la estimación del extranjero ni una oferta sin conexión.
const inStock = (p: { domestic_offers: Offer[] }) => p.domestic_offers.filter(o => o.status === 'available');

// Sin aggregateRating a propósito: las notas son de las tiendas y Google no admite reseñas tomadas de otros sitios.
// Sin stock confirmado en Chile no hay `offers` honestas, y un Product sin offers/review/aggregateRating es un error
// crítico para Google: en ese caso solo va el BreadcrumbList.
function structuredData(p: Detail, id: string, categoryPath: string, brandPath: string) {
  const stock = inStock(p), prices = stock.map(o => o.price.amount);
  const product = {
    '@context': 'https://schema.org', '@type': 'Product', name: fullName(p), url: abs(`/p/${id}`),
    ...(p.brand_slug !== 'sin-marca' && { brand: { '@type': 'Brand', name: p.brand } }),
    ...(p.images.length && { image: p.images }),
    ...(p.description?.text && { description: p.description.text }),
    offers: { '@type': 'AggregateOffer', priceCurrency: 'CLP', lowPrice: Math.min(...prices), highPrice: Math.max(...prices), offerCount: stock.length, availability: 'https://schema.org/InStock' },
  };
  const crumbs: [string, string][] = [['Inicio', '/'], ...(p.section === 'dermocosmetica' ? [['Dermocosmética', '/dermocosmetica'] as [string, string]] : []),
    ...(p.category ? [[p.category_label, categoryPath] as [string, string]] : []), ...(p.brand_slug !== 'sin-marca' ? [[p.brand, brandPath] as [string, string]] : []), [p.name, `/p/${id}`]];
  const trail = { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: crumbs.map(([name, path], i) => ({ '@type': 'ListItem', position: i + 1, name, item: abs(path) })) };
  return stock.length ? [product, trail] : [trail];
}

function Offers({ offers, best, name, international = false }: {
  offers: Offer[]; best: string[]; name: string; international?: boolean;
}) {
  return <div className="offers" data-offers={international ? 'international' : 'domestic'}>
    {offers.map(offer => {
      const url = safeUrl(offer.url);
      const shippingSource = safeUrl(offer.shipping?.fuente || null);
      const confirmedBest = best.includes(offer.store);
      return <div key={offer.store} className={`offer${confirmedBest ? ' best-offer' : offer.status !== 'available' ? ' out' : ''}`}
        data-store-id={offer.store} data-offer-status={offer.status}>
        <div className="offer-main">
          <div className="offer-store">{offer.store_name}</div>
          <div className="offer-sub">
            {confirmedBest && <span className="tag tag-best">Mejor precio confirmado</span>}
            <span className={offer.status !== 'available' ? 'tag tag-off' : 'status-ok'}>{offer.status_label}</span>
            {offer.stale_since && <span>Desde {offer.stale_since}</span>}
            {offer.missing_since && <span>Desde {offer.missing_since}</span>}
            {offer.suspect_reason && <span>{offer.suspect_reason}</span>}
            {international && <span className="tag tag-est">Estimado</span>}
          </div>
          <div className="offer-meta">
            {offer.rating != null && offer.reviews != null && offer.reviews > 0 &&
              <span><span aria-hidden="true">★</span><span className="sr-only">Valoración </span> {offer.rating} · {offer.reviews} {offer.reviews === 1 ? 'reseña' : 'reseñas'}</span>}
            {international && <span><Price value={offer.price} /> + IVA 19%, sin envío</span>}
            {!international && (offer.shipping ? <span>
              <b>Despacho</b> {offer.shipping.desde == null ? 'sin monto confirmado' : <>desde <Price value={{ amount: offer.shipping.desde, currency: 'CLP', decimals: 0 }} /></>}
              {offer.shipping.gratis != null && <> · gratis desde <Price value={{ amount: offer.shipping.gratis, currency: 'CLP', decimals: 0 }} /></>}
              {offer.shipping.donde && <> · {offer.shipping.donde}</>}{offer.shipping.nota && <>. {offer.shipping.nota}</>}.
              {shippingSource && <a className="link" href={shippingSource} rel="noopener nofollow"> Condiciones de despacho</a>}
            </span> : <span>Despacho no informado</span>)}
          </div>
        </div>
        <div className="offer-price">
          {international && offer.estimate ? <><span aria-label="Precio estimado">≈ <Price value={offer.estimate} /></span><small>Precio en tienda: <Price value={offer.price} /></small></> : <Price value={offer.price} />}
          {!!offer.drop_percent && offer.reference_price && <small>−{offer.drop_percent}% · Referencia del historial: <s><Price value={offer.reference_price} /></s></small>}
          {offer.price_since_day && <small>Vigente desde {offer.price_since_day}</small>}
        </div>
        {url && <a className={`btn ${confirmedBest ? 'btn-primary' : 'btn-soft'} btn-sm`} href={url} target="_blank" rel="noopener noreferrer nofollow sponsored"
          aria-label={`Ver ${name} en ${offer.store_name} (se abre en otra pestaña)`}>Ver en tienda</a>}
      </div>;
    })}
    {!offers.length && <p className="muted">Sin ofertas en esta sección.</p>}
  </div>;
}

export default async function ProductPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const historyRange = query.rango === 'dia' || query.rango === 'semana' ? query.rango : 'mes';
  if (!/^[0-9a-f]{10}$/.test(id)) notFound();
  let data;
  try { data = await product(id); } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 404) notFound();
      return <Failure message={error.message} />;
    }
    throw error;
  }
  if (data.canonical_id !== id) permanentRedirect(`/p/${data.canonical_id}`);
  const p = data.product;
  const base = p.section === 'dermocosmetica' ? `/dermocosmetica${p.is_pack ? '/packs' : ''}` : p.is_pack ? '/packs' : '/explorar';
  const brandPath = `${base}?marca=${encodeURIComponent(p.brand_slug)}`;
  const categoryPath = `${p.section === 'dermocosmetica' ? '/dermocosmetica' : '/explorar'}?cat=${encodeURIComponent(p.category)}`;
  const bestOffers = p.best_store_ids.map(store => p.domestic_offers.find(offer => offer.store === store)).filter((offer): offer is Offer => !!offer);
  const primaryOffers = p.primary_offer_store_ids.map(store => [...p.domestic_offers, ...p.international_offers].find(offer => offer.store === store)).filter((offer): offer is Offer => !!offer);
  return <article className="container" data-product-id={p.id} data-product-detail="">
    {structuredData(p, data.canonical_id, categoryPath, brandPath).map((d, i) => <script key={i} type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(d) }} />)}
    <nav className="crumbs" aria-label="Ruta"><a href="/">Inicio</a>
      {p.section === 'dermocosmetica' && <> / <a href="/dermocosmetica">Dermocosmética</a></>}
      {p.category && <> / <a href={categoryPath}>{p.category_label}</a></>}{' / '}<a href={brandPath}>{p.brand}</a>
    </nav>
    <div className="product">
      <ProductGallery images={p.images} src={p.image} alternatives={p.image_alternatives} name={`${p.brand} ${p.name}`} />
      <div>
        <p className="eyebrow"><a href={brandPath}>{p.brand}</a></p><h1>{p.name}</h1>
        <p className="muted product-subtitle">{[p.is_pack ? p.small_format ? 'Pack en formato mini' : 'Pack' : '', p.variant, p.size, p.mini ? 'Miniatura' : ''].filter(Boolean).join(' · ')}</p>
        {p.description && <div className="about">
          <p>{p.description.text}</p>
          {!!p.description.skin.length && <p className="for"><span className="muted">Especial para:</span>{p.description.skin.map(skin => <span key={skin} className="chip chip-static">{skin}</span>)}</p>}
          <p className="muted small">{p.description_disclaimer}</p>
        </div>}
        <p className="best"><span className="big"><strong>{p.display_is_estimate && '≈ '}<Price value={p.display_price} display /></strong></span>
          {bestOffers.length > 1 ? `Mismo precio en ${bestOffers.length} tiendas` : bestOffers.length === 1 ? <>Mejor precio confirmado en <strong>{bestOffers[0].store_name}</strong></> : p.display_is_estimate ? 'Estimado · incluye IVA, excluye envío' : 'Sin precio confirmado disponible'}
        </p>
        {!p.display_price_confirmed && p.display_price && <p className="muted small">Precio por confirmar</p>}
        <p className="muted small">{p.domestic_store_count} tiendas chilenas · {p.international_store_count} internacionales</p>
        {p.rating && <p className="muted small">Valoración: {p.rating.value} · {p.rating.reviews} reseñas en {p.rating.store}</p>}
        {p.price_spread_warning && <p className="warn small" role="note">La diferencia entre tiendas es grande: confirma que sea el mismo tamaño y versión antes de comprar.</p>}
        <div className="actions">
          {primaryOffers.map(offer => safeUrl(offer.url) && <a className="btn btn-primary btn-lg" key={offer.store} href={safeUrl(offer.url)} title={offer.status !== 'available' ? offer.status_label : undefined} target="_blank" rel="noopener nofollow sponsored">Ver en {offer.store_name}<span className="sr-only"> (se abre en otra pestaña){offer.status !== 'available' ? ` · ${offer.status_label}` : ''}</span></a>)}
          <FavoriteButton id={p.id} name={p.name} />
        </div>
      </div>
    </div>
    {p.domestic_offers.length > 0 && <section className="section">
      <div className="section-head"><div><h2>Precios por tienda</h2><p className="muted small">Los precios no incluyen despacho. Condiciones revisadas: {p.shipping_reviewed}. Confírmalas al comprar.</p></div></div>
      <Offers offers={p.domestic_offers} best={p.best_store_ids} name={p.name} />
    </section>}
    {p.card_offers.length > 0 && <section className="section section-sub">
      <div className="section-head"><div><h2>Con tarjeta de la tienda</h2><p className="muted">Precios exclusivos con la tarjeta de cada tienda; no cuentan como mejor precio.</p></div></div>
      <div className="offers">{p.card_offers.map((offer, index) => <div className="offer" key={index}>
        <div><div className="offer-store">{offer.store_name}</div><div className="offer-sub"><span className="tag tag-est">Con {offer.card_name}</span></div></div>
        <div className="offer-price"><Price value={offer.price} /><small>Precio normal: <Price value={offer.normal_price} /></small></div>
        {safeUrl(offer.url) && <a className="btn btn-soft btn-sm" href={safeUrl(offer.url)} target="_blank" rel="noopener nofollow sponsored" aria-label={`Ver ${p.name} en ${offer.store_name} con ${offer.card_name} (se abre en otra pestaña)`}>Ver en tienda</a>}
      </div>)}</div>
    </section>}
    {p.search_elsewhere.length > 0 && <section className="section section-sub">
      <div className="section-head"><div><h2>Búscalo también en</h2><p className="muted">Estas tiendas no las revisamos automáticamente, así que no mostramos su precio ni lo comparamos.</p></div></div>
      <p className="search-elsewhere">{p.search_elsewhere.map(shop => safeUrl(shop.url) && <a className="btn btn-soft btn-sm" key={shop.name} href={safeUrl(shop.url)} target="_blank" rel="noopener nofollow">{shop.name}<span className="sr-only"> (búsqueda en otra pestaña)</span></a>)}</p>
    </section>}
    {p.international_offers.length > 0 && <section className="section">
      <div className="section-head"><div><h2>Desde el extranjero</h2><p className="muted">Tiendas fuera de Chile que envían aquí. No entran en el mejor precio de arriba.</p></div></div>
      <Offers offers={p.international_offers} best={[]} name={p.name} international />
      <p className="muted small">La estimación incluye IVA de 19%; no incluye envío internacional ni posibles cobros del courier. Confirma el total en la tienda antes de comprar.</p>
    </section>}
    {p.contents.length > 0 && <section className="section">
      <div className="section-head"><div><h2>Este pack incluye</h2><p className="muted">Los productos y tamaños que indica la tienda. Cuando el producto suelto está en el catálogo, enlazamos a él.</p></div></div>
      {p.pack_size_warning && <div className="callout"><strong>Ojo con los tamaños.</strong> Este pack puede traer versiones más pequeñas (mini o de prueba) que los productos sueltos. Compara los ml de cada producto: el precio del producto suelto es el de su tamaño normal.</div>}
      <div className="grid">{p.contents.map((content, index) => content.product ? <Card key={index} p={content.product} note={`En el pack: ${content.size || 'Sin tamaño confirmado'}`} /> : <div className="card content-card" key={index}><div className="card-img done"><span className="no-img">Sin imagen</span></div><div className="card-body"><h3 className="card-name">{content.product_id ? <a href={`/p/${content.product_id}`}>{content.name}</a> : content.name}</h3><p className="card-meta">{content.size || 'Sin tamaño confirmado'}</p><p className="card-note">No lo tenemos suelto en el catálogo</p></div></div>)}</div>
    </section>}
    {!p.contents.length && p.includes.length > 0 && <section className="section">
      <div className="section-head"><div><h2>Este pack incluye</h2><p className="muted">Cada producto se compara por separado. Revisa el tamaño que trae el pack.</p></div></div>
      {p.pack_size_warning && <div className="callout"><strong>Ojo con los tamaños.</strong> Este pack puede traer versiones más pequeñas (mini o de prueba) que los productos sueltos. Los precios de abajo corresponden al tamaño normal y no se pueden comparar directamente con el precio del pack.</div>}
      <div className="grid">{p.includes.map(row => row.product && <Card key={row.product_id} p={row.product} note={`${row.quantity} unidades · En el pack: ${row.pack_size || 'Sin tamaño confirmado'}`} />)}</div>
    </section>}
    <ProductHistory id={p.id} offers={p.domestic_offers} range={historyRange} />
    {p.included_in.length > 0 && <section className="section">
      <div className="section-head"><div><h2>Se incluye en estos packs</h2><p className="muted">Este producto también se vende dentro de estos sets, a veces en tamaño mini. No cuentan en la comparación de precios de arriba.</p></div></div>
      <div className="grid">{p.included_in.map(row => row.product && <Card key={row.product_id} p={row.product} note={`${row.quantity} unidades`} />)}</div>
    </section>}
    {p.related.length > 0 && <section className="section">
      <div className="section-head"><div><h2>También te podría interesar</h2><p className="muted">{p.is_pack ? 'Otros packs' : 'Otros productos'} del mismo tipo, con ingredientes o tipo de piel en común.</p></div></div>
      <div className="grid">{p.related.map(other => <Card key={other.id} p={other} />)}</div>
    </section>}
    <CatalogMetadata data={data} />
  </article>;
}
