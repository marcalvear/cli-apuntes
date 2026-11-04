"""Interfaz de línea de órdenes.

Aquí solo se leen argumentos y se pinta la salida; la lógica vive en
los demás módulos. Los errores previsibles (ApuntesError) se muestran
como un mensaje y un código de salida, nunca como traceback.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from apuntes import __version__
from apuntes.errores import ApuntesError
from apuntes.ficheros import TipoFichero, listar_carpeta, tamano_legible

consola = Console()
consola_err = Console(stderr=True)


class _GrupoApuntes(typer.core.TyperGroup):
    """Grupo de órdenes que traduce los errores previsibles en mensaje + código de salida."""

    def invoke(self, ctx: typer.Context) -> object:
        try:
            return super().invoke(ctx)
        except ApuntesError as error:
            consola_err.print(f"[bold red]Error:[/] {error.mensaje}")
            if error.pista:
                consola_err.print(f"[yellow]Pista:[/] {error.pista}")
            raise typer.Exit(error.codigo_salida) from None


app = typer.Typer(
    cls=_GrupoApuntes,
    name="apuntes",
    help="Organiza tus apuntes y el material de clase con acciones definidas en acciones.json.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)


class Orden(StrEnum):
    NOMBRE = "nombre"
    TAMANO = "tamano"
    FECHA = "fecha"


@app.command()
def version() -> None:
    """Muestra la versión instalada."""
    consola.print(f"apuntes {__version__}")


@app.command()
def listar(
    carpeta: Annotated[
        Path, typer.Argument(help="Carpeta a listar. Por defecto, la actual.", show_default=False)
    ] = Path("."),
    todos: Annotated[bool, typer.Option("--todos", "-a", help="Incluye ficheros ocultos.")] = False,
    orden: Annotated[
        Orden, typer.Option("--orden", "-o", help="Criterio de ordenación.")
    ] = Orden.NOMBRE,
) -> None:
    """Tabla con nombre, tipo, tamaño y fecha de cada fichero de CARPETA."""
    infos = listar_carpeta(carpeta, incluir_ocultos=todos)
    if orden is Orden.TAMANO:
        infos.sort(key=lambda i: i.tamano, reverse=True)
    elif orden is Orden.FECHA:
        infos.sort(key=lambda i: i.modificado, reverse=True)

    if not infos:
        consola.print(f"[dim]La carpeta «{carpeta}» está vacía.[/]")
        return

    tabla = Table(title=str(carpeta.expanduser().resolve()), title_justify="left")
    tabla.add_column("Nombre", overflow="fold")
    tabla.add_column("Tipo")
    tabla.add_column("Tamaño", justify="right")
    tabla.add_column("Modificado")
    for info in infos:
        es_carpeta = info.tipo is TipoFichero.CARPETA
        tabla.add_row(
            f"[bold blue]{info.nombre}/[/]" if es_carpeta else info.nombre,
            str(info.tipo),
            "" if es_carpeta else tamano_legible(info.tamano),
            info.modificado.strftime("%Y-%m-%d %H:%M"),
        )
    consola.print(tabla)
    consola.print(f"[dim]{len(infos)} elementos[/]")


def main() -> None:
    """Punto de entrada del comando `apuntes`."""
    app()
