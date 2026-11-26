import Favorites from '../favorites-client';
export const metadata = { title: 'Favoritos', robots: { index: false, follow: true } };  // la lista vive en el navegador de cada persona
export default function FavoritesPage() { return <Favorites />; }
