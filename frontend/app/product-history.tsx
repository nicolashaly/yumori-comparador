import { ApiError, type HistoryResponse, type Offer, history, money } from '../lib/api';
import { RANGES, cheapest, historyChart, instant, windowed } from '../lib/chart.mjs';
import { Price } from './components';

export type HistoryRange = keyof typeof RANGES;
const LABELS: Record<HistoryRange, string> = { dia: '1 día', semana: '1 semana', mes: '1 mes' };

function captured(value: string) {
  const date = new Date(instant(value));
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('es-CL', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Santiago',
  }).format(date);
}

const tz = 'America/Santiago';
const day = (time: number, year = false) => new Intl.DateTimeFormat('es-CL', { day: 'numeric', month: 'short', year: year ? 'numeric' : undefined, timeZone: tz }).format(time);
const hour = (time: number) => new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: tz }).format(time);
const hourOf = new Intl.DateTimeFormat('es-CL', { hour: 'numeric', hourCycle: 'h23', timeZone: tz });

// Líneas verticales: cada medianoche de Chile, o cada 3 horas en el rango de un día (los husos de Chile son horas enteras).
function gridTimes(from: number, to: number, range: HistoryRange) {
  const times = [];
  for (let time = Math.ceil(from / 3600000) * 3600000; time <= to; time += 3600000) {
    const h = Number(hourOf.format(time));
    if (range === 'dia' ? h % 3 === 0 : h === 0) times.push(time);
  }
  return times;
}
const clp = (amount: number) => money({ amount, currency: 'CLP', decimals: 0 });

// La API pagina en orden cronológico; se juntan todas las páginas para tener el precio vigente al empezar el rango.
async function fullHistory(id: string) {
  const data = await history(id, 1);
  for (let page = 2; data.stores.some(s => s.total > (page - 1) * data.limit); page++) {
    for (const s of (await history(id, page)).stores) data.stores.find(d => d.store === s.store)?.observations.push(...s.observations);
  }
  return data;
}

function HistoryChart({ stores, from, to, until, range }: { stores: HistoryResponse['stores']; from: number; to: number; until: Record<string, number>; range: HistoryRange }) {
  // Orden alfabético para asignar colores sin favorecer a ninguna tienda.
  const chart = historyChart([...stores].sort((a, b) => a.store.localeCompare(b.store)), { from, to, until, grid: gridTimes(from, to, range) });
  if (!chart) return <p>No hay precios confirmados en este rango.</p>;
  const amounts = windowed(stores, from, to, until).flatMap(s => s.observations.map(o => o.price.amount));
  const style = (i: number) => `s${i % 6} d${Math.floor(i / 6) % 3}`;
  // Etiquetas: cada semana en 1 mes, cada 6 horas en 1 día, cada día en 1 semana.
  const labeled = (time: number, i: number) => range === 'mes' ? i % 7 === 0 : range === 'dia' ? Number(hourOf.format(time)) % 6 === 0 : true;
  return <figure className="history-chart">
    <div className="history-chart-scroll" tabIndex={0}>
      <svg viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-labelledby="historial-grafico-titulo historial-grafico-desc">
        <title id="historial-grafico-titulo">{`Precio observado por tienda, rango de ${LABELS[range]}`}</title>
        <desc id="historial-grafico-desc">{`${chart.series.length} tiendas entre el ${day(from, true)} ${hour(from)} y el ${day(to, true)} ${hour(to)}; precio más bajo ${clp(Math.min(...amounts))} y más alto ${clp(Math.max(...amounts))}. Los datos de todas las tiendas están en las tablas por tienda.`}</desc>
        {chart.yTicks.map(t => <g key={t.value} className="tick">
          <line x1={chart.left} x2={chart.width - chart.right} y1={t.y} y2={t.y} />
          <text x={chart.left - 8} y={t.y} textAnchor="end" dominantBaseline="middle">{clp(t.value)}</text>
        </g>)}
        {chart.xTicks.map((t, i) => <g key={t.time} className="tick">
          <line className={labeled(t.time, i) ? 'v major' : 'v'} x1={t.x} x2={t.x} y1={chart.top} y2={chart.height - chart.bottom} />
          {labeled(t.time, i) && t.x > chart.left + 20 && t.x < chart.width - chart.right - 20 &&
            <text x={t.x} y={chart.height - 6} textAnchor="middle">{range === 'dia' && Number(hourOf.format(t.time)) ? hour(t.time) : day(t.time)}</text>}
        </g>)}
        {chart.series.map((s, i) => <g key={s.store} className={`series ${style(i)}`}><path className="area" d={s.area} /></g>)}
        {chart.series.map((s, i) => <g key={s.store} className={`series ${style(i)}`}><path d={s.path} /></g>)}
        {/* Burbuja con CSS puro (sin JS en línea): aparece al pasar el cursor por un cambio de precio. */}
        {chart.series.map((s, i) => <g key={s.store} className={`series ${style(i)}`}>
          {s.points.map((p, j) => {
            const lines = [clp(p.amount), s.store, `${range === 'dia' ? `${day(p.time)} ${hour(p.time)}` : day(p.time, true)}${p.available ? '' : ' · sin stock'}`];
            // shortcut: ancho estimado por cantidad de caracteres, no medido; si cambia la tipografía, ajustar 6.5.
            const w = Math.max(...lines.map(l => l.length)) * 6.5 + 16, h = 54;
            const bx = Math.min(Math.max(p.x - w / 2, 2), chart.width - 2 - w), by = p.y - h - 10 < 2 ? p.y + 10 : p.y - h - 10;
            return <g key={j} className="pt">
              <line className="guide" x1={p.x} x2={p.x} y1={p.y} y2={chart.height - chart.bottom} />
              <circle cx={p.x} cy={p.y} r={4} className={p.available ? undefined : 'out'} />
              <circle cx={p.x} cy={p.y} r={11} className="hit" />
              <g className="bubble"><rect x={bx} y={by} width={w} height={h} rx={8} />
                <text x={bx + 8} y={by + 16} className="b-price">{lines[0]}</text>
                <text x={bx + 8} y={by + 31}>{lines[1]}</text>
                <text x={bx + 8} y={by + 45}>{lines[2]}</text></g>
            </g>;
          })}
        </g>)}
      </svg>
    </div>
    <figcaption>
      <ul className="history-legend">{chart.series.map((s, i) => <li key={s.store}>
        <svg className={`series ${style(i)}`} viewBox="0 0 24 10" aria-hidden="true"><path d="M0 5H24" /></svg>{s.store}
      </li>)}</ul>
      <p>La línea une cada cambio de precio observado con el siguiente; la pendiente no significa que el precio cambió de forma gradual, y se extiende hasta la última lectura de cada tienda. Punto: cambio observado; hueco: sin stock.</p>
    </figcaption>
  </figure>;
}

