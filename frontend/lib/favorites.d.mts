import type { Product, FavoritesResponse } from './api';
export const KEY: string;
export function validateIds(value: unknown): string[];
export function readFavorites(storage: Pick<Storage, 'getItem'>): string[];
export function importIds(text: string): string[];
export function exportIds(ids: string[]): string;
export function resolveFavorites(ids: string[], request: (batch: string[]) => Promise<FavoritesResponse>): Promise<{ ids: string[]; items: Product[]; missing: string[] }>;
export function commitFavorites(storage: Pick<Storage, 'getItem' | 'setItem'>, before: string[], after: string[]): boolean;
