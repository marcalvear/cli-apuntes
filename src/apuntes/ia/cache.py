"""Caché de respuestas de la IA (patrón decorador).

`ProveedorConCache` envuelve cualquier `ProveedorIA` y guarda cada respuesta
en ~/.cache/apuntes/ia.json, con una clave formada por la tarea, el modelo,
los parámetros y la huella SHA-256 del documento. Así:

- `--simular` seguido de la ejecución real no paga dos veces la clasificación;
- si una ejecución se corta a medias, al repetirla lo ya generado sale gratis;
- renombrar o mover un PDF no invalida su caché (cuenta el contenido).
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from apuntes.config import Asignatura
from apuntes.disco import escribir_atomico
from apuntes.ia.documento import Documento
from apuntes.ia.proveedor import Clasificacion, ProveedorIA


def ruta_cache_por_defecto() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "apuntes" / "ia.json"


class ProveedorConCache(ProveedorIA):
    def __init__(self, proveedor: ProveedorIA, ruta: Path | None = None) -> None:
        self._proveedor = proveedor
        self._ruta = ruta or ruta_cache_por_defecto()
        self._datos: dict[str, Any] | None = None
        self.modelo = proveedor.modelo
        self.aciertos = 0

    def comprobar(self) -> None:
        self._proveedor.comprobar()

    def clasificar(self, documento: Documento, asignaturas: list[Asignatura]) -> Clasificacion:
        # Las asignaturas forman parte de la clave: si cambian, hay que volver a preguntar.
        lista = sorted(f"{a.nombre}:{','.join(a.palabras_clave)}" for a in asignaturas)
        clave = self._clave("clasificar", documento, lista)
        if (guardado := self._leer(clave)) is not None:
            return Clasificacion(**guardado)
        resultado = self._proveedor.clasificar(documento, asignaturas)
        self._guardar(clave, asdict(resultado))
        return resultado

    def resumir(self, documento: Documento) -> str:
        return self._texto("resumir", documento, None, lambda: self._proveedor.resumir(documento))

    def preguntas(self, documento: Documento, numero: int) -> str:
        return self._texto(
            "preguntas", documento, numero, lambda: self._proveedor.preguntas(documento, numero)
        )

    # -- Interno --

    def _texto(self, tarea: str, documento: Documento, parametros: Any, generar: Any) -> str:
        clave = self._clave(tarea, documento, parametros)
        if (guardado := self._leer(clave)) is not None:
            return str(guardado)
        texto = generar()
        self._guardar(clave, texto)
        return texto

    def _clave(self, tarea: str, documento: Documento, parametros: Any) -> str:
        return json.dumps([tarea, self.modelo, parametros, documento.huella], ensure_ascii=False)

    def _cargar(self) -> dict[str, Any]:
        if self._datos is None:
            try:
                datos = json.loads(self._ruta.read_text("utf-8"))
                self._datos = datos if isinstance(datos, dict) else {}
            except (OSError, ValueError):
                self._datos = {}  # sin caché o dañada: se empieza de cero, nunca es un error
        return self._datos

    def _leer(self, clave: str) -> Any:
        valor = self._cargar().get(clave)
        if valor is not None:
            self.aciertos += 1
        return valor

    def _guardar(self, clave: str, valor: Any) -> None:
        datos = self._cargar()
        datos[clave] = valor
        # No poder guardar la caché no debe estropear el trabajo hecho.
        with contextlib.suppress(OSError):
            escribir_atomico(self._ruta, json.dumps(datos, ensure_ascii=False, indent=1))
