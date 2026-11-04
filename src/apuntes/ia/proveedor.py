"""La interfaz común de cualquier proveedor de IA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from apuntes.config import Asignatura
from apuntes.ia.documento import Documento

Confianza = Literal["alta", "media", "baja"]


@dataclass(frozen=True)
class Clasificacion:
    """Respuesta de la IA a «¿de qué asignatura es este documento?»."""

    asignatura: str | None  # None: no es de ninguna
    confianza: Confianza
    motivo: str

    @property
    def fiable(self) -> bool:
        """Solo se actúa sobre clasificaciones con asignatura y confianza no baja."""
        return self.asignatura is not None and self.confianza != "baja"


class ProveedorIA(ABC):
    """Lo que las acciones de IA necesitan, sin saber qué IA hay detrás."""

    #: Identifica el modelo concreto (forma parte de la clave de la caché).
    modelo: str

    @abstractmethod
    def comprobar(self) -> None:
        """Lanza IANoDisponible si no se puede usar (sin clave, sin red...). Debe ser rápido."""

    @abstractmethod
    def clasificar(self, documento: Documento, asignaturas: list[Asignatura]) -> Clasificacion:
        """Decide a cuál de `asignaturas` pertenece el documento."""

    @abstractmethod
    def resumir(self, documento: Documento) -> str:
        """Resumen en Markdown con los conceptos clave."""

    @abstractmethod
    def preguntas(self, documento: Documento, numero: int) -> str:
        """`numero` preguntas tipo test con solución, en Markdown."""
