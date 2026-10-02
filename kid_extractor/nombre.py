"""Nombre del fondo y su clase, leído por la IA local y validado.

Cada gestora escribe el nombre a su manera (PIMCO pone el subfondo, luego el
paraguas y luego la clase), así que no sirve una regla fija. La IA lee la
sección «Producto» de la primera página, pero lo que devuelve SOLO se acepta
si cada pieza aparece palabra por palabra en el PDF: la IA no puede inventarse
un nombre; como mucho puede escoger mal un trozo de texto real.
"""

from __future__ import annotations

import re
import unicodedata

from . import ia

# El título de la sección va con mayúscula ("Producto", "PRODUCT"); en minúscula
# la palabra sale antes, en la "Finalidad" ("producto de inversión").
RE_SECCION_PRODUCTO = re.compile(r"\b(?:Producto|Product|Produit|Produkt|PRODUCTO|PRODUCT|PRODUIT|PRODUKT)\b")
LARGO_SECCION_PRODUCTO = 1000
# Etiquetas que la IA a veces deja delante de la clase ("Clase de acciones: NC").
RE_ETIQUETA_CLASE = re.compile(
    r"^(?:clase de (?:acciones|participaciones)|share class|class|classe(?: d'actions| de parts)?"
    r"|anteilklasse|serie de participaciones)\s*:\s*", re.I)
# Coletillas que algunas gestoras ponen tras el nombre y no son parte de la
# clase: "R2 USD Un Subfondo de Amundi Funds" · "Acciones de acumulación con
# n.º ISIN LU1582988488" (NFKC deja "n.o").
RE_COLETILLA = re.compile(
    r"[\s,]*\bcon (?:el )?(?:n\.?\s?[oº°]\.?|n[úu]mero|c[óo]digo)(?:\s*ISIN)?$"
    r"|[\s,(-]*\b(?:un )?(?:subfondo|compartimento) de\b.*$|[\s,(-]*\ba sub-?fund of\b.*$"
    r"|[\s,(-]*\b(?:un )?compartiment de\b.*$|[\s,(-]*\bein teilfonds (?:des|der|von)\b.*$", re.I)
# El ISIN no es parte del nombre: "AXA IM FIIS ... A EUR (LU0658025209)".
RE_ISIN_EN_NOMBRE = re.compile(r"\s*\(?\b[A-Z]{2}[A-Z0-9]{9}\d\b\)?")
# La IA a veces mete la clase en el subfondo y deja la clase vacía:
# "AMUNDI FUNDS CASH USD - R2 USD". Se acepta si tras el último " - " hay algo
# corto con una divisa, que es como se nombran las clases.
RE_CLASE_EN_SUBFONDO = re.compile(
    r"(.+?) - ([^-]{0,15}\b(?:EUR|USD|GBP|CHF|JPY|SEK|NOK|DKK)\b[^-]{0,10})")
ESQUEMA_NOMBRE = {
    "type": "object",
    "properties": {"paraguas": {"type": "string"}, "subfondo": {"type": "string"},
                   "clase": {"type": "string"}},
    "required": ["paraguas", "subfondo", "clase"],
}
PROMPT_NOMBRE = """Extracto de la sección "Producto" de un Documento de Datos Fundamentales (KID) de un fondo de inversión. Extrae tres piezas del nombre, copiando las palabras exactamente como aparecen en el texto (sin traducir, sin añadir nada):
- "paraguas": la SICAV o estructura paraguas de la que el fondo es subfondo (p.ej. "PIMCO Funds: Global Investors Series plc", "Storm Fund II", "FIDELITY FUNDS"). Vacío si no hay.
- "subfondo": el nombre del fondo en sí (p.ej. "Income Fund", "Storm Bond Fund", "Vanguard European Stock Index Fund", "GLOBAL TECHNOLOGY FUND").
- "clase": la clase de participaciones o acciones (p.ej. "Institutional EUR (Hedged) Accumulation", "IC (EUR)", "EUR Accumulation Shares", "Y-ACC-EURO (HEDGED)"). Vacío si no aparece.
Responde solo con JSON.

ISIN de la clase: {isin}
Texto:
{texto}"""


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", texto)).strip().lower()


