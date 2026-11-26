// Límite de peticiones por clave en ventana fija. shortcut: memoria de un solo proceso, vale mientras haya una sola instancia de Next.
export function createLimiter(limit, windowMs, now = Date.now) {
  const hits = new Map();
  return key => {
    const t = now();
    if (hits.size > 5000) for (const [k, v] of hits) if (v.reset <= t) hits.delete(k);
    const hit = hits.get(key);
    if (!hit || hit.reset <= t) { hits.set(key, { n: 1, reset: t + windowMs }); return true; }
    return ++hit.n <= limit;
  };
}
