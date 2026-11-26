'use client';
import { useEffect, useState } from 'react';
import { KEY, readFavorites, validateIds } from '../lib/favorites.mjs';
import Icon from './ui-icon';
export const CHANGED = 'yumori-favorites-changed';
export function changed() { window.dispatchEvent(new Event(CHANGED)); }
export function FavoriteCount() {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    const paint = () => { try { setCount(readFavorites(localStorage).length); } catch { setCount(null); } };
    const storage = (event: StorageEvent) => { if (event.key === KEY || event.key === null) paint(); };
    paint(); window.addEventListener(CHANGED, paint); window.addEventListener('storage', storage);
    return () => { window.removeEventListener(CHANGED, paint); window.removeEventListener('storage', storage); };
  }, []);
  return count ? <span className="fav-count">{count}</span> : null;
}
export function FavoriteButton({ id, name, variant = 'product' }: { id: string; name: string; variant?: 'product' | 'card' }) {
  const [saved, setSaved] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const paint = () => { try { setSaved(readFavorites(localStorage).includes(id)); setReady(true); } catch { setError('No se pudo leer la lista guardada.'); } };
    const storage = (event: StorageEvent) => { if (event.key === KEY || event.key === null) paint(); };
    paint(); window.addEventListener(CHANGED, paint); window.addEventListener('storage', storage);
    return () => { window.removeEventListener(CHANGED, paint); window.removeEventListener('storage', storage); };
  }, [id]);
  function toggle() {
    try { const ids = readFavorites(localStorage); localStorage.setItem(KEY, JSON.stringify(validateIds(ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id]))); changed(); setError(''); }
    catch { setError('No se pudo guardar. Tu lista anterior se conserva.'); }
  }
  return <><button className={variant === 'card' ? 'fav' : 'btn btn-soft btn-lg fav-btn'} type="button" data-fav={id} aria-pressed={saved} aria-label={`${saved ? 'Quitar' : 'Guardar'} ${name} en favoritos`} disabled={!ready} onClick={toggle}><Icon name="heart" />{variant !== 'card' && <span className="label">{saved ? 'Guardado' : 'Guardar'}</span>}</button>{error && <small className="favorite-error" role="alert">{error}</small>}</>;
}
