"""Base de datos SQLite con todos los KID leídos (resultados/kids.db).

Cada PDF es una fila, identificada por su huella (sha256): volver a leer el
mismo archivo actualiza su fila en lugar de duplicarla. Un mismo ISIN puede
tener varias filas, una por cada versión del KID (fecha), y así se ve si el
que tienes es el último.

Consulta desde la terminal:
    sqlite3 -box resultados/kids.db "SELECT * FROM ultimos"
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .extractor import Ficha

NOMBRE_BD = "kids.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS kid (
    id             INTEGER PRIMARY KEY,
    huella         TEXT NOT NULL UNIQUE,   -- sha256 del PDF
    isin           TEXT,
    nombre         TEXT,
    fecha_kid      TEXT,                   -- AAAA-MM-DD
    idioma         TEXT,
    riesgo         INTEGER,                -- SRI 1-7
    ter            REAL,                   -- % anual
    descripcion    TEXT,
    descripcion_ia INTEGER NOT NULL,       -- 0: extracto literal, sin resumir
    con_ia         INTEGER NOT NULL,       -- 1: leído con Ollama
    otros_isin     TEXT,                   -- KID que cubren varias clases
    avisos         TEXT,
    archivo        TEXT NOT NULL,
    leido_primero  TEXT NOT NULL,          -- AAAA-MM-DD HH:MM:SS
    leido_ultimo   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS kid_isin_fecha ON kid (isin, fecha_kid);

-- Las vistas se rehacen al abrir la base, así siempre están al día.
DROP VIEW IF EXISTS ultimos;
DROP VIEW IF EXISTS kids;
CREATE VIEW kids AS
SELECT isin, nombre, fecha_kid, riesgo, ter, idioma, descripcion,
       CASE WHEN isin IS NULL OR fecha_kid IS NULL THEN '?'
            WHEN fecha_kid = MAX(fecha_kid) OVER (PARTITION BY isin) THEN 'sí'
            ELSE 'no' END AS ultimo,
       archivo, avisos, leido_ultimo
FROM kid;
CREATE VIEW ultimos AS
SELECT isin, nombre, fecha_kid, riesgo, ter, idioma, descripcion, archivo
FROM kids WHERE ultimo = 'sí' ORDER BY nombre, isin;
"""

# Si el mismo PDF ya se leyó con IA y ahora se lee sin ella, se conservan el
# nombre, la descripción y los avisos de la lectura con IA.
UPSERT = """
INSERT INTO kid (huella, isin, nombre, fecha_kid, idioma, riesgo, ter, descripcion, descripcion_ia,
                 con_ia, otros_isin, avisos, archivo, leido_primero, leido_ultimo)
VALUES (:huella, :isin, :nombre, :fecha_kid, :idioma, :riesgo, :ter, :descripcion, :descripcion_ia,
        :con_ia, :otros_isin, :avisos, :archivo, :ahora, :ahora)
ON CONFLICT (huella) DO UPDATE SET
    isin = excluded.isin, fecha_kid = excluded.fecha_kid, idioma = excluded.idioma,
    riesgo = excluded.riesgo, ter = excluded.ter, otros_isin = excluded.otros_isin,
    archivo = excluded.archivo, leido_ultimo = excluded.leido_ultimo,
    nombre         = CASE WHEN kid.con_ia AND NOT excluded.con_ia THEN kid.nombre ELSE excluded.nombre END,
    descripcion    = CASE WHEN kid.con_ia AND NOT excluded.con_ia THEN kid.descripcion ELSE excluded.descripcion END,
    descripcion_ia = CASE WHEN kid.con_ia AND NOT excluded.con_ia THEN kid.descripcion_ia ELSE excluded.descripcion_ia END,
    avisos         = CASE WHEN kid.con_ia AND NOT excluded.con_ia THEN kid.avisos ELSE excluded.avisos END,
    con_ia         = MAX(kid.con_ia, excluded.con_ia)
"""


@dataclass
class Estado:
    """Cómo queda un KID frente a lo que ya había en la base."""
    tipo: str                    # nuevo · actualiza · ultimo · antiguo · sin_datos
    ya_guardado: bool = False    # este mismo PDF ya estaba en la base
    otra_fecha: date | None = None  # la versión anterior (actualiza) o la más reciente (antiguo)


def abrir(carpeta: Path) -> sqlite3.Connection:
    carpeta.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(carpeta / NOMBRE_BD)
    con.executescript(ESQUEMA)
    return con


def guardar(con: sqlite3.Connection, fichas: list[Ficha]) -> list[Estado]:
    """Guarda (o actualiza) las fichas y devuelve cómo queda cada una frente a
    las demás versiones de su ISIN, incluidas las leídas en esta misma tanda.
    Las de PDF que no se han podido abrir no tienen huella y no se guardan."""
    ya = {h for (h,) in con.execute("SELECT huella FROM kid")}
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filas = [{
        "huella": f.huella, "isin": f.isin, "nombre": f.nombre,
        "fecha_kid": f.fecha.isoformat() if f.fecha else None, "idioma": f.idioma, "riesgo": f.sri,
        "ter": f.ter, "descripcion": f.descripcion, "descripcion_ia": int(f.descripcion_ia),
        "con_ia": int(f.con_ia), "otros_isin": ", ".join(f.otros_isin) or None,
        "avisos": "; ".join(f.avisos) or None, "archivo": f.archivo, "ahora": ahora,
    } for f in fichas if f.huella]
    with con:
        con.executemany(UPSERT, filas)
    return [_estado(con, f, f.huella in ya) for f in fichas]


def _estado(con: sqlite3.Connection, f: Ficha, ya_guardado: bool) -> Estado:
    if not f.huella or not f.isin or not f.fecha:
        return Estado("sin_datos", ya_guardado)
    fecha = f.fecha.isoformat()
    mas_reciente, anterior = con.execute(
        "SELECT MAX(CASE WHEN fecha_kid > :f THEN fecha_kid END),"
        "       MAX(CASE WHEN fecha_kid < :f THEN fecha_kid END) FROM kid WHERE isin = :isin",
        {"f": fecha, "isin": f.isin}).fetchone()
    if mas_reciente:
        return Estado("antiguo", ya_guardado, date.fromisoformat(mas_reciente))
    if ya_guardado:
        return Estado("ultimo", True)
    if anterior:
        return Estado("actualiza", False, date.fromisoformat(anterior))
    otro_igual = con.execute("SELECT 1 FROM kid WHERE isin = ? AND fecha_kid = ? AND huella <> ?",
                             (f.isin, fecha, f.huella)).fetchone()
    return Estado("ultimo" if otro_igual else "nuevo", False)


def ultimos(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """La última versión guardada de cada fondo."""
    con.row_factory = sqlite3.Row
    try:
        return con.execute("SELECT * FROM ultimos").fetchall()
    finally:
        con.row_factory = None
