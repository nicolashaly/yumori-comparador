import type { MetadataRoute } from 'next';
export const dynamic = 'force-dynamic';
import { INDEXABLE, abs } from '../lib/seo';
export default function robots(): MetadataRoute.Robots {
  if (!INDEXABLE) return { rules: { userAgent: '*', disallow: '/' } };
  return { rules: { userAgent: '*', allow: '/', disallow: ['/favoritos', '/api/'] }, sitemap: abs('/sitemap.xml') };
}
