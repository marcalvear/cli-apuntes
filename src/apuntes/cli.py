"""Interfaz de línea de órdenes.

Aquí solo se leen argumentos y se pinta la salida; la lógica vive en
los demás módulos. Los errores previsibles (ApuntesError) se muestran
como un mensaje y un código de salida, nunca como traceback.
"""

from __future__ import annotations

from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from apuntes import __version__
from apuntes import config as cfg
from apuntes.config import Configuracion
from apuntes.disco import escribir_atomico
from apuntes.errores import ApuntesError, ConfigError
from apuntes.ficheros import TipoFichero, listar_carpeta, tamano_legible

consola = Console()
consola_err = Console(stderr=True)


class _GrupoApuntes(typer.core.TyperGroup):
    """Grupo de órdenes que traduce los errores previsibles en mensaje + código de salida."""

    def invoke(self, ctx: typer.Context) -> object:
        try:
            return super().invoke(ctx)
        except ApuntesError as error:
            mostrar_error(error)
            raise typer.Exit(error.codigo_salida) from None


def mostrar_error(error: ApuntesError) -> None:
    consola_err.print(f"[bold red]Error:[/] {escape(error.mensaje)}")
    if isinstance(error, ConfigError):
        for problema in error.problemas:
            consola_err.print(f"  [red]•[/] {escape(problema)}")
    if error.pista:
        consola_err.print(f"[yellow]Pista:[/] {escape(error.pista)}")


app = typer.Typer(
    cls=_GrupoApuntes,
    name="apuntes",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)


@app.callback()
def _global(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Fichero de acciones. Por defecto: $APUNTES_CONFIG, ./acciones.json "
            "o ~/.config/apuntes/acciones.json.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Organiza tus apuntes y el material de clase con acciones definidas en acciones.json."""
    ctx.obj = config


def _ruta_config(ctx: typer.Context) -> Path:
    return cfg.localizar(ctx.obj)


def _cargar(ctx: typer.Context) -> Configuracion:
    return Configuracion.desde_fichero(_ruta_config(ctx))


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
        consola.print(f"[dim]La carpeta «{escape(str(carpeta))}» está vacía.[/]")
        return

    tabla = Table(title=escape(str(carpeta.expanduser().resolve())), title_justify="left")
    tabla.add_column("Nombre", overflow="fold")
    tabla.add_column("Tipo")
    tabla.add_column("Tamaño", justify="right")
    tabla.add_column("Modificado")
    for info in infos:
        es_carpeta = info.tipo is TipoFichero.CARPETA
        tabla.add_row(
            f"[bold blue]{escape(info.nombre)}/[/]" if es_carpeta else escape(info.nombre),
            str(info.tipo),
            "" if es_carpeta else tamano_legible(info.tamano),
            info.modificado.strftime("%Y-%m-%d %H:%M"),
        )
    consola.print(tabla)
    consola.print(f"[dim]{len(infos)} elementos[/]")


@app.command()
def acciones(ctx: typer.Context) -> None:
    """Lista las acciones definidas en acciones.json con su descripción."""
    configuracion = _cargar(ctx)
    tabla = Table(title=f"Acciones de {escape(str(_ruta_config(ctx)))}", title_justify="left")
    tabla.add_column("Nombre", style="bold cyan", no_wrap=True)
    tabla.add_column("Tipo")
    tabla.add_column("Descripción")
    tabla.add_column("", no_wrap=True)  # marcas
    for accion in configuracion.acciones:
        marcas = []
        if accion.debe_confirmar:
            marcas.append("[yellow]confirma[/]")
        if accion.USA_IA:
            marcas.append("[magenta]IA[/]")
        descripcion = escape(accion.descripcion)
        if accion.tipo == "pipeline":
            descripcion += f"\n[dim]→ {' → '.join(accion.pasos)}[/]"
        tabla.add_row(accion.nombre, accion.tipo, descripcion, " ".join(marcas))
    consola.print(tabla)
    consola.print("[dim]Ejecuta una con: apuntes ejecutar NOMBRE [CARPETA] --simular[/]")


@app.command()
def validar(ctx: typer.Context) -> None:
    """Comprueba acciones.json y dice exactamente qué campo falla (código 3 si es inválido)."""
    ruta = _ruta_config(ctx)
    configuracion = Configuracion.desde_fichero(ruta)
    total = len(configuracion.acciones)
    con_ia = sum(1 for a in configuracion.acciones if a.USA_IA)
    consola.print(
        f"[bold green]✓[/] «{escape(str(ruta))}» es válido: {total} acciones "
        f"({con_ia} con IA) y {len(configuracion.asignaturas)} asignaturas."
    )


@app.command()
def init(
    ruta: Annotated[
        Path, typer.Argument(help="Dónde crearlo.", show_default="./acciones.json")
    ] = Path(cfg.NOMBRE_FICHERO),
    forzar: Annotated[
        bool, typer.Option("--forzar", help="Sobrescribe si ya existe (guarda copia .bak).")
    ] = False,
) -> None:
    """Crea un acciones.json de ejemplo, con asignaturas de DAM, listo para adaptar."""
    ruta = ruta.expanduser()
    if ruta.is_dir():
        ruta = ruta / cfg.NOMBRE_FICHERO
    if ruta.exists() and not forzar:
        raise ApuntesError(
            f"«{ruta}» ya existe; no lo sobrescribo.",
            pista="Usa --forzar para reemplazarlo (se guardará una copia .bak).",
        )
    plantilla = files("apuntes").joinpath("plantillas", cfg.NOMBRE_FICHERO).read_text("utf-8")
    if ruta.exists():
        copia = ruta.with_name(ruta.name + ".bak")
        escribir_atomico(copia, ruta.read_bytes())
        consola.print(f"[dim]Copia del anterior en «{escape(str(copia))}».[/]")
    escribir_atomico(ruta, plantilla)
    consola.print(f"[bold green]✓[/] Creado «{escape(str(ruta))}».")
    consola.print("[dim]Revisa las asignaturas y prueba: apuntes acciones[/]")


def main() -> None:
    """Punto de entrada del comando `apuntes`."""
    app()
