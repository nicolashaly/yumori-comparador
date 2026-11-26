import { ApiError, suggestions } from '../../../lib/api';
export async function GET(request: Request) {
  const url = new URL(request.url);
  if ([...url.searchParams.keys()].some(key => key !== 'q') || url.searchParams.getAll('q').length !== 1 || (url.searchParams.get('q') || '').length > 200) return Response.json({ error: 'Búsqueda inválida' }, { status: 400 });
  try { return Response.json(await suggestions(url.searchParams.get('q') || ''), { headers: { 'Cache-Control': 'no-store' } }); }
  catch (error) { return Response.json({ error: 'No se pudieron cargar sugerencias' }, { status: error instanceof ApiError ? error.status : 503 }); }
}
