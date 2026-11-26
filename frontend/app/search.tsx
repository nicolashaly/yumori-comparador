'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import type { SuggestionsResponse } from '../lib/api';
import { money } from '../lib/display';
import Icon from './ui-icon';
import ProductImage from './product-image';

export default function Search({ action }: { action?: string }) {
  const pathname = usePathname();
  const searchAction = action || (pathname.startsWith('/dermocosmetica') ? '/dermocosmetica' : '/explorar');
  const params = useSearchParams();
  const [query, setQuery] = useState(params.get('q') || '');
  const [data, setData] = useState<SuggestionsResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(-1);
  const [error, setError] = useState('');
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.key === '/' && !event.ctrlKey && !event.metaKey && !(event.target instanceof HTMLElement && (event.target.isContentEditable || ['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)))) { event.preventDefault(); input.current?.focus(); }
    };
    document.addEventListener('keydown', shortcut);
    return () => document.removeEventListener('keydown', shortcut);
  }, []);
  useEffect(() => {
    setSelected(-1); setData(null); setError('');
    if (query.trim().length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/suggestions?q=${encodeURIComponent(query)}`, { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error();
        const result = await response.json();
        if (result.version !== 1 || !Array.isArray(result.items) || !Array.isArray(result.sections)) throw new Error();
        if (!controller.signal.aborted) setData(result);
      } catch { if (!controller.signal.aborted) setError('Sin conexión con las sugerencias. Puedes usar Buscar.'); }
    }, 150);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query]);
  const options = data ? [...data.items.map(p => ({ path: `/p/${p.id}`, label: `${p.name} · ${p.section === 'dermocosmetica' ? 'Dermocosmética · ' : ''}${money(p.display_price)}${p.display_is_estimate ? ' estimado' : !p.display_price_confirmed ? ' por confirmar' : ''}` })), ...data.sections.map(section => ({ path: `${section.path}?q=${encodeURIComponent(query)}`, label: `Ver ${section.total === 1 ? 'el resultado' : `los ${section.total.toLocaleString('es-CL')} resultados`} en ${section.section === 'dermocosmetica' ? 'Dermocosmética' : 'Explorar'}` }))] : [];
  return <form action={searchAction} role="search" className="search"><Icon name="search" /><input ref={input} placeholder={pathname === '/' ? 'Busca un producto o una marca…' : 'Buscar productos o marcas…'} aria-label="Buscar" name="q" type="search" autoComplete="off" maxLength={200} role="combobox" aria-autocomplete="list" aria-expanded={open && !!options.length} aria-controls={`${id}-list`} aria-activedescendant={open && selected >= 0 ? `${id}-${selected}` : undefined} value={query} onChange={event => { setQuery(event.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onKeyDown={event => {
    if (event.key === 'Escape') { setOpen(false); setSelected(-1); }
    if (options.length && ['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); setOpen(true); setSelected(value => event.key === 'ArrowDown' ? (value + 1) % options.length : (value - 1 + options.length) % options.length); }
    if (event.key === 'Enter' && open && selected >= 0 && options[selected]) { event.preventDefault(); window.location.assign(options[selected].path); }
  }} /><kbd>/</kbd><ul className="suggest" id={`${id}-list`} role="listbox" aria-label="Sugerencias de productos" hidden={!open || (!options.length && !data)}>{data && !options.length && <li className="sug-empty">No encontramos productos para «{query}».</li>}{options.map((option, index) => { const p = data?.items[index]; return <li key={option.path}><a className={p ? 'sug' : 'sug sug-all'} id={`${id}-${index}`} role="option" aria-selected={selected === index} tabIndex={-1} href={option.path} onMouseDown={event => event.preventDefault()}>{p ? <><span className="sug-body"><span className="sug-name">{p.name}</span><span className="sug-meta">{[p.section === 'dermocosmetica' ? 'Dermocosmética' : '',p.brand,p.variant,p.size,p.card_store_label].filter(Boolean).join(' · ')}</span><span className="sug-price">{p.card_prefix && <small>{p.card_prefix}</small>}{p.display_price ? money(p.display_price) : 'Ver precio'}{p.has_deal && <span className="deal-pill">−{p.drop_percent}%</span>}</span></span><span className="sug-img done"><ProductImage src={p.image} alternatives={p.image_alternatives} name={p.name} /></span></> : option.label}</a></li>; })}</ul>{error && <small className="search-error" role="status">{error}</small>}</form>;
}

