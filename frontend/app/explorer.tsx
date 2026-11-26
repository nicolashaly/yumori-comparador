import { ApiError, products, Query, queryString, site } from '../lib/api';
import { Card, CatalogMetadata, Failure } from './components';
import FilterDrawer, { FilterToggle } from './filter-drawer';
export const dynamic = 'force-dynamic';

const sorts = [['', 'Relevancia'], ['precio_asc', 'Precio: menor a mayor'], ['precio_desc', 'Precio: mayor a menor'], ['ahorro', 'Mayor diferencia entre tiendas'], ['descuento', 'Mayor descuento'], ['nombre', 'Nombre']];
const number = (value: number) => new Intl.NumberFormat('es-CL').format(value);

export default async function Explorer({ searchParams, base = '/explorar', title = 'Explorar', forced = {}, intro }: { searchParams: Promise<Query>; base?: string; title?: string; forced?: Query; intro?: React.ReactNode }) {
  const query = { ...await searchParams, ...forced };
  let data, context;
  try { [data, context] = await Promise.all([products(query), site()]); }
  catch (error) { if (error instanceof ApiError) return <Failure message={error.message} />; throw error; }
  const first = (key: string) => { const value = query[key]; return Array.isArray(value) ? value[0] : value || ''; };
  const selected = (key: string): string[] => { const value = query[key]; return Array.isArray(value) ? value : value ? [value] : []; };
  const url = (overrides: Query) => `${base}?${queryString({ ...query, pagina: undefined, ...overrides })}`;
  const packs = first('packs') === '1';
  const derm = base.startsWith('/dermocosmetica');
  const event = context.events.find(event => event.slug === first('evento'));
  const brands = event ? [...context.brands.asiatica, ...context.brands.dermocosmetica] : context.brands[derm ? 'dermocosmetica' : 'asiatica'];
  const stores = event ? [...context.stores.asiatica, ...context.stores.dermocosmetica] : context.stores[derm ? 'dermocosmetica' : 'asiatica'];
  const storeNames = new Map(stores.map(store => [store.domain, store.name]));
  const brand = brands.find(brand => brand.slug === first('marca'));
  const category = context.categories.find(category => category.slug === first('cat'));
  if (derm && data.section_product_count === 0) return <div className="container"><div className="page-head"><h1>Dermocosmética</h1></div><div className="empty"><p>Estamos sumando farmacias a Yumori.</p><p className="small">Todavía no tenemos precios de dermocosmética para mostrar.</p><p><a className="link" href="/explorar">Explorar belleza asiática</a></p></div></div>;
  let heading = packs && !derm && !event ? 'Packs y sets' : title;
  if (first('q')) heading = base === '/explorar' ? `Resultados para «${first('q')}»` : `${heading}: «${first('q')}»`;
  else if (brand) heading = `${brand.name}${packs ? ' · packs' : ''}`;
  else if (category && !packs) heading = derm || event ? `${title}: ${category.name}` : category.name;
  else if (first('oferta') === '1' && !packs) heading = selected('tienda').length === 1 ? `Ofertas en ${storeNames.get(first('tienda')) || first('tienda')}` : 'Productos con descuento';
  const packsBase = base === '/explorar' ? '/packs' : `${base}/packs`;
  const packsUrl = `${packsBase}?${queryString({q: first('q'), marca: first('marca'), sinstock: first('sinstock')})}`;
  const otherBase = derm ? '/explorar' : '/dermocosmetica';
  const otherUrl = `${otherBase}?${queryString({q: first('q'), sinstock: first('sinstock')})}`;
  const checks = (key: string, label: string, limit?: number, initiallyOpen = false) => {
    const counts = { ...data.facets[key] };
    if (key === 'tienda') for (const store of stores) counts[store.domain] ??= 0;
    const values = Object.entries(counts).sort((a,b) => b[1] - a[1]);
    const options = limit ? values.slice(0, limit) : values;
    for (const value of selected(key)) if (!options.some(([option]) => option === value)) options.push([value, data.facets[key]?.[value] || 0]);
    return <details className="fgroup" open={initiallyOpen || selected(key).length > 0}><summary>{label}</summary>{options.map(([value,count]) => <label className="check" key={value}><input type="checkbox" name={key} value={value} defaultChecked={selected(key).includes(value)} />{key === 'tienda' ? storeNames.get(value) || value : value.charAt(0).toUpperCase() + value.slice(1)}<span className="n" data-facet-name={key} data-facet-value={value} data-facet-count={count}>{number(count)}</span></label>)}</details>;
  };
  const filters = <>
    {['q','marca','cat'].map(key => <input type="hidden" name={key} value={first(key)} key={key} />)}
    {Object.entries(forced).map(([key,value]) => !['q','marca','cat'].includes(key) && <input type="hidden" name={key} value={Array.isArray(value) ? value[0] : value} key={key} />)}
    {!packs && <>{checks('tipo', 'Tipo de producto', 16, true)}{checks('piel', 'Tipo de piel')}{checks('ing', 'Ingrediente destacado', 12)}</>}
    {checks('tienda', 'Tiendas')}
    <div><h3>Precio (CLP)</h3><div className="range"><input className="field" type="number" min="0" step="1000" name="min" placeholder="Mín." aria-label="Precio mínimo" defaultValue={first('min')} /><input className="field" type="number" min="0" step="1000" name="max" placeholder="Máx." aria-label="Precio máximo" defaultValue={first('max')} /></div></div>
    <div><h3>Disponibilidad</h3>{[['sinstock', 'Incluir productos sin stock'], ['multi', 'En 2 o más tiendas'], ['oferta', 'Solo con descuento']].filter(([key]) => forced[key] === undefined && !(event && key === 'oferta')).map(([key,label]) => <label className="check" key={key}><input type="checkbox" name={key} value="1" defaultChecked={first(key) === '1'} />{label}</label>)}</div>
    <div style={{display: 'flex', gap: 'var(--s-2)'}}><button className="btn btn-primary btn-sm" type="submit">Aplicar</button><a className="btn btn-ghost btn-sm" href={first('q') ? `${base}?${queryString({q: first('q')})}` : base}>Limpiar</a></div>
  </>;
  return <div className="container">
    <div className="page-head">
      {event ? <h1 className="ev-title"><span className={`ev-logo ev-${event.theme} ev-xl`}><svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{event.theme === 'black-friday' ? <><path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z" /><circle cx="7.5" cy="7.5" r="1.5" /></> : <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />}</svg><span>{event.name}</span></span>{heading !== event.name && <span className="ev-rest">{heading.startsWith(event.name) ? heading.slice(event.name.length) : `: ${heading}`}</span>}</h1> : <h1>{heading}</h1>}
      <p className="muted" data-total={data.total}>{number(data.total)} {packs ? 'packs' : 'productos'}</p>
      {intro && <div className="muted small">{intro}</div>}
      {packs && !intro && <p className="muted small">Sets, kits, duos y packs de varias unidades. Cada pack se compara solo con el mismo pack en otras tiendas, no con los productos sueltos.</p>}
      {derm && !first('q') && !packs && <p className="muted small">Marcas que se venden sobre todo en farmacias, con los precios de las tiendas chilenas que las tienen. Un precio que exige una tarjeta de la tienda no cuenta como mejor precio: se muestra aparte en cada producto.</p>}
      {data.related_counts.packs > 0 && <a className="packs-callout" href={packsUrl}><span><b>{number(data.related_counts.packs)} packs</b> también coinciden con tu búsqueda</span><span className="btn btn-primary btn-sm" aria-hidden="true">Ver packs</span></a>}
      {data.related_counts.other_section > 0 && <p className="muted small">También hay {number(data.related_counts.other_section)} productos en {derm ? 'belleza asiática' : 'dermocosmética'} que coinciden · <a className="link" href={otherUrl}>Ver en {derm ? 'Explorar' : 'Dermocosmética'}</a></p>}
      {!packs && <nav className="chips cats" aria-label="Categorías">{[{slug: '', name: 'Todo', count: 0}, ...context.categories].map(({slug,name}) => <a className="chip" key={slug} aria-current={first('cat') === slug ? 'page' : undefined} href={`${base}?${queryString({q: first('q'), marca: first('marca'), cat: slug, sinstock: first('sinstock')})}`}>{name}{slug && <span className="n" data-facet-name="cat" data-facet-value={slug} data-facet-count={data.category_counts[slug] || 0}>{number(data.category_counts[slug] || 0)}</span>}</a>)}</nav>}
    </div>
    <FilterDrawer action={base} filters={filters}>
      <div className="toolbar"><div className="active-filters"><FilterToggle />{brand && <a className="chip" href={url({marca: undefined})} aria-label="Quitar filtro de marca">{brand.name} ×</a>}{first('oferta') === '1' && <a className="chip" href={url({oferta: undefined})} aria-label="Quitar filtro de descuento">Con descuento ×</a>}</div><label className="sr-only" htmlFor="sort">Ordenar por</label><select className="select" id="sort" name="orden" form="ff" defaultValue={first('orden')} style={{width:'auto'}}>{sorts.map(([value,label]) => <option value={value} key={value}>{label}</option>)}</select></div>
      {data.items.length ? <div className="grid">{data.items.map(product => <Card key={product.id} p={product} />)}</div> : <div className="empty"><p>{event && !Object.keys(query).some(key => !['evento','packs','seccion','orden'].includes(key) && first(key)) ? `Todavía no detectamos rebajas de ${event.name}.` : `No encontramos ${packs ? 'packs' : 'productos'} con esos filtros.`}</p>{event && <p className="small">Aparecen aquí a medida que revisamos los precios de cada tienda.</p>}{data.related_counts.other_section > 0 && <p><a className="btn btn-primary btn-sm" href={otherUrl}>Ver en {derm ? 'Explorar' : 'Dermocosmética'}</a></p>}<p><a className="link" href={base}>Ver {packs ? 'todos los packs' : 'todo el catálogo'}</a></p></div>}
      {data.pages > 1 && <nav aria-label="Paginación" className="pagination">{data.page > 1 && <a className="btn btn-soft btn-sm" href={url({pagina: String(data.page - 1)})}>Anterior</a>}<span>Página {data.page} de {data.pages}</span>{data.page < data.pages && <a className="btn btn-soft btn-sm" href={url({pagina: String(data.page + 1)})}>Siguiente</a>}</nav>}
    </FilterDrawer>
    <CatalogMetadata data={data} />
  </div>;
}
