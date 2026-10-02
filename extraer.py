"""Extrae los datos principales de los KID de fondos de inversión.

Uso:
    python extraer.py                    # lee los PDF de la carpeta kids/
    python extraer.py ruta/a/carpeta     # otra carpeta
    python extraer.py a.pdf b.pdf        # PDF sueltos
    python extraer.py --sin-ia           # sin Ollama: sin nombre y con extracto literal
    python extraer.py --ver              # última versión de cada KID guardado

Muestra una tabla en la terminal y guarda todo en la base de datos
resultados/kids.db, que se va acumulando entre ejecuciones.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import closing
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn

from kid_extractor import bd, ia, salida
from kid_extractor.extractor import analizar

RAIZ = Path(__file__).resolve().parent
CARPETA_KIDS = RAIZ / "kids"
CARPETA_RESULTADOS = RAIZ / "resultados"


def _pdfs(rutas: list[str]) -> list[Path]:
    encontrados: list[Path] = []
    for r in (Path(x) for x in rutas) if rutas else [CARPETA_KIDS]:
        if r.is_dir():
            encontrados += sorted(p for p in r.iterdir() if p.suffix.lower() == ".pdf")
        elif r.suffix.lower() == ".pdf" and r.exists():
            encontrados.append(r)
        else:
            raise SystemExit(f"No existe o no es un PDF ni una carpeta: {r}")
    return encontrados


def main() -> None:
    p = argparse.ArgumentParser(description="Extrae nombre, ISIN, riesgo, TER y descripción de los KID en PDF.")
    p.add_argument("rutas", nargs="*", help="carpetas o PDF (por defecto: kids/)")
    p.add_argument("--sin-ia", action="store_true", help="no usar Ollama")
    p.add_argument("--modelo", default=ia.MODELO, help=f"modelo de Ollama (por defecto: {ia.MODELO})")
    p.add_argument("--salida", type=Path, default=CARPETA_RESULTADOS,
                   help=f"carpeta de la base de datos {bd.NOMBRE_BD} (por defecto: resultados/)")
    p.add_argument("--ver", action="store_true", help="solo muestra la última versión de cada KID guardado")
    args = p.parse_args()
    consola = Console()

    if args.ver:
        with closing(bd.abrir(args.salida)) as con:
            salida.tabla_ultimos(bd.ultimos(con), consola)
        consola.print(f"[dim]Consultas a medida: sqlite3 -box {args.salida / bd.NOMBRE_BD}[/]")
        return

    pdfs = _pdfs(args.rutas)
    if not pdfs:
        consola.print(f"[yellow]No hay PDF que leer. Deja los KID en[/] {CARPETA_KIDS}")
        sys.exit(1)

    usar_ia = not args.sin_ia
    if usar_ia and not ia.disponible(args.modelo):
        consola.print(f"[yellow]Ollama no está abierto o no tiene el modelo «{args.modelo}».[/] "
                      f"Sigo sin IA: sin nombre del fondo y con la descripción sin resumir.\n"
                      f"Para usarla: abre Ollama y ejecuta [bold]ollama pull {args.modelo}[/]\n")
        usar_ia = False

    fichas = []
    columnas = (TextColumn("[progress.description]{task.description}"), BarColumn(), MofNCompleteColumn())
    with Progress(*columnas, console=consola, transient=True) as progreso:
        tarea = progreso.add_task("Leyendo KID", total=len(pdfs))
        for pdf in pdfs:
            progreso.update(tarea, description=f"Leyendo {pdf.name[:40]}")
            try:
                fichas.append(analizar(pdf, usar_ia, args.modelo))
            except ia.IANoDisponible:
                consola.print("[yellow]Ollama ha dejado de responder: sigo sin IA.[/]")
                usar_ia = False
                fichas.append(analizar(pdf, usar_ia, args.modelo))
            progreso.advance(tarea)

    with closing(bd.abrir(args.salida)) as con:
        estados = bd.guardar(con, fichas)
    salida.tabla(fichas, estados, consola)

    con_avisos = [f for f in fichas if f.avisos]
    for f in con_avisos:
        consola.print(f"[yellow]⚠ {f.archivo}:[/] {'; '.join(f.avisos)}")
    consola.print(f"\n[green]✓[/] {len(fichas)} KID leídos, {len(fichas) - len(con_avisos)} completos, "
                  f"guardados en [bold]{args.salida / bd.NOMBRE_BD}[/]")
    antiguos = sum(e.tipo == "antiguo" for e in estados)
    if antiguos:
        consola.print(f"[red]{antiguos} de los KID leídos no son la última versión que tienes guardada.[/]")


if __name__ == "__main__":
    main()
