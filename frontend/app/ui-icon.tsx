export default function Icon({ name }: { name: 'heart' | 'search' | 'menu' | 'close' | 'filter' | 'arrow' }) {
  const paths = {
    heart: <path d="M12 20s-7-4.4-9.3-9A5.2 5.2 0 0 1 12 6.5 5.2 5.2 0 0 1 21.3 11C19 15.6 12 20 12 20z" />,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    filter: <><path d="M4 7h16M7 12h10M10 17h4" /></>,
    arrow: <path d="m9 5 7 7-7 7" />,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
