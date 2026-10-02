"""Lee un KID en PDF y devuelve su ficha: nombre, ISIN, fecha, idioma,
riesgo (SRI 1-7), TER y una breve descripción de en qué invierte.

- ISIN, fecha, idioma, riesgo y TER: reglas fijas (`reglas.py`), sin IA.
- Nombre: IA local, validado palabra por palabra contra el PDF (`nombre.py`).
- Descripción: la IA local resume el apartado «Objetivos». Sin IA, se da un
  extracto literal de ese apartado.

Los PDF solo se leen: nunca se mueven, modifican ni envían a ningún sitio.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import ia, reglas
from .nombre import leer_nombre

ESQUEMA_RESUMEN = {
    "type": "object",
    "properties": {"descripcion": {"type": "string"}},
    "required": ["descripcion"],
}
PROMPT_RESUMEN = """Texto del apartado "Objetivos" del Documento de Datos Fundamentales (KID) de un fondo de inversión. Resume EN ESPAÑOL, en una o dos frases (máximo 45 palabras), en qué invierte el fondo: tipo de activo (acciones, bonos, mixto, monetario...), zona geográfica, sector o estilo si lo hay, y si replica un índice o es de gestión activa.
Usa solo lo que dice el texto: no añadas opiniones, rentabilidades ni datos que no aparezcan. Empieza directamente por "Invierte en..." o "Replica...".
Responde solo con JSON.

Texto:
{texto}"""
LARGO_EXTRACTO = 300  # caracteres del extracto literal cuando no hay IA


@dataclass
class Ficha:
    archivo: str
    isin: str | None = None
    otros_isin: list[str] = field(default_factory=list)  # KID que cubren varias clases
    nombre: str | None = None
    fecha: date | None = None
    idioma: str | None = None
    sri: int | None = None
    ter: float | None = None          # %
    descripcion: str | None = None
    descripcion_ia: bool = False      # False: extracto literal, sin resumir
    avisos: list[str] = field(default_factory=list)
    huella: str | None = None         # sha256 del PDF: lo identifica en la base de datos
    con_ia: bool = False              # leído con Ollama


def analizar(ruta: Path, usar_ia: bool = True, modelo: str = ia.MODELO) -> Ficha:
    """Ficha del KID. Lo que no se puede leer con seguridad queda en None y
    se explica en `avisos`."""
    f = Ficha(archivo=ruta.name, con_ia=usar_ia)
    try:
        f.huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
        pagina1, todo = reglas.texto_pdf(ruta)
    except Exception as e:  # PDF dañado o protegido
        f.avisos.append(f"no se puede abrir el PDF ({e.__class__.__name__})")
        return f
    if len(todo) < 200:
        f.avisos.append("el PDF no tiene texto (¿escaneado?)")
        return f

    f.idioma = reglas.leer_idioma(pagina1)
    if f.idioma is None:
        f.avisos.append("no parece un KID (no tiene el título del documento)")
    isins = reglas.leer_isins(pagina1) or reglas.leer_isins(todo)
    if isins:
        f.isin, f.otros_isin = isins[0], isins[1:]
    f.fecha = reglas.leer_fecha(pagina1)
    f.sri = reglas.leer_sri(todo)
    f.ter = reglas.leer_ter(todo)
    objetivos = reglas.leer_objetivos(todo)

    if usar_ia and f.isin:
        f.nombre = leer_nombre(pagina1, f.isin, modelo)
    if objetivos:
        if usar_ia:
            f.descripcion = resumir(objetivos, modelo)
            f.descripcion_ia = f.descripcion is not None
        if f.descripcion is None:
            f.descripcion = extracto(objetivos)
            f.avisos.append("descripción sin resumir (extracto literal)")

    faltan = [n for n, v in (("ISIN", f.isin), ("fecha", f.fecha), ("riesgo", f.sri), ("TER", f.ter),
                             ("descripción", f.descripcion)) if v is None]
    if usar_ia and f.nombre is None:
        faltan.insert(0, "nombre")
    if faltan:
        f.avisos.append("no se encuentra: " + ", ".join(faltan))
    return f


def resumir(objetivos: str, modelo: str = ia.MODELO) -> str | None:
    """Resumen en español de en qué invierte el fondo. None si la IA no
    devuelve nada utilizable. Lanza ia.IANoDisponible si Ollama no responde."""
    d = ia.extraer_json(PROMPT_RESUMEN.format(texto=objetivos), ESQUEMA_RESUMEN, modelo)
    resumen = re.sub(r"\s+", " ", str(d.get("descripcion") or "")).strip()
    return resumen or None


def extracto(objetivos: str) -> str:
    """Primeras frases del apartado, cortadas en una palabra completa."""
    if len(objetivos) <= LARGO_EXTRACTO:
        return objetivos
    corte = objetivos[:LARGO_EXTRACTO].rsplit(" ", 1)[0]
    return corte.rstrip(" ,;:") + "…"
