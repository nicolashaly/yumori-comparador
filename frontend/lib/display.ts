import type { Money } from './api';
export function safeUrl(value: string | null) {
  if (!value || /[\x00-\x20]/.test(value)) return undefined;
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? value : undefined; } catch { return undefined; }
}
export function money(value: Money | null) {
  if (!value) return 'Precio por confirmar';
  const amount = new Intl.NumberFormat('es-CL', { minimumFractionDigits: value.decimals, maximumFractionDigits: value.decimals }).format(value.amount / 10 ** value.decimals);
  return `${value.currency === 'USD' ? 'US$' : '$'}${amount}`;
}
