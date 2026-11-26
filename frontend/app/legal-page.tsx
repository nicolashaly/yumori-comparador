import { ApiError, LegalDocument, type LegalInline, safeUrl, site } from '../lib/api';
import { notFound } from 'next/navigation';
import { Failure } from './components';

// Ocultas hasta completar los datos del titular; poner en true para reactivarlas (páginas y enlaces del pie).
export const LEGAL_VISIBLE = false;

function inlineHref(value: string | undefined) {
  if (!value) return undefined;
  if (['/privacidad', '/terminos', '/cookies'].includes(value)) return value;
  if (/^mailto:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(value)) return value;
  return safeUrl(value);
}

function Inline({ nodes }: { nodes: LegalInline[] }) {
  return nodes.map((node, index) => {
    if ('text' in node) return <span key={index}>{node.text}</span>;
    const children = <Inline nodes={node.children} />;
    if (node.tag === 'strong') return <strong key={index}>{children}</strong>;
    if (node.tag === 'em') return <em key={index}>{children}</em>;
    if (node.tag === 'code') return <code key={index}>{children}</code>;
    const href = node.tag === 'a' ? inlineHref(node.href) : undefined;
    return href ? <a className="link" key={index} href={href}>{children}</a> : <span key={index}>{children}</span>;
  });
}

function Content({ block }: { block: LegalDocument['blocks'][number] }) {
  return block.inline ? <Inline nodes={block.inline} /> : block.text;
}

function Blocks({ blocks }: { blocks: LegalDocument['blocks'] }) {
  const rendered: React.ReactNode[] = [];
  for (let index = 0; index < blocks.length; index++) {
    const block = blocks[index];
    if (block.tag === 'h1' || block.text.startsWith('Última actualización:')) continue;
    if (block.tag === 'li') {
      const items = [block];
      while (blocks[index + 1]?.tag === 'li') items.push(blocks[++index]);
      rendered.push(<ul key={index}>{items.map((item,position) => <li key={position}><Content block={item} /></li>)}</ul>);
    } else if (block.tag === 'th' || block.tag === 'td') {
      const cells = [block];
      while (['th','td'].includes(blocks[index + 1]?.tag)) cells.push(blocks[++index]);
      const headings = cells.filter(cell => cell.tag === 'th');
      const values = cells.filter(cell => cell.tag === 'td');
      const columns = headings.length || 1;
      const rows: LegalDocument['blocks'][] = [];
      for (let position = 0; position < values.length; position += columns) rows.push(values.slice(position, position + columns));
      rendered.push(<div className="table-wrap" key={index}><table>{headings.length > 0 && <thead><tr>{headings.map((cell,col) => <th scope="col" key={col}><Content block={cell} /></th>)}</tr></thead>}<tbody>{rows.map((row,rowIndex) => <tr key={rowIndex}>{row.map((cell,col) => <td key={col}><Content block={cell} /></td>)}</tr>)}</tbody></table></div>);
    } else if (block.tag === 'h2') rendered.push(<h2 key={index}><Content block={block} /></h2>);
    else rendered.push(<p key={index}><Content block={block} /></p>);
  }
  return rendered;
}

export default async function LegalPage({ slug }: { slug: 'privacidad' | 'terminos' | 'cookies' }) {
  if (!LEGAL_VISIBLE) notFound();
  let data; try { data = await site(); } catch (error) { if (error instanceof ApiError) return <Failure message={error.message} />; throw error; }
  const page = data.legal[slug];
  return <article className="container legal"><div className="page-head"><h1>{page.title}</h1><p className="muted">Última actualización: {page.updated}</p></div>{data.operator_missing_fields.length > 0 && <aside className="callout"><strong>Antes de publicar el sitio:</strong> faltan datos del titular ({data.operator_missing_fields.join(', ')}).</aside>}<Blocks blocks={page.blocks} /></article>;
}
