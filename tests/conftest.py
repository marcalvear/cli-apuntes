"""Utilidades compartidas por los tests.

Todos los tests trabajan en carpetas temporales (tmp_path de pytest):
nunca tocan ficheros reales del usuario.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def _consola_ancha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rich corta las líneas a 80 columnas; con rutas temporales largas (Windows)
    un mensaje podría partirse justo donde lo buscamos. Ensanchamos la consola."""
    monkeypatch.setenv("COLUMNS", "300")


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


class PapeleraFalsa:
    """Sustituye a la papelera del sistema: guarda lo recibido en una carpeta del test."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = carpeta
        self.recibidos: list[str] = []

    def __call__(self, ruta: Path) -> None:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.recibidos.append(ruta.name)
        shutil.move(ruta, self.carpeta / f"{len(self.recibidos)}-{ruta.name}")


@pytest.fixture(autouse=True)
def papelera(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Ningún test envía nada a la papelera real del ordenador."""
    falsa = PapeleraFalsa(tmp_path_factory.mktemp("papelera"))
    monkeypatch.setattr("apuntes.motor._papelera_del_sistema", falsa)
    return falsa


@pytest.fixture(autouse=True)
def ia(monkeypatch: pytest.MonkeyPatch):
    """Ningún test llama a la API real: el motor usa siempre una IA falsa."""
    from tests.ia_falsa import IAFalsa

    falsa = IAFalsa()
    monkeypatch.setattr("apuntes.motor._proveedor_por_defecto", lambda: falsa)
    return falsa