def leer_nombre(pagina1: str, isin: str, modelo: str = ia.MODELO) -> str | None:
    """Nombre del fondo con su clase. None si alguna pieza no aparece literal
    en el texto. Lanza ia.IANoDisponible si Ollama no responde."""
    m = RE_SECCION_PRODUCTO.search(pagina1)
    inicio = m.start() if m else 0
    pos_isin = pagina1.find(isin)
    # Si el ISIN va muy detrás, se amplía el recorte para incluirlo.
    fin = max(inicio + LARGO_SECCION_PRODUCTO, pos_isin + 100 if pos_isin >= 0 else 0)
    piezas = _nombre_de(pagina1, pagina1[inicio:fin], isin, modelo)
    # Algunos KID ponen el nombre en la cabecera, antes de la sección
    # "Producto": si no ha salido, se prueba desde el principio.
    if piezas is None and 0 <= pos_isin < inicio:
        piezas = _nombre_de(pagina1, pagina1[:max(LARGO_SECCION_PRODUCTO, pos_isin + 100)], isin, modelo)
    return "".join(piezas).strip() if piezas else None


def _nombre_de(pagina1: str, seccion: str, isin: str, modelo: str) -> tuple[str, str, str] | None:
    """(fondo, separador, clase) leídos por la IA en `seccion`, validados
    contra la página entera."""
    d = ia.extraer_json(PROMPT_NOMBRE.format(isin=isin, texto=seccion), ESQUEMA_NOMBRE, modelo)
    paraguas, subfondo, clase = (str(d.get(k) or "").strip() for k in ("paraguas", "subfondo", "clase"))
    clase = RE_ISIN_EN_NOMBRE.sub("", RE_COLETILLA.sub("", RE_ETIQUETA_CLASE.sub("", clase))).strip()
    subfondo = RE_ISIN_EN_NOMBRE.sub("", subfondo).strip()
    texto = _normalizar(pagina1)

    def literal(pieza: str) -> bool:
        # Palabras completas: "BlackRock Global Fu" (cortado) no vale.
        return re.search(r"(?<!\w)" + re.escape(_normalizar(pieza)) + r"(?!\w)", texto) is not None

    if not subfondo or not literal(subfondo):
        return None
    separador = " "
    if not clase:
        clase = _clase_junto_al_isin(pagina1, subfondo, isin)
    if not clase:
        m = RE_CLASE_EN_SUBFONDO.fullmatch(subfondo)
        if m:
            subfondo, clase, separador = m.group(1).strip(), m.group(2).strip(), " - "
    # Sin clase el nombre no distingue retail/limpia/institucional: no vale.
    if not clase or not literal(clase):
        return None
    if paraguas and not literal(paraguas):
        paraguas = ""   # opcional: si no es literal, mejor sin él
    # Si el subfondo no lleva la marca del paraguas ("Income Fund"), se antepone.
    marca = paraguas.split()[0].lower() if paraguas else ""
    base = subfondo if not paraguas or marca in subfondo.lower() else f"{paraguas} - {subfondo}"
    return base, separador, clase


def _clase_junto_al_isin(pagina1: str, subfondo: str, isin: str) -> str:
    """La IA a veces se salta una clase corta pegada al ISIN: en
    "Robeco BP Global Premium Equities FH EUR (LU1736383024)" la clase es lo
    que hay entre el nombre del fondo y el ISIN. Vacío si no hay nada claro."""
    pos_isin = pagina1.find(isin)
    pos_fondo = pagina1.lower().rfind(subfondo.lower(), 0, max(pos_isin, 0))
    if pos_isin < 0 or pos_fondo < 0:
        return ""
    hueco = pagina1[pos_fondo + len(subfondo):pos_isin]
    hueco = re.sub(r"(?:\bISIN\b)?[\s:(,\-]*$", "", hueco).strip(" -,:")
    hueco = RE_COLETILLA.sub("", hueco).strip(" -,:")
    return hueco if 0 < len(hueco) <= 40 and not re.search(r"[.;«»\"]", hueco) else ""
