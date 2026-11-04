"""Operaciones de escritura seguras.

Regla del proyecto: nunca se deja un fichero a medias. Se escribe en un
temporal de la misma carpeta y luego se renombra con os.replace, que es
atómico: o queda el fichero nuevo completo o sigue el antiguo intacto.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def escribir_atomico(ruta: Path, contenido: str | bytes) -> None:
    """Escribe `contenido` en `ruta` de forma atómica (crea las carpetas si faltan)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = contenido.encode("utf-8") if isinstance(contenido, str) else contenido
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as fichero:
            fichero.write(datos)
            fichero.flush()
            os.fsync(fichero.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise
