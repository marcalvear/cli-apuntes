"""Inspección de ficheros: qué hay en una carpeta y de qué tipo es cada cosa.

Este módulo solo lee el disco; nunca modifica nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from apuntes.errores import CarpetaNoValida


class TipoFichero(StrEnum):
    CARPETA = "carpeta"
    PDF = "pdf"
    PRESENTACION = "presentación"
    DOCUMENTO = "documento"
    HOJA_CALCULO = "hoja de cálculo"
    TEXTO = "texto"
    CODIGO = "código"
    IMAGEN = "imagen"
    COMPRIMIDO = "comprimido"
    OTRO = "otro"


_EXTENSIONES: dict[TipoFichero, frozenset[str]] = {
    TipoFichero.PDF: frozenset({".pdf"}),
    TipoFichero.PRESENTACION: frozenset({".ppt", ".pptx", ".odp", ".key"}),
    TipoFichero.DOCUMENTO: frozenset({".doc", ".docx", ".odt", ".rtf", ".pages"}),
    TipoFichero.HOJA_CALCULO: frozenset({".xls", ".xlsx", ".ods", ".csv", ".numbers"}),
    TipoFichero.TEXTO: frozenset({".txt", ".md"}),
    TipoFichero.CODIGO: frozenset(
        {
            ".py",
            ".java",
            ".kt",
            ".js",
            ".ts",
            ".html",
            ".css",
            ".sql",
            ".c",
            ".cpp",
            ".json",
            ".xml",
            ".toml",
            ".yaml",
            ".yml",
        }
    ),
    TipoFichero.IMAGEN: frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".svg"}),
    TipoFichero.COMPRIMIDO: frozenset({".zip", ".rar", ".7z", ".tar", ".gz"}),
}


@dataclass(frozen=True, slots=True)
class InfoFichero:
    """Lo que `listar` muestra de cada entrada de una carpeta."""

    ruta: Path
    tipo: TipoFichero
    tamano: int  # bytes; 0 para carpetas
    modificado: datetime

    @property
    def nombre(self) -> str:
        return self.ruta.name

    @staticmethod
    def desde_ruta(ruta: Path) -> InfoFichero:
        """Fábrica: construye la información leyendo el disco una sola vez."""
        datos = ruta.stat()
        es_carpeta = ruta.is_dir()
        return InfoFichero(
            ruta=ruta,
            tipo=TipoFichero.CARPETA if es_carpeta else tipo_de(ruta),
            tamano=0 if es_carpeta else datos.st_size,
            modificado=datetime.fromtimestamp(datos.st_mtime),
        )


def tipo_de(ruta: Path) -> TipoFichero:
    """Clasifica un fichero por su extensión (sin distinguir mayúsculas)."""
    extension = ruta.suffix.lower()
    for tipo, extensiones in _EXTENSIONES.items():
        if extension in extensiones:
            return tipo
    return TipoFichero.OTRO


def tamano_legible(num_bytes: int) -> str:
    """1536 -> '1.5 KB'. Usa base 1024, como Finder y el Explorador."""
    assert num_bytes >= 0, "un tamaño nunca es negativo"
    valor = float(num_bytes)
    for unidad in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidad == "GB":
            return f"{int(valor)} {unidad}" if unidad == "B" else f"{valor:.1f} {unidad}"
        valor /= 1024
    raise AssertionError("inalcanzable")


def listar_carpeta(carpeta: Path, *, incluir_ocultos: bool = False) -> list[InfoFichero]:
    """Devuelve las entradas de `carpeta` (sin recursión): carpetas primero y luego por nombre."""
    carpeta = carpeta.expanduser()
    if not carpeta.exists():
        raise CarpetaNoValida(f"La carpeta «{carpeta}» no existe.")
    if not carpeta.is_dir():
        raise CarpetaNoValida(f"«{carpeta}» es un fichero, no una carpeta.")
    try:
        entradas = list(carpeta.iterdir())
    except PermissionError as error:
        raise CarpetaNoValida(f"No tengo permiso para leer «{carpeta}».") from error

    infos: list[InfoFichero] = []
    for entrada in entradas:
        if not incluir_ocultos and entrada.name.startswith("."):
            continue
        try:
            infos.append(InfoFichero.desde_ruta(entrada))
        except OSError:
            continue  # enlace roto o fichero borrado mientras leíamos: no es motivo para fallar
    return sorted(infos, key=lambda i: (i.tipo is not TipoFichero.CARPETA, i.nombre.lower()))
