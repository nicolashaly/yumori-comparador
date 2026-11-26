import { NextRequest, NextResponse } from 'next/server';
import { createLimiter } from './lib/rate-limit.mjs';

const allow = createLimiter(180, 60_000);  // por IP y minuto, solo en /api/ (las rutas que consultan el catálogo)

export function proxy(request: NextRequest) {
  // Caddy reemplaza X-Forwarded-For por la IP real del cliente, así que no se puede falsear desde fuera.
  if (request.nextUrl.pathname.startsWith('/api/') && !allow(request.headers.get('x-forwarded-for')?.split(',')[0].trim() || 'local')) {
    return new NextResponse(JSON.stringify({ error: 'Demasiadas solicitudes' }), { status: 429, headers: { 'Content-Type': 'application/json', 'Retry-After': '60', 'Cache-Control': 'no-store' } });
  }
  const nonce = btoa(crypto.randomUUID());
  const ga = process.env.GA_MEASUREMENT_ID;  // con analítica se abren solo los dominios de Google que gtag.js necesita
  const csp = `default-src 'self'; script-src 'self' 'nonce-${nonce}'${ga ? ' https://www.googletagmanager.com' : ''}; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'${ga ? ' https://www.googletagmanager.com https://*.google-analytics.com https://*.analytics.google.com' : ''}; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'`;
  const headers = new Headers(request.headers);
  headers.set('Content-Security-Policy', csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set('Content-Security-Policy', csp);
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  response.headers.set('Strict-Transport-Security', 'max-age=2592000');  // 30 días de partida; subir a un año cuando pase un mes sin problemas de HTTPS
  response.headers.set('Cache-Control', 'no-store');
  return response;
}

export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };
