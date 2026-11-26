import { ApiError, favorites } from '../../../lib/api';
export async function GET(request: Request) {
  const url = new URL(request.url);
  if ([...url.searchParams.keys()].some(key => key !== 'ids') || url.searchParams.getAll('ids').length !== 1) return Response.json({ error: 'Parámetros inválidos' }, { status: 400 });
  const raw = url.searchParams.get('ids') || '';
  if (raw.length > 1099 || raw.split(',').length > 100 || !/^[0-9a-f]{10}(,[0-9a-f]{10})*$/.test(raw)) return Response.json({ error: 'Ids inválidos' }, { status: 400 });
  try { return Response.json(await favorites(raw.split(',')), { headers: { 'Cache-Control': 'no-store' } }); }
  catch (error) { return Response.json({ error: 'No se pudieron cargar los favoritos' }, { status: error instanceof ApiError ? error.status : 503 }); }
}
