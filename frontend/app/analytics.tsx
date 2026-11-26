'use client';
import { useEffect, useState } from 'react';

const KEY = 'yumori:consent';  // 'si' | 'no'; sin valor = aún no eligió
type W = { dataLayer?: unknown[]; [k: string]: unknown };
const win = () => window as unknown as W;

// Google Analytics solo se carga si la persona aceptó; rechazar o no elegir deja el sitio sin rastreo.
function load(id: string) {
  const w = win();
  w[`ga-disable-${id}`] = false;
  if (document.getElementById('gtag-js')) return;
  w.dataLayer = w.dataLayer || [];
  function gtag(..._: unknown[]) { w.dataLayer!.push(arguments); }  // gtag.js solo lee objetos `arguments`, no arreglos
  gtag('js', new Date());
  gtag('config', id);
  const s = document.createElement('script');
  s.id = 'gtag-js';
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
  document.head.appendChild(s);
}

function unload(id: string) {
  win()[`ga-disable-${id}`] = true;
  const host = location.hostname;
  for (const name of document.cookie.split(';').map(c => c.split('=')[0].trim()).filter(n => n === '_ga' || n.startsWith('_ga_'))) {
    for (const domain of ['', `;domain=${host}`, `;domain=.${host.replace(/^www\./, '')}`]) document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/${domain}`;
  }
}

// `legal`: LEGAL_VISIBLE; mientras /cookies esté oculta (404) el aviso no la enlaza.
export default function Analytics({ id, legal }: { id: string; legal: boolean }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(KEY); } catch {}
    if (saved === 'si') load(id); else if (saved !== 'no') setOpen(true);
  }, [id]);
  function choose(v: 'si' | 'no') {
    try { localStorage.setItem(KEY, v); } catch {}
    setOpen(false);
    if (v === 'si') load(id); else unload(id);
  }
  return <>
    <button type="button" className="cookie-pref" onClick={() => setOpen(true)}>Preferencias de cookies</button>
    {open && <div className="cookie-banner" role="region" aria-label="Cookies de analítica">
      <p>Usamos Google Analytics, con tu permiso, para saber cómo se usa el sitio. Pone cookies y envía datos de uso a Google. Si rechazas, el sitio funciona igual.{legal && <> <a href="/cookies">Más información</a></>}</p>
      <div><button type="button" onClick={() => choose('no')}>Rechazar</button><button type="button" onClick={() => choose('si')}>Aceptar</button></div>
    </div>}
  </>;
}
