'use client';

import { useState } from 'react';
import { safeUrl } from '../lib/display';
import ProductImage from './product-image';

export default function ProductGallery({ images, src, alternatives, name }: {
  images: string[]; src: string | null; alternatives: string[]; name: string;
}) {
  const urls = [...new Set([src, ...images].filter((url): url is string => !!safeUrl(url)))];
  const [selected, setSelected] = useState(0);
  return <div className="gallery">
    <div className="product-img">
      <ProductImage key={urls[selected] || 'empty'} src={urls[selected] || null} alternatives={selected === 0 ? alternatives : []}
        name={urls.length > 1 ? `${name}, imagen ${selected + 1} de ${urls.length}` : name} large />
    </div>
    {urls.length > 1 && <div className="thumbs" aria-label="Imágenes del producto">{urls.map((url, index) =>
      <button type="button" className="thumb" key={url} aria-label={`Ver imagen ${index + 1} de ${urls.length}`}
        aria-current={selected === index ? 'true' : undefined} onClick={() => setSelected(index)}>
        <img src={url} alt="" loading="lazy" referrerPolicy="no-referrer" width={68} height={68} />
      </button>)}</div>}
  </div>;
}
