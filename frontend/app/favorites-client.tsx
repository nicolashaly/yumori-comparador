'use client';
import { useEffect, useRef, useState } from 'react';
import type { FavoritesResponse, Product } from '../lib/api';
import Card from './product-card';
import { CHANGED, changed } from './favorite-controls';
export { FavoriteButton, FavoriteCount } from './favorite-controls';
import { KEY, commitFavorites, readFavorites, resolveFavorites } from '../lib/favorites.mjs';


async function batch(ids: string[]): Promise<FavoritesResponse> {
  const response = await fetch(`/api/favorites?ids=${encodeURIComponent(ids.join(','))}`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Sin conexión: no se pudieron cargar los favoritos.');
  return response.json();
}
export default function Favorites() {
  const [items, setItems] = useState<Product[]>([]);
  const [message, setMessage] = useState('Cargando favoritos…');
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const active = useRef(false);
  const pending = useRef(false);
  const mounted = useRef(false);
  const loadRef = useRef<() => Promise<void>>(async () => {});
  loadRef.current = async () => {
    if (active.current) { pending.current = true; return; }
    active.current = true; setBusy(true); setRetry(false);
    try {
      const before = readFavorites(localStorage);
      const result = await resolveFavorites(before, batch);
      if (!mounted.current) return;
      if (!commitFavorites(localStorage, before, result.ids)) { pending.current = true; return; }
      setItems(result.items);
      setMessage(result.ids.length ? (result.missing.length ? `${result.missing.length} productos ya no aparecen en el catálogo.` : '') : 'Todavía no guardas ningún producto.');
      // La página pinta primero y los botones reciben la nueva lista.
      changed(); pending.current = false;
    } catch {
      if (mounted.current) { setMessage('Sin conexión o almacenamiento no disponible: no se pudieron cargar tus favoritos. La lista guardada se conserva. Puedes reintentar.'); setRetry(true); }
    } finally {
      active.current = false;
      if (mounted.current) { setBusy(false); if (pending.current) { pending.current = false; void loadRef.current(); } }
    }
  };
  useEffect(() => {
    mounted.current = true;
    const update = () => { void loadRef.current(); };
    const storage = (event: StorageEvent) => { if (event.key === KEY || event.key === null) update(); };
    update(); window.addEventListener(CHANGED, update); window.addEventListener('storage', storage);
    return () => { mounted.current = false; window.removeEventListener(CHANGED, update); window.removeEventListener('storage', storage); };
  }, []);
  return <div className="container"><div className="page-head"><h1>Favoritos</h1><p>Guardados en este navegador y en esta dirección del sitio.</p></div><div className="grid" aria-busy={busy}>{items.map(p => <Card p={p} key={p.id} />)}</div><p role="status" aria-live="polite">{message}</p>{retry && <button className="btn btn-soft" type="button" disabled={busy} onClick={() => void loadRef.current()}>Reintentar</button>}</div>;
}

