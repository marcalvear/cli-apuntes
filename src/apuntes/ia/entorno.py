"""Configuración de la IA desde el entorno y los ficheros .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from apuntes.ia.proveedor import ProveedorIA

VARIABLE_MODELO = "APUNTES_MODELO"
VARIABLE_PROVEEDOR = "APUNTES_PROVEEDOR"
PROVEEDORES = ("gemini", "claude")


def ficheros_env(cwd: Path | None = None) -> list[Path]:
    """Dónde se busca .env: la carpeta actual y la configuración del usuario."""
    return [(cwd or Path.cwd()) / ".env", Path.home() / ".config" / "apuntes" / ".env"]


def cargar_env(cwd: Path | None = None) -> None:
    """Carga los .env que existan. Nunca pisa variables que ya estén definidas."""
    for ruta in ficheros_env(cwd):
        if ruta.is_file():
            load_dotenv(ruta, override=False)


_CLAVES = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
}


def proveedor_elegido() -> str:
    """APUNTES_PROVEEDOR si está; si no, el que tenga clave (Gemini, gratis, si no hay ninguna)."""
    elegido = (os.environ.get(VARIABLE_PROVEEDOR) or "").strip().lower()
    if elegido:
        return elegido
    if _tiene_clave("claude") and not _tiene_clave("gemini"):
        return "claude"
    return "gemini"


def _tiene_clave(proveedor: str) -> bool:
    return any(os.environ.get(v) for v in _CLAVES.get(proveedor, ()))


def hay_clave() -> bool:
    """¿Tiene clave el proveedor elegido? (sin red: solo mira el entorno)."""
    return _tiene_clave(proveedor_elegido())


def variable_clave() -> str:
    """Nombre de la variable de la clave del proveedor elegido, para los mensajes."""
    return _CLAVES.get(proveedor_elegido(), ("GEMINI_API_KEY",))[0]


def crear_proveedor() -> ProveedorIA:
    """Fábrica del proveedor configurado, envuelto en la caché.

    Importa el SDK de Anthropic aquí y no arriba: así las órdenes que no usan
    IA arrancan sin cargarlo.
    """
    from apuntes.errores import IANoDisponible
    from apuntes.ia.cache import ProveedorConCache

    proveedor = proveedor_elegido()
    modelo = (os.environ.get(VARIABLE_MODELO) or "").strip()
    if proveedor == "gemini":
        from apuntes.ia.gemini import MODELOS_POR_DEFECTO, ProveedorGemini

        # Con APUNTES_MODELO, ese primero y los demás de reserva.
        modelos = (modelo, *[m for m in MODELOS_POR_DEFECTO if m != modelo]) if modelo else None
        return ProveedorConCache(ProveedorGemini(modelos=modelos or MODELOS_POR_DEFECTO))
    if proveedor == "claude":
        from apuntes.ia.claude import MODELO_POR_DEFECTO, ProveedorClaude

        return ProveedorConCache(ProveedorClaude(modelo=modelo or MODELO_POR_DEFECTO))
    raise IANoDisponible(
        f"Proveedor de IA desconocido: APUNTES_PROVEEDOR={proveedor!r}.",
        pista=f"Valores válidos: {', '.join(PROVEEDORES)}.",
    )