export default async function ProductHistory({ id, offers, range = 'mes' }: { id: string; offers: Offer[]; range?: HistoryRange }) {
  let data;
  try { data = await fullHistory(id); } catch (error) {
    return <section className="section" id="historial">
      <div className="section-head"><h2>Historial de precios</h2></div>
      <div className="history"><p role="alert">{error instanceof ApiError ? error.message : 'No se pudo cargar el historial.'}</p>
        <a className="link" href={`/p/${id}#historial`}>Reintentar historial</a>
      </div>
    </section>;
  }
  const to = Date.now(), from = to - RANGES[range], updated = data.catalog_last_update;
  // Hasta dónde está confirmado cada precio: la última lectura de la tienda o del listing, si dejó de leerse.
  const until = Object.fromEntries(offers.map(o => [o.store, instant(o.stale_since ?? o.missing_since ?? updated ?? '')] as const)
    .filter(([, time]) => Number.isFinite(time)));
  // Con muchas tiendas el gráfico se satura: dibuja solo las 3 más baratas hoy; las tablas accesibles conservan todas.
  const top = cheapest(offers), stores = data.stores.filter(s => top.includes(s.store));
  const shown = windowed(data.stores, from, to, until);
  return <section className="section" id="historial">
    <div className="section-head"><h2>Historial de precios</h2></div>
    <div className="history">
      <p>Cambios de precio por tienda chilena. Fechas en hora de Chile (America/Santiago); no se estiman precios entre lecturas ni se suma despacho.</p>
      <nav className="history-ranges" aria-label="Rango del historial">
        {(Object.keys(LABELS) as HistoryRange[]).map(key => <a key={key} className={key === range ? 'chip chip-accent' : 'chip'}
          aria-current={key === range ? 'true' : undefined} href={`/p/${id}${key === 'mes' ? '' : `?rango=${key}`}#historial`}>{LABELS[key]}</a>)}
      </nav>
      {stores.length ? <HistoryChart stores={stores} from={from} to={to} until={until} range={range} /> : <p>Sin historial de tiendas chilenas.</p>}
      {offers.length > top.length && <p className="muted">Se muestran las {top.length} tiendas más baratas hoy de {offers.length}; el precio de todas está en la lista de arriba.</p>}
      {/* Alternativa accesible del gráfico: los mismos datos, solo para lectores de pantalla. */}
      <div className="sr-only">{shown.map(store => <table key={store.store} data-history-store={store.store}>
        <caption>{store.store} · {store.observations.length} observaciones</caption>
        <thead><tr><th>Captura en Chile</th><th>Precio</th><th>Stock observado</th></tr></thead>
        <tbody>{store.observations.map((observation, index) =>
          <tr key={index} data-history-store={store.store} data-captured-at={observation.captured_at}>
            <th scope="row"><time dateTime={observation.captured_at}>{captured(observation.captured_at)}</time></th>
            <td><Price value={observation.price} /></td><td>{observation.available ? 'Disponible' : 'Sin stock'}</td>
          </tr>)}</tbody>
      </table>)}</div>
    </div>
  </section>;
}
