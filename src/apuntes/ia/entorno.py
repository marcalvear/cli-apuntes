"""Configuración de la IA desde el entorno y los ficheros .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from apuntes.ia.proveedor import ProveedorIA

VARIABLE_MODELO = "APUNTES_MODELO"


def ficheros_env(cwd: Path | None = None) -> list[Path]:
    """Dónde se busca .env: la carpeta actual y la configuración del usuario."""
    return [(cwd or Path.cwd()) / ".env", Path.home() / ".config" / "apuntes" / ".env"]


def cargar_env(cwd: Path | None = None) -> None:
    """Carga los .env que existan. Nunca pisa variables que ya estén definidas."""
    for ruta in ficheros_env(cwd):
        if ruta.is_file():
            load_dotenv(ruta, override=False)


def hay_clave() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def crear_proveedor() -> ProveedorIA:
    """Fábrica del proveedor configurado, envuelto en la caché.

    Importa el SDK de Anthropic aquí y no arriba: así las órdenes que no usan
    IA arrancan sin cargarlo.
    """
    from apuntes.ia.cache import ProveedorConCache
    from apuntes.ia.claude import MODELO_POR_DEFECTO, ProveedorClaude

    modelo = os.environ.get(VARIABLE_MODELO) or MODELO_POR_DEFECTO
    return ProveedorConCache(ProveedorClaude(modelo=modelo))
