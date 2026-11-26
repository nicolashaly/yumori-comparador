import { ApiError, site, type Event } from '../lib/api';
import Search from './search';
import { Card, Failure } from './components';
import HomeDecor from './home-decor';
import DealsCarousel from './deals-carousel';

import { SITE_DESC, abs, jsonLd } from '../lib/seo';

export const metadata = { alternates: { canonical: '/' } };

const count = (value: number) => new Intl.NumberFormat('es-CL').format(value);

function eventDates(event: Event) {
  const months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const [, firstMonth, firstDay] = event.start.split('-').map(Number);
  const [, lastMonth, lastDay] = event.end.split('-').map(Number);
  const first = firstMonth === lastMonth ? firstDay : `${firstDay} de ${months[firstMonth - 1]}`;
  return `del ${first} al ${lastDay} de ${months[lastMonth - 1]}`;
}

function EventLogo({ event }: { event: Event }) {
  return (
    <span className={`ev-logo ev-${event.theme || 'cyber'} ev-md`}>
      <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {event.theme === 'black-friday'
          ? <><path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z" /><circle cx="7.5" cy="7.5" r="1.5" /></>
          : <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />}
      </svg>
      <span>{event.name}</span>
    </span>
  );
}

export default async function Home() {
  let data;
  try {
    data = await site();
  } catch (error) {
    if (error instanceof ApiError) return <Failure message={error.message} />;
    throw error;
  }
  const home = data.home;

  const website = { '@context': 'https://schema.org', '@type': 'WebSite', name: 'Yumori', url: abs('/'), inLanguage: 'es-CL', description: SITE_DESC };
  return (
    <div className="container">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(website) }} />
      <section className="hero">
        <HomeDecor />
        <p className="hero-tags">
          <a className="hero-tag t-rose" href="/explorar">K-beauty</a>
          <a className="hero-tag t-lav" href="/explorar">J-beauty</a>
          {home.section_counts.dermocosmetica > 0 && (
            <a className="hero-tag t-sage" href="/dermocosmetica">Dermocosmética</a>
          )}
        </p>
        <h1 className="hero-title">Tu skincare favorito, <em>al mejor precio</em></h1>
        <p className="hero-sub">
          Comparamos {count(home.product_count)} productos de belleza coreana y japonesa,
          maquillaje y marcas de farmacia en {home.store_count} tiendas de Chile y del
          extranjero, con el historial de cada precio.
        </p>
        <Search action="/explorar" />
        <div className="chips">
          {home.top_brands.map(brand => (
            <a className="chip" key={brand.slug} href={`/explorar?marca=${encodeURIComponent(brand.slug)}`}>
              {brand.name} <span className="n">{brand.count}</span>
            </a>
          ))}
        </div>
      </section>

      {data.live_event && home.live_event_summary && home.live_event_summary.product_count > 0 && (
        <a className="event-callout" href={`/${data.live_event.slug}`}>
          <span>
            <EventLogo event={data.live_event} /> {eventDates(data.live_event)}<br />
            {count(home.live_event_summary.product_count)} producto{home.live_event_summary.product_count !== 1 ? 's' : ''}
            {' '}rebajado{home.live_event_summary.product_count !== 1 ? 's' : ''} en{' '}
            {home.live_event_summary.store_count} tienda{home.live_event_summary.store_count !== 1 ? 's' : ''}
          </span>
          <span className="btn btn-primary btn-sm" aria-hidden="true">Ver {data.live_event.name}</span>
        </a>
      )}

      {home.deals.length > 0 && (
        <DealsCarousel total={home.deals_total} items={home.deals.length}
          percent={home.deal_show_percent} days={home.deal_days}>
          {home.deals.map(product => <Card key={product.id} p={product} />)}
        </DealsCarousel>
      )}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Mayor diferencia entre tiendas</h2>
            <p className="muted">El mismo producto, con precios distintos según dónde lo compres.</p>
          </div>
          <a className="link" href="/explorar?multi=1&orden=ahorro"
            aria-label="Ver más productos con diferencias de precio entre tiendas">Ver más</a>
        </div>
        <div className="grid">{home.spread.map(product => <Card key={product.id} p={product} />)}</div>
      </section>

      {home.drops.length > 0 && (
        <section className="section">
          <div className="section-head"><h2>Bajaron de precio</h2></div>
          <div className="grid">{home.drops.map(product => <Card key={product.id} p={product} />)}</div>
        </section>
      )}

      <p className="muted" style={{ marginTop: 'var(--s-8)', textAlign: 'center', fontSize: 'var(--fs-sm)' }}>
        {count(home.section_counts.asiatica ?? 0)} productos · {data.stores.asiatica.length} tiendas
      </p>
      {home.section_counts.dermocosmetica > 0 && (
        <p className="home-more">
          ¿Buscas dermocosmética de farmacia? <a className="link" href="/dermocosmetica">Ver dermocosmética</a>
        </p>
      )}
    </div>
  );
}
