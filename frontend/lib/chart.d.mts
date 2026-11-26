import type { HistoryResponse, Offer } from './api';
type Stores = HistoryResponse['stores'];
type Observation = Stores[number]['observations'][number];
export function instant(value: string): number;
export function cheapest(offers: Pick<Offer, 'store' | 'store_name' | 'status' | 'price'>[], n?: number): string[];
export const RANGES: { dia: number; semana: number; mes: number };
export function windowed(stores: Stores, from: number, to: number, until?: Record<string, number>): { store: string; observations: (Observation & { time: number })[] }[];
export type HistoryChart = {
  width: number; height: number; left: number; right: number; top: number; bottom: number;
  yTicks: { value: number; y: number }[]; xTicks: { time: number; x: number }[];
  series: { store: string; path: string; area: string; points: { x: number; y: number; time: number; amount: number; available: boolean }[] }[];
};
export function historyChart(stores: Stores, options: { from: number; to: number; until?: Record<string, number>; grid?: number[] } & Partial<Pick<HistoryChart, 'width' | 'height' | 'left' | 'right' | 'top' | 'bottom'>>): HistoryChart | null;
