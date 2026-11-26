'use client';
import { useState } from 'react';
import { safeUrl } from '../lib/display';
export default function ProductImage({ src, alternatives = [], name, large = false }: { src: string | null; alternatives?: string[]; name: string; large?: boolean }) {
  const urls = [...new Set([src, ...alternatives].filter((url): url is string => !!safeUrl(url)))];
  const [index, setIndex] = useState(0);
  return urls[index] ? <img className="loaded" src={urls[index]} alt={name} loading={large ? 'eager' : 'lazy'} decoding="async" referrerPolicy="no-referrer" onError={() => setIndex(value => value + 1)} /> : <span className="no-img">Sin imagen</span>;
}
