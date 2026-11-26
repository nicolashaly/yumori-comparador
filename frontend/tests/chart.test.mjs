import test from 'node:test';
import assert from 'node:assert/strict';
import { cheapest, historyChart, instant, windowed } from '../lib/chart.mjs';

const obs = (captured_at, amount, available = true) => ({ captured_at, price: { amount, currency: 'CLP', decimals: 0 }, available });
const t = value => instant(value);
const box = { width: 400, height: 200, left: 0, right: 0, top: 0, bottom: 0 };

test('sin observaciones no hay gráfico', () => {
  assert.equal(historyChart([], { from: 0, to: 1 }), null);
  assert.equal(historyChart([{ store: 'a.cl', total: 0, observations: [] }], { from: 0, to: 1 }), null);
});

test('une las lecturas con líneas rectas, desde el precio vigente al empezar y hasta la última lectura', () => {
  const stores = [
    { store: 'a.cl', total: 4, observations: [obs('2026-09-01 12:00:00', 7000), obs('2026-09-28 12:00:00', 10000), obs('2026-10-04 12:00:00', 8000, false), obs('2026-10-07 12:00:00', 9000)] },
    { store: 'b.cl', total: 1, observations: [obs('2026-10-03 12:00:00', 12500)] },
  ];
  const from = t('2026-10-01 12:00:00'), to = t('2026-10-10 12:00:00');
  const chart = historyChart(stores, { ...box, from, to, until: { 'a.cl': t('2026-10-08 12:00:00'), 'b.cl': to }, grid: [t('2026-09-30 12:00:00'), from, t('2026-10-04 12:00:00'), t('2026-10-07 12:00:00'), to] });
  // a.cl arrastra $10.000 desde el 28 sept al borde izquierdo y termina en su última lectura (8 oct), no al final del rango.
  assert.equal(chart.series[0].path, 'M0 133.3L133.3 200L266.7 166.7H311.1');
  assert.deepEqual(chart.series[0].points.map(p => [p.amount, p.available]), [[8000, false], [9000, true]]);
  assert.equal(chart.series[0].area, 'M0 133.3L133.3 200L266.7 166.7H311.1V200H0Z');
  assert.equal(chart.series[1].path, 'M88.9 50H400');
  assert.deepEqual(chart.yTicks.map(tick => tick.value), [8000, 10000, 12000, 14000]);
  // Las líneas fuera del rango se descartan.
  assert.deepEqual(chart.xTicks.map(tick => tick.x), [0, 133.3, 266.7, 400]);
});

test('el rango deja fuera tiendas sin lectura desde antes de empezar', () => {
  const stores = [{ store: 'a.cl', total: 1, observations: [obs('2026-09-01 12:00:00', 5000)] }];
  const from = t('2026-10-01 00:00:00'), to = t('2026-10-02 00:00:00');
  assert.deepEqual(windowed(stores, from, to, { 'a.cl': t('2026-09-20 00:00:00') }), []);
  const chart = historyChart(stores, { ...box, from, to, until: { 'a.cl': to } });
  assert.equal(chart.series[0].path, 'M0 100H400');
  assert.deepEqual(chart.series[0].points, []);
  assert.ok(chart.yTicks[0].value <= 5000 && chart.yTicks.at(-1).value >= 5000);
  assert.equal(instant('2026-10-01 15:00:00'), instant('2026-10-01T12:00:00-03:00'));
});

test('el gráfico toma las 3 tiendas más baratas, con precio confirmado primero y empates alfabéticos', () => {
  const offer = (store, amount, status = 'available') => ({ store, store_name: store, status, price: { amount, currency: 'CLP', decimals: 0 } });
  const offers = [offer('e.cl', 9000), offer('d.cl', 5000), offer('c.cl', 1000, 'suspect'), offer('b.cl', 7000), offer('a.cl', 7000), offer('f.cl', 8000)];
  assert.deepEqual(cheapest(offers), ['d.cl', 'a.cl', 'b.cl']);
  assert.deepEqual(cheapest(offers.slice(0, 2)), ['d.cl', 'e.cl']);
});
