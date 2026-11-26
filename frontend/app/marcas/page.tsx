import { ApiError, Brand, site } from '../../lib/api';
import { CatalogMetadata, Failure } from '../components';
export const metadata = { title: 'Marcas', description: 'Las marcas de belleza coreana, japonesa y china que comparamos en tiendas de Chile, de la A a la Z.', alternates: { canonical: '/marcas' } };

function Letters({ brands, base, level }: { brands: Brand[]; base: string; level: 2 | 3 }) {
  const letters = new Map<string, Brand[]>();
  for (const brand of brands) {
    const initial = brand.name.charAt(0).toUpperCase();
    const letter = /^[A-ZÀ-Ü]$/u.test(initial) ? initial : '#';
    letters.set(letter, [...letters.get(letter) || [], brand]);
  }
  return [...letters].sort(([a],[b]) => a.localeCompare(b, 'es')).map(([letter,brands]) => <section className="letter" key={letter}>
    {level === 2 ? <h2>{letter}</h2> : <h3>{letter}</h3>}
    <div className="chips" style={{justifyContent: 'flex-start'}}>{brands.map(brand => <a className="chip" data-brand-slug={brand.slug} key={brand.slug} href={`${base}?marca=${encodeURIComponent(brand.slug)}`}>{brand.name} <span className="n">{brand.count}</span></a>)}</div>
  </section>);
}

export default async function Page() {
  let data; try { data = await site(); } catch (error) { if (error instanceof ApiError) return <Failure message={error.message} />; throw error; }
  const derm = data.brands.dermocosmetica.length > 0;
  return <div className="container"><div className="page-head"><h1>Marcas</h1><p className="muted">{data.brands.asiatica.length} marcas{derm && ` de belleza asiática y ${data.brands.dermocosmetica.length} de dermocosmética`}</p></div>
    {derm ? <><section className="section"><div className="section-head"><h2>Belleza asiática</h2></div><Letters brands={data.brands.asiatica} base="/explorar" level={3} /></section><section className="section"><div className="section-head"><div><h2>Dermocosmética</h2><p className="muted small">Marcas que se venden sobre todo en farmacias. Se comparan aparte.</p></div></div><Letters brands={data.brands.dermocosmetica} base="/dermocosmetica" level={3} /></section></> : <Letters brands={data.brands.asiatica} base="/explorar" level={2} />}
    <CatalogMetadata data={data} />
  </div>;
}
