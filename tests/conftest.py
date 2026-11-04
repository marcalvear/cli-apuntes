"""Utilidades compartidas por los tests.

Todos los tests trabajan en carpetas temporales (tmp_path de pytest):
nunca tocan ficheros reales del usuario.
"""

import os
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def crear_fichero(ruta: Path, contenido: bytes = b"x", *, fecha: datetime | None = None) -> Path:
    """Crea un fichero (y sus carpetas) con contenido y, opcionalmente, fecha de modificación."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    if fecha is not None:
        marca = fecha.timestamp()
        os.utime(ruta, (marca, marca))
    return ruta


@pytest.fixture
def carpeta_apuntes(tmp_path: Path) -> Path:
    """Una carpeta de descargas típica con material de clase variado."""
    crear_fichero(tmp_path / "Tema3_POO.pdf", b"%PDF" + b"0" * 2000)
    crear_fichero(tmp_path / "presentacion.PPTX", b"p" * 10)
    crear_fichero(tmp_path / "ejercicio.py", b"print('hola')\n")
    crear_fichero(tmp_path / ".DS_Store", b"basura")
    (tmp_path / "Programacion").mkdir()
    return tmp_path
