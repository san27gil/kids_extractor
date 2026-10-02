"""Tablas de la terminal: los KID recién leídos y los guardados en la base."""

from __future__ import annotations

import sqlite3
from datetime import date

from rich.console import Console
from rich.table import Table

from .bd import Estado
from .extractor import Ficha

# Los KID se revisan al menos una vez al año (Reglamento PRIIPs): uno más
# antiguo seguramente ya tiene una versión nueva en la web de la gestora.
DIAS_VIGENCIA = 365


def tabla(fichas: list[Ficha], estados: list[Estado], consola: Console) -> None:
    t = Table(title="Datos extraídos de los KID", show_lines=True, header_style="bold cyan")
    t.add_column("ISIN", no_wrap=True)
    t.add_column("Nombre", ratio=2)
    t.add_column("Fecha", no_wrap=True)
    t.add_column("Riesgo", justify="center")
    t.add_column("TER", justify="right", no_wrap=True)
    t.add_column("Descripción", ratio=3)
    t.add_column("En la base", ratio=1)
    for f, e in zip(fichas, estados):
        t.add_row(
            f.isin or "[red]—[/]",
            f.nombre or f"[dim]{f.archivo}[/]",
            _fecha(f.fecha),
            _sri(f.sri),
            _ter(f.ter),
            (f.descripcion or "[red]—[/]") if f.descripcion_ia else f"[dim]{f.descripcion or '—'}[/]",
            _estado(e),
        )
    consola.print(t)


def tabla_ultimos(filas: list[sqlite3.Row], consola: Console) -> None:
    t = Table(title=f"Última versión de cada KID guardado ({len(filas)})", show_lines=True,
              header_style="bold cyan")
    t.add_column("ISIN", no_wrap=True)
    t.add_column("Nombre", ratio=2)
    t.add_column("Fecha", no_wrap=True)
    t.add_column("Riesgo", justify="center")
    t.add_column("TER", justify="right", no_wrap=True)
    t.add_column("Descripción", ratio=3)
    for r in filas:
        fecha = date.fromisoformat(r["fecha_kid"])
        viejo = (date.today() - fecha).days > DIAS_VIGENCIA
        t.add_row(r["isin"], r["nombre"] or f"[dim]{r['archivo']}[/]",
                  f"[red]{_fecha(fecha)}\n(+1 año)[/]" if viejo else _fecha(fecha),
                  _sri(r["riesgo"]), _ter(r["ter"]), r["descripcion"] or "[red]—[/]")
    consola.print(t)


def _estado(e: Estado) -> str:
    if e.tipo == "nuevo":
        return "[green]nuevo[/]"
    if e.tipo == "actualiza":
        return f"[green]nuevo: sustituye al del {_fecha(e.otra_fecha)}[/]"
    if e.tipo == "antiguo":
        return f"[red]ya tienes uno más reciente, del {_fecha(e.otra_fecha)}[/]"
    if e.tipo == "ultimo":
        return "último" + (" [dim](ya guardado)[/]" if e.ya_guardado else "")
    return "[yellow]sin ISIN o fecha: no se puede comparar[/]"


def _fecha(d: date | None) -> str:
    return f"{d:%d/%m/%Y}" if d else "[red]—[/]"


def _ter(ter: float | None) -> str:
    return f"{ter:.2f} %".replace(".", ",") if ter is not None else "[red]—[/]"


def _sri(sri: int | None) -> str:
    if sri is None:
        return "[red]—[/]"
    color = "green" if sri <= 2 else "yellow" if sri <= 4 else "red"
    return f"[bold {color}]{sri}[/]"
