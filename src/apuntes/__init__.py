"""apuntes: organiza el material de clase con acciones definidas en acciones.json."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("apuntes")
except PackageNotFoundError:  # ejecutando desde el código sin instalar
    __version__ = "0.0.0"
