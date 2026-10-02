from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

from pypdf import PdfReader

# pypdf avisa por el log de cada PDF dañado
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

# Título obligatorio del documento en cada idioma.
TITULOS = {
    "es": r"documento de datos fundamentales",
    "en": r"key information document",
    "fr": r"document d.informations? cl[ée]s",
    "de": r"basisinformationsblatt",
}

MESES = {
    # es
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    # en
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    # fr
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
    # de
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "juni": 6, "juli": 7,
    "oktober": 10, "dezember": 12,
}
_MES = "|".join(sorted(MESES, key=len, reverse=True))

# Formatos de fecha: 14.04.2026 · 13/04/2026 · 2026-04-13 · 29 de abril de 2026 ·
# 14. April 2026 · 1er mars 2026 · April 14, 2026.
RE_FECHAS = [
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(rf"\b(\d{{1,2}})(?:er|\.)?\s+(?:de\s+)?({_MES})\s+(?:de\s+)?(\d{{4}})\b", re.I), "d_mes_y"),
    (re.compile(rf"\b({_MES})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I), "mes_d_y"),
]

# Frases que introducen la fecha del documento (la fecha va justo detrás).
CLAVES_FECHA = re.compile(
    r"\b(?:elabor[óo]|fecha de (?:publicaci[óo]n|elaboraci[óo]n|producci[óo]n)|tiene fecha"
    r"|public(?:ad[oa]|[óo])|fecha del documento"
    r"|v[áa]lid[oa] (?:a|desde)|exact[oa] a"
    r"|produced|publi(?:shed|cation)|dated|date of (?:production|publication)"
    r"|accurate as (?:at|of)|valid as (?:at|of)"
    r"|date de (?:production|publication|r[ée]daction)|[ée]tabli le|exactes au|valable au|[àa] jour au"
    r"|datum der erstellung|erstellt am|stand(?: vom)?|g[üu]ltig (?:ab|zum))\b",
    re.I,
)
VENTANA_FECHA = 60  # caracteres tras la frase clave en los que buscar la fecha

# Riesgo: "clase de riesgo 4" · "risk class 4" · "classe de risque 4" · "Risikoklasse 4".
# La cifra puede ir hasta 40 caracteres detrás, sin cruzar un punto ni otra cifra
# ("la categoría de riesgo de este producto se establece en 2").
RE_SRI = re.compile(
    r"(?:(?:clase|categor[íi]a) de riesgo|risk (?:class|category)|(?:classe|cat[ée]gorie) de risque"
    r"|risikoklasse|risikokategorie)[^.\d]{0,40}?(\d)\b", re.I
)
# Alternativa: "4 en una escala de 7" · "4 out of 7" · "4 sur 7" · "4 von 7".
RE_SRI_ESCALA = re.compile(r"\b(\d)\s+(?:en una escala de|out of|on a scale of|sur|von)\s+7\b", re.I)
# "Hemos clasificado este producto como 2 de 7" (el número del gráfico no sale como texto).
RE_SRI_CLASIFICADO = re.compile(r"clasificad[oa][^.\d]{0,60}?\b(\d)\s+de\s+7\b", re.I)

# TER: la fila de costes corrientes "Comisiones de gestión y otros costes
# administrativos o de funcionamiento 1,11%" (y su equivalente en cada idioma).
# Hasta 250 caracteres entre la etiqueta y la cifra: algunas gestoras meten una
# frase o la descripción entera antes de la cifra. Si con eso se alcanza la
# fila siguiente, lo descarta `_es_coste_de_operacion`.
RE_TER = re.compile(
    r"(?:gesti[óo]n y otros (?:costes|gastos)"
    r"|management fees and other"
    r"|frais de gestion et autres"
    r"|verwaltungsgeb[üu]hren und sonstige)"
    r".{0,250}?(\d{1,2}(?:[.,]\d{1,4})?)\s?%",
    re.I,
)
TER_MAXIMO = 5.0  # %: por encima, casi seguro que se ha leído otra cifra
# En PDF con la tabla de costes desordenada la etiqueta del TER puede quedar
# justo antes de la cifra de los COSTES DE OPERACIÓN. Una cifra se descarta si
# entre la etiqueta y ella está la de costes de operación, o si lo que la
# sigue describe la compraventa de las inversiones.
RE_COSTES_OPERACION = re.compile(
    r"costes de operaci[óo]n|(?:costes|gastos) de transacci[óo]n|transaction costs"
    r"|co[ûu]ts de transaction|transaktionskosten", re.I)
RE_COMPRAVENTA = re.compile(
    r"comprar y vender|compra y venta|buy(?:ing)? and sell|achat(?:er)? et (?:de )?vend"
    r"|achetons et vendons|kaufen und verkaufen|kauf und verkauf|an- und verkauf", re.I)
RE_PORCENTAJE = re.compile(r"\d(?:[.,]\d+)?\s?%")
VENTANA_TRAS_TER = 300  # caracteres tras la cifra en los que buscar su descripción
# Respaldo para maquetas con la cifra ANTES de la etiqueta (BNP Paribas):
# "Costes corrientes [detraídos cada año] 191,09 EUR 1,97% del valor de su
# inversión al año. El porcentaje de gastos corrientes ... Comisiones de
# gestión y otros costes ...". Solo se usa si la regla normal no da nada.
RE_TER_ANTES_DE_ETIQUETA = re.compile(
    r"costes corrientes \[?detra[íi]dos cada año\]?\s*[\d.,]+\s*[A-Z]{3}\s+"
    r"(\d{1,2}(?:[.,]\d{1,4})?)\s?% del valor de su inversi[óo]n al año\. "
    r"El porcentaje de gastos corrientes[^%]{0,150}?comisiones de gesti[óo]n y otros costes", re.I)

RE_ISIN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")

# Sección de objetivos / política de inversión: empieza en su título y acaba
# en el siguiente apartado obligatorio (inversor al que va dirigido o riesgos).
# "Objectivos" es una errata real (Evli).
RE_INICIO_OBJETIVOS = re.compile(
    r"\b(?:Obje(?:c)?tivos?|OBJE(?:C)?TIVOS?|Objectives?|OBJECTIVES?|Objectifs?|OBJECTIFS?"
    r"|Anlageziele?|Ziele|ZIELE)\b\s*(?:y pol[íi]tica de inversi[óo]n|and investment policy"
    r"|et politique d.investissement)?\s*:?")
RE_FIN_OBJETIVOS = re.compile(
    r"inversor(?:es)? minorista|tipo de inversor|intended retail investor|retail investor"
    r"|investisseurs? de d[ée]tail|kleinanleger|anlegerzielgruppe"
    r"|¿qu[ée] riesgos|what are the risks|quels sont les risques|welche risiken", re.I)
LARGO_MAXIMO_OBJETIVOS = 2500  # caracteres: lo suficiente para resumir


def isin_valido(isin: str) -> bool:
    """Dígito de control del ISIN (Luhn sobre letras convertidas a números)."""
    digitos = "".join(str(int(c, 36)) for c in isin[:-1])
    total = 0
    for i, c in enumerate(reversed(digitos)):
        n = int(c)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(isin[-1])


def texto_pdf(ruta: Path) -> tuple[str, str]:
    """(primera página, documento entero), con los espacios normalizados y en
    Unicode NFKC: algunos PDF escriben "ó" como "o" + tilde suelta."""
    # Algunos PDF intercalan un carácter nulo entre letras: fuera.
    paginas = [re.sub(r"\s+", " ", unicodedata.normalize("NFKC", (p.extract_text() or "").replace("\x00", "")))
               for p in PdfReader(ruta).pages]
    return (paginas[0] if paginas else ""), " ".join(paginas)


def _fechas_en(texto: str) -> list[tuple[int, date]]:
    """Todas las fechas válidas del texto con su posición."""
    halladas = []
    for regex, formato in RE_FECHAS:
        for m in regex.finditer(texto):
            a, b, c = m.groups()
            try:
                if formato == "dmy":
                    f = date(int(c), int(b), int(a))
                elif formato == "ymd":
                    f = date(int(a), int(b), int(c))
                elif formato == "d_mes_y":
                    f = date(int(c), MESES[b.lower()], int(a))
                else:
                    f = date(int(c), MESES[a.lower()], int(b))
            except (ValueError, KeyError):
                continue
            halladas.append((m.start(), f))
    return sorted(halladas)


def leer_fecha(texto: str) -> date | None:
    """Fecha del documento: la primera que aparece justo tras una frase clave.
    Si no hay frase clave pero la página solo tiene una fecha, esa."""
    fechas = _fechas_en(texto)
    for clave in CLAVES_FECHA.finditer(texto):
        for pos, f in fechas:
            if clave.end() <= pos <= clave.end() + VENTANA_FECHA:
                return f
    distintas = {f for _, f in fechas}
    return distintas.pop() if len(distintas) == 1 else None


def leer_sri(texto: str) -> int | None:
    """Riesgo 1-7; None si no aparece o si el documento se contradice."""
    valores = ({int(v) for v in RE_SRI.findall(texto)}
               or {int(v) for v in RE_SRI_ESCALA.findall(texto) + RE_SRI_CLASIFICADO.findall(texto)})
    valores = {v for v in valores if 1 <= v <= 7}
    return valores.pop() if len(valores) == 1 else None


def _es_coste_de_operacion(texto: str, m: re.Match) -> bool:
    """¿La cifra que ha casado con RE_TER es en realidad la de costes de operación?"""
    if RE_COSTES_OPERACION.search(m.group(0)) or RE_COMPRAVENTA.search(m.group(0)):
        return True
    # Su descripción: lo que sigue hasta la siguiente cifra o fila de la tabla.
    tras = texto[m.end():m.end() + VENTANA_TRAS_TER]
    corte = min((x.start() for x in (RE_PORCENTAJE.search(tras), RE_COSTES_OPERACION.search(tras)) if x),
                default=len(tras))
    return RE_COMPRAVENTA.search(tras[:corte]) is not None


def leer_ter(texto: str) -> float | None:
    """TER en %; None si no aparece, si es inverosímil, si hay dos distintos
    o si la cifra resulta ser la de costes de operación."""
    valores = {float(m.group(1).replace(",", ".")) for m in RE_TER.finditer(texto)
               if not _es_coste_de_operacion(texto, m)}
    if not valores:
        valores = {float(v.replace(",", ".")) for v in RE_TER_ANTES_DE_ETIQUETA.findall(texto)}
    valores = {v for v in valores if 0 < v <= TER_MAXIMO}
    return valores.pop() if len(valores) == 1 else None


def leer_idioma(texto: str) -> str | None:
    inicio = texto[:1500].lower()
    for idioma, patron in TITULOS.items():
        if re.search(patron, inicio):
            return idioma
    return None


def leer_isins(texto: str) -> list[str]:
    """ISIN válidos, en orden de aparición y sin repetir."""
    return list(dict.fromkeys(i for i in RE_ISIN.findall(texto) if isin_valido(i)))


def leer_objetivos(texto: str) -> str | None:
    """Texto del apartado «Objetivos» (qué hace y en qué invierte el fondo),
    hasta el siguiente apartado obligatorio. None si no se encuentra."""
    for inicio in RE_INICIO_OBJETIVOS.finditer(texto):
        resto = texto[inicio.end():]
        fin = RE_FIN_OBJETIVOS.search(resto)
        seccion = resto[:fin.start()] if fin else resto[:LARGO_MAXIMO_OBJETIVOS]
        seccion = seccion.strip(" :.-")[:LARGO_MAXIMO_OBJETIVOS]
        # Una mención suelta ("objetivo de inversión" en otra frase) da un
        # trozo muy corto: se prueba con la siguiente.
        if len(seccion) >= 150:
            return seccion
    return None
