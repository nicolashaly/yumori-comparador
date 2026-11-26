import type { Metadata } from 'next';
import { site, type Query } from './api';

// Origen público (ej. https://yumori.cl). Sin él el sitio sigue siendo el piloto: noindex y sin sitemap.
export const SITE_URL = (process.env.YUMORI_URL || '').replace(/\/+$/, '');
export const INDEXABLE = SITE_URL !== '';
export const SITE_DESC = 'Compara precios de skincare, maquillaje y cuidado personal coreano, japonés y chino en tiendas de Chile, y encuentra dónde está más barato.';

export const abs = (path: string) => SITE_URL + path;
export const clip = (text: string, n = 158) => text.length <= n ? text : text.slice(0, n).replace(/\s+\S*$/, '').replace(/[,;:·]+$/, '') + '…';
// Escapa < > & y los separadores de línea Unicode: el JSON sigue válido y un texto con "</script>" no cierra la etiqueta.
const BACKSLASH = String.fromCharCode(92);
export const jsonLd = (data: unknown) => JSON.stringify(data).replace(/[<>&\u2028\u2029]/g, c => `${BACKSLASH}u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);

// Indexables: el listado general, por marca y por categoría (con su página). Búsquedas, filtros y orden son
// combinaciones casi infinitas del mismo contenido: noindex,follow para que sus enlaces a productos se sigan.
// Por marca o categoría el título y la descripción las nombran (si no, cientos de páginas comparten título),
// y una marca o categoría que no existe lleva noindex. `scope` distingue la sección: "COSRX (packs y sets)".
export function listingMeta(baseTitle: string, baseDescription: string, base: string, scope = '') {
  return async ({ searchParams }: { searchParams: Promise<Query> }): Promise<Metadata> => {
    // Locales a cada solicitud: reasignar los parámetros de listingMeta dejaba el título de una marca a las visitas siguientes.
    let title = baseTitle, description = baseDescription;
    const query = await searchParams;
    const first = (key: string) => { const v = query[key]; return (Array.isArray(v) ? v[0] : v) || ''; };
    const used = Object.entries(query).filter(([, v]) => [v].flat().some(x => x?.trim())).map(([k]) => k);
    // Solo un entero positivo es página ("2.5" o "1e3" no van al título ni a la canónica, y llevan noindex).
    const pageNumber = /^\d{1,6}$/.test(first('pagina')) ? Number(first('pagina')) : 0;
    let clean = used.every(k => ['marca', 'cat', 'pagina'].includes(k)) && (!first('pagina') || pageNumber >= 1);
    const params = new URLSearchParams();
    for (const key of ['cat', 'marca']) if (first(key)) params.set(key, first(key));
    if (pageNumber > 1) params.set('pagina', String(pageNumber));
    const canonical = base + (params.size ? `?${params}` : '');
    if (first('marca') || first('cat')) {
      const data = await site().catch(() => null);
      if (!data) clean = false;  // sin catálogo no se puede validar la marca ni la categoría: noindex
      else {
        // Igual que explorer.tsx: dermocosmética y asiática tienen sus marcas; los eventos, ambas.
        const brands = base.startsWith('/dermocosmetica') ? data.brands.dermocosmetica : ['/explorar', '/packs'].includes(base) ? data.brands.asiatica : [...data.brands.asiatica, ...data.brands.dermocosmetica];
        const brand = first('marca') ? brands.find(b => b.slug === first('marca')) : undefined;
        const category = first('cat') ? data.categories.find(c => c.slug === first('cat')) : undefined;
        if ((first('marca') && !brand) || (first('cat') && !category)) clean = false;
        else {
          const subject = [category?.name, brand?.name].filter(Boolean).join(' ') + (scope ? ` (${scope})` : '');
          const page = pageNumber > 1 ? `, página ${pageNumber}` : '';
          title = `${subject}: precios en Chile${page}`;
          description = `Compara precios de ${subject} en tiendas de Chile y encuentra dónde está más barato, con el historial de precios de cada producto.`;
        }
      }
    }
    return {
      title, description: clip(description), alternates: { canonical },
      openGraph: { title, description: clip(description, 200), url: canonical },
      ...(clean ? {} : { robots: { index: false, follow: true } }),
    };
  };
}
