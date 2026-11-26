import test from 'node:test';
import assert from 'node:assert/strict';
import { KEY, commitFavorites, exportIds, importIds, readFavorites, resolveFavorites } from '../lib/favorites.mjs';

const id = n => n.toString(16).padStart(10, '0');
const product = n => ({ id: id(n), name: `Producto ${n}` });
function storage(ids) {
  let raw = JSON.stringify(ids);
  return { getItem: key => key === KEY ? raw : null, setItem(key, value) { assert.equal(key, KEY); raw = value; } };
}
function response(ids) {
  return { version: 1, items: ids.map(value => ({ id: value, name: value })), resolutions: Object.fromEntries(ids.map(value => [value, value])), missing_ids: [] };
}
test('resuelve más de cien favoritos sin truncar y conserva el orden', async () => {
  const ids = Array.from({ length: 205 }, (_, n) => id(n));
  const sizes = [];
  const result = await resolveFavorites(ids, async batch => { sizes.push(batch.length); return response(batch); });
  assert.deepEqual(sizes, [100, 100, 5]);
  assert.deepEqual(result.ids, ids);
});
test('aliases se deduplican y solo una respuesta completa permite retirar faltantes', async () => {
  const result = await resolveFavorites([id(1), id(2), id(3)], async () => ({ version: 1, items: [product(4)], resolutions: { [id(1)]: id(4), [id(2)]: id(4), [id(3)]: null }, missing_ids: [id(3)] }));
  assert.deepEqual(result.ids, [id(4)]);
  assert.deepEqual(result.missing, [id(3)]);
});
test('un segundo lote fallido deja intacto el almacenamiento', async () => {
  const before = Array.from({ length: 101 }, (_, n) => id(n));
  const saved = storage(before);
  let calls = 0;
  await assert.rejects(resolveFavorites(before, async batch => { if (++calls === 2) throw new Error('offline'); return response(batch); }));
  assert.deepEqual(readFavorites(saved), before);
});
test('rechaza éxito parcial y faltantes contradictorios', async () => {
  const values = [id(1), id(2)];
  await assert.rejects(resolveFavorites(values, async () => response([id(1)])), /incompletas/);
  await assert.rejects(resolveFavorites([id(1)], async () => ({ version: 1, items: [], resolutions: { [id(1)]: id(4) }, missing_ids: [] })), /ausente/);
  await assert.rejects(resolveFavorites([id(1)], async () => ({ version: 1, items: [], resolutions: { [id(1)]: null }, missing_ids: [] })), /contradictoria/);
});
test('una edición concurrente evita sobrescribir cambios del usuario', () => {
  const saved = storage([id(1)]);
  const before = readFavorites(saved);
  saved.setItem(KEY, JSON.stringify([id(1), id(2)]));
  assert.equal(commitFavorites(saved, before, [id(4)]), false);
  assert.deepEqual(readFavorites(saved), [id(1), id(2)]);
});
test('traslado exporta misma clave y valida JSON sin ejecutar texto', () => {
  assert.deepEqual(importIds(exportIds([id(1), id(2), id(1)])), [id(1), id(2)]);
  assert.deepEqual(importIds(JSON.stringify([id(1)])), [id(1)]);
  assert.throws(() => importIds('{"version":2,"key":"yumori:fav","ids":[]}'));
  assert.throws(() => importIds(JSON.stringify([id(1), '<script>'])));
  assert.throws(() => importIds('x'.repeat(1000001)));
});
test('error de almacenamiento nunca se confunde con favoritos vacíos', () => {
  assert.throws(() => readFavorites({ getItem() { throw new Error('blocked'); } }));
  assert.throws(() => readFavorites(storage({ ids: [] })));
  assert.throws(() => commitFavorites({ getItem: () => '[]', setItem() { throw new Error('quota'); } }, [], [id(1)]));
});
