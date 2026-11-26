export const KEY = 'yumori:fav';
const ID = /^[0-9a-f]{10}$/;

export function validateIds(value) {
  if (!Array.isArray(value) || value.length > 10000 || value.some(id => typeof id !== 'string' || !ID.test(id))) {
    throw new Error('La lista de favoritos no es válida. Se conserva el contenido guardado.');
  }
  return [...new Set(value)];
}
export function readFavorites(storage) {
  const raw = storage.getItem(KEY);
  return raw === null ? [] : validateIds(JSON.parse(raw));
}
export function importIds(text) {
  if (text.length > 1000000) throw new Error('El archivo de favoritos es demasiado grande.');
  const value = JSON.parse(text);
  if (Array.isArray(value)) return validateIds(value);
  if (!value || value.version !== 1 || value.key !== KEY) throw new Error('Formato de favoritos desconocido.');
  return validateIds(value.ids);
}
export function exportIds(ids) {
  return JSON.stringify({ version: 1, key: KEY, ids: validateIds(ids) }, null, 2);
}
export async function resolveFavorites(ids, request) {
  const input = validateIds(ids);
  const items = new Map();
  const missing = [];
  for (let index = 0; index < input.length; index += 100) {
    const batch = input.slice(index, index + 100);
    const result = await request(batch);
    if (result?.version !== 1 || !Array.isArray(result.items) || !result.resolutions || !Array.isArray(result.missing_ids)) {
      throw new Error('Respuesta incompleta de favoritos.');
    }
    const returned = new Map();
    for (const item of result.items) {
      if (!item || !ID.test(item.id) || returned.has(item.id) || typeof item.name !== 'string') throw new Error('Respuesta inválida de favoritos.');
      returned.set(item.id, item);
    }
    if (Object.keys(result.resolutions).length !== batch.length) throw new Error('Resoluciones incompletas.');
    const expected = new Set();
    const absent = [];
    for (const requested of batch) {
      if (!Object.hasOwn(result.resolutions, requested)) throw new Error('Resoluciones incompletas.');
      const canonical = result.resolutions[requested];
      if (canonical === null) { absent.push(requested); missing.push(requested); }
      else {
        if (typeof canonical !== 'string' || !ID.test(canonical) || !returned.has(canonical)) throw new Error('Producto resuelto ausente.');
        expected.add(canonical);
        if (!items.has(canonical)) items.set(canonical, returned.get(canonical));
      }
    }
    if (returned.size !== expected.size || JSON.stringify([...absent].sort()) !== JSON.stringify([...result.missing_ids].sort())) throw new Error('Respuesta de favoritos contradictoria.');
  }
  return { ids: [...items.keys()], items: [...items.values()], missing };
}
export function commitFavorites(storage, before, after) {
  if (JSON.stringify(readFavorites(storage)) !== JSON.stringify(before)) return false;
  storage.setItem(KEY, JSON.stringify(validateIds(after)));
  return true;
}
