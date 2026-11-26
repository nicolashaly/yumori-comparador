"""Marcas de dermocosmética para los adaptadores de tiendas generales (Paris) o de farmacias que no declaran la marca (Novasalud).

Es LA lista de marcas de dermocosmética: `catalog.DERMO_BRANDS` se arma desde aquí. Una tienda que no es farmacia (Paris) y vende una
marca que no está en esta lista la deja en la sección asiática del sitio.
"""
import re
import unicodedata

BRANDS = ("Eucerin", "La Roche-Posay", "Vichy", "Avène", "Cetaphil", "ISDIN", "Uriage", "Ducray", "CeraVe", "Bioderma", "Apivita", "Heliocare", "Nuxe",
          "SVR", "Sesderma", "Filorga", "A-Derma", "Mustela")


def words(text):
    """Palabras en minúscula y sin tildes: "Avène" y "Avéne" (como lo escribe Paris) dan lo mismo."""
    return re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower())


CANON = {" ".join(words(b)): b for b in BRANDS}  # "la roche posay" -> "La Roche-Posay"
CANON["roche posay"] = "La Roche-Posay"
IN_TEXT = re.compile(r"\b(" + "|".join(sorted(CANON, key=len, reverse=True)) + r")\b")  # la más larga primero: "la roche posay" antes que "roche posay"


def brand_of(name):
    """El nombre exacto de una marca de la lista ("Cerave" -> "CeraVe", "La Roche Posay" -> "La Roche-Posay"), o None si no es una de ellas."""
    return CANON.get(" ".join(words(name)))


def brand_in(text):
    """La primera marca de la lista que aparece como palabra en un texto (título o slug de URL), o None. Sirve para tiendas sin campo de marca."""
    m = IN_TEXT.search(" ".join(words(text)))
    return CANON[m.group(1)] if m else None
