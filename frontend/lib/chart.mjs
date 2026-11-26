// Geometría del gráfico de historial: solo presentación, sin reglas del catálogo.
export function instant(value) {
  const iso = value.replace(' ', 'T');
  return Date.parse(/(?:Z|[+-]\d\d:\d\d)$/.test(iso) ? iso : `${iso}Z`);
}

// Tiendas que entran al gráfico: las `n` más baratas hoy, con stock y precio confirmado primero; empates en orden alfabético.
export function cheapest(offers, n = 3) {
  const rank = o => Number(o.status !== 'available');
  return [...offers].sort((a, b) => rank(a) - rank(b) || a.price.amount - b.price.amount || a.store_name.localeCompare(b.store_name, 'es'))
    .slice(0, n).map(o => o.store);
}

export const RANGES = { dia: 86400000, semana: 7 * 86400000, mes: 30 * 86400000 };

// La base guarda solo cambios: la última observación anterior al rango es el precio vigente al empezar,
// salvo que la tienda no se haya vuelto a leer desde entonces (`until` anterior al rango).
export function windowed(stores, from, to, until = {}) {
  return stores.map(s => {
    const sorted = s.observations.map(o => ({ ...o, time: instant(o.captured_at) })).filter(o => Number.isFinite(o.time) && o.time <= to)
      .sort((a, b) => a.time - b.time);
    const first = sorted.findIndex(o => o.time >= from);
    const start = first === -1 ? sorted.length - 1 : Math.max(0, first - 1);
    return { store: s.store, observations: start < 0 ? [] : sorted.slice(start) };
  }).filter(s => s.observations.length && Math.max(s.observations.at(-1).time, until[s.store] ?? -Infinity) >= from);
}

function niceStep(span, count) {
  const raw = span / count, magnitude = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map(m => m * magnitude).find(step => step >= raw);
}

const round = n => Math.round(n * 10) / 10;

// `grid`: instantes de las líneas verticales (días u horas, según el rango).
// `until`: hasta cuándo cada tienda confirmó su precio (última lectura); la línea no se alarga más allá.
export function historyChart(stores, { from, to, until = {}, grid = [], width = 640, height = 260, left = 76, right = 16, top = 12, bottom = 28 }) {
  const series = windowed(stores, from, to, until);
  if (!series.length) return null;
  const amounts = series.flatMap(s => s.observations.map(o => o.price.amount));
  let lo = Math.min(...amounts), hi = Math.max(...amounts);
  if (lo === hi) { lo -= Math.max(1, hi * 0.05); hi += Math.max(1, hi * 0.05); }
  const step = niceStep(hi - lo, 4), y0 = Math.max(0, Math.floor(lo / step) * step), y1 = Math.ceil(hi / step) * step;
  const x = time => round(left + (Math.min(to, Math.max(from, time)) - from) / (to - from) * (width - left - right));
  const y = amount => round(top + (y1 - amount) / (y1 - y0) * (height - top - bottom));
  const yTicks = [];
  for (let value = y0; value <= y1 + step / 2; value += step) yTicks.push({ value, y: y(value) });
  return {
    width, height, left, right, top, bottom, yTicks,
    xTicks: grid.filter(time => time >= from && time <= to).map(time => ({ time, x: x(time) })),
    // Línea recta entre observaciones, y plana desde la última hasta `end`. La pendiente solo une dos lecturas: no es un precio estimado.
    series: series.map(s => {
      const obs = s.observations, last = obs.at(-1), end = Math.min(to, Math.max(last.time, until[s.store] ?? last.time));
      const path = obs.map((o, i) => `${i ? 'L' : 'M'}${x(o.time)} ${y(o.price.amount)}`).join('') + (x(end) > x(last.time) ? `H${x(end)}` : '');
      return {
        store: s.store,
        path,
        // Relleno bajo la línea: la misma línea, cerrada contra el eje X.
        area: `${path}V${height - bottom}H${x(obs[0].time)}Z`,
        // La observación arrastrada desde antes del rango queda en el borde izquierdo, sin punto.
        points: obs.filter(o => o.time >= from).map(o => ({ x: x(o.time), y: y(o.price.amount), time: o.time, amount: o.price.amount, available: o.available })),
      };
    }),
  };
}
