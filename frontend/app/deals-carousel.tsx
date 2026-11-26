'use client';

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

function ControlIcon({ path }: { path: string }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

export default function DealsCarousel({ children, total, items, percent, days }: {
  children: ReactNode; total: number; items: number; percent: number; days: number;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [mouse, setMouse] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [paused, setPaused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const pointer = window.matchMedia('(hover: hover) and (pointer: fine)');
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePointer = () => setMouse(pointer.matches);
    const updateMotion = () => {
      setReduced(motion.matches);
      setPaused(motion.matches);
    };
    updatePointer();
    updateMotion();
    pointer.addEventListener('change', updatePointer);
    motion.addEventListener('change', updateMotion);
    return () => {
      pointer.removeEventListener('change', updatePointer);
      motion.removeEventListener('change', updateMotion);
    };
  }, []);

  const go = useCallback((direction: number) => {
    const element = track.current;
    if (!element || !element.firstElementChild) return;
    const atEnd = element.scrollLeft + element.clientWidth >= element.scrollWidth - 4;
    const behavior = reduced ? 'auto' : 'smooth';
    if (direction > 0 && atEnd) element.scrollTo({ left: 0, behavior });
    else if (direction < 0 && element.scrollLeft <= 4) element.scrollTo({ left: element.scrollWidth, behavior });
    else {
      const step = element.firstElementChild.getBoundingClientRect().width
        + (parseFloat(window.getComputedStyle(element).columnGap) || 0);
      element.scrollBy({ left: direction * step, behavior });
    }
  }, [reduced]);

  const controls = mouse && items > 1;
  useEffect(() => {
    if (!controls || paused || reduced || hovered || focused) return;
    const timer = window.setInterval(() => go(1), 5000);
    return () => window.clearInterval(timer);
  }, [controls, paused, reduced, hovered, focused, go]);

  return (
    <section className={`deals${controls ? ' js' : ''}`} data-deals="" aria-label="Ofertas detectadas"
      onPointerEnter={event => { if (event.pointerType === 'mouse') setHovered(true); }}
      onPointerLeave={event => { if (event.pointerType === 'mouse') setHovered(false); }}
      onFocus={() => setFocused(true)}
      onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false); }}>
      <div className="deals-head">
        <h2>Ofertas detectadas</h2>
        <a className="link deals-all" href="/explorar?oferta=1&orden=descuento">
          Ver las {new Intl.NumberFormat('es-CL').format(total)} ofertas
        </a>
        {controls && (
          <div className="deals-ctl">
            <button type="button" className="btn btn-ghost btn-icon" aria-label="Ofertas anteriores" onClick={() => go(-1)}>
              <ControlIcon path="m15 6-6 6 6 6" />
            </button>
            <button type="button" className="btn btn-ghost btn-icon" aria-label="Más ofertas" onClick={() => go(1)}>
              <ControlIcon path="m9 6 6 6-6 6" />
            </button>
            {!reduced && (
              <button type="button" className="btn btn-ghost btn-icon"
                aria-label={paused ? 'Reanudar' : 'Pausar'} onClick={() => setPaused(value => !value)}>
                <ControlIcon path={paused ? 'm8 5 11 7-11 7z' : 'M9 6v12M15 6v12'} />
              </button>
            )}
          </div>
        )}
      </div>
      <div className="deals-track" ref={track} tabIndex={0} aria-label="Productos rebajados: desliza para ver más">
        {children}
      </div>
      <p className="deals-note">
        Bajas de al menos {percent}% frente al precio más alto que Yumori vio en cada tienda en
        los últimos {days} días. No es publicidad ni una promoción informada por las tiendas.
      </p>
    </section>
  );
}
