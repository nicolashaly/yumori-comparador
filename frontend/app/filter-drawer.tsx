'use client';

import { createContext, useContext, useEffect, useRef, useState } from 'react';

const DrawerContext = createContext<{ open: boolean; show: () => void; close: () => void }>({ open: false, show: () => {}, close: () => {} });

export function FilterToggle() {
  const drawer = useContext(DrawerContext);
  return <button type="button" className="btn btn-soft btn-sm filters-toggle" aria-controls="ff" aria-expanded={drawer.open} onClick={drawer.show}>
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 7h16M7 12h10M10 17h4" /></svg>Filtros
  </button>;
}

export function FilterClose() {
  const drawer = useContext(DrawerContext);
  return <button type="button" className="btn btn-ghost btn-icon" aria-label="Cerrar filtros" onClick={drawer.close}>
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
  </button>;
}

export default function FilterDrawer({ action, filters, children }: { action: string; filters: React.ReactNode; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const close = () => setOpen(false);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 1024px)');
    const change = () => { setMobile(query.matches); if (!query.matches) setOpen(false); };
    change(); query.addEventListener('change', change);
    return () => query.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    if (!open || !mobile) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const focusFirst = () => form.current?.querySelector<HTMLElement>('button, input:not([type="hidden"]), select, summary, a[href]')?.focus();
    const retainFocus = (event: FocusEvent) => {
      if (event.target instanceof Node && !form.current?.contains(event.target)) focusFirst();
    };
    focusFirst();
    document.addEventListener('focusin', retainFocus);
    return () => {
      document.removeEventListener('focusin', retainFocus);
      document.body.style.overflow = overflow;
      previousFocus.current?.focus();
    };
  }, [open, mobile]);
  return <DrawerContext.Provider value={{ open, close, show: () => { previousFocus.current = document.activeElement as HTMLElement; setOpen(true); } }}>
    <div className="explore" onChange={event => {
      if (event.target instanceof HTMLSelectElement && event.target.id === 'sort') form.current?.requestSubmit();
    }}>
      <div className={`overlay${open ? ' open' : ''}`} aria-hidden="true" onClick={close} />
      <form action={action} method="get" className={`filters${open ? ' open' : ''}`} id="ff" ref={form}
        inert={mobile && !open} role={mobile && open ? 'dialog' : undefined} aria-modal={mobile && open ? true : undefined} aria-labelledby={mobile && open ? 'filters-title' : undefined}
        onKeyDown={event => {
          if (!mobile || !open) return;
          if (event.key === 'Escape') { event.preventDefault(); close(); }
          if (event.key !== 'Tab') return;
          const elements = Array.from(form.current?.querySelectorAll<HTMLElement>('button, input:not([type="hidden"]), select, summary, a[href]') || []).filter(element => element.getClientRects().length > 0 && !element.hasAttribute('disabled'));
          const first = elements[0], last = elements.at(-1);
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }}>
        <div className="filters-head"><h2 id="filters-title">Filtros</h2><FilterClose /></div>{filters}
      </form>
      <div className="results" inert={mobile && open}>{children}</div>
    </div>
  </DrawerContext.Provider>;
}
