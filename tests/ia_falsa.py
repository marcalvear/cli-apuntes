"""Proveedor de IA falso para los tests: responde al instante y sin red ni coste."""

from __future__ import annotations

from apuntes.config import Asignatura
from apuntes.errores import IANoDisponible
from apuntes.ia.documento import Documento
from apuntes.ia.proveedor import Clasificacion, ProveedorIA


class IAFalsa(ProveedorIA):
    """Clasifica buscando el nombre de la asignatura en el *contenido* del documento.

    `disponible=False` simula que falta la clave o no hay red.
    """

    modelo = "falso-1"

    def __init__(self, *, disponible: bool = True) -> None:
        self.disponible = disponible
        self.llamadas: list[tuple[str, str]] = []  # (tarea, documento)

    def comprobar(self) -> None:
        if not self.disponible:
            raise IANoDisponible("No hay conexión con la API de Claude (¿sin internet?).")

    def clasificar(self, documento: Documento, asignaturas: list[Asignatura]) -> Clasificacion:
        self.llamadas.append(("clasificar", documento.nombre))
        contenido = documento.contenido.decode("utf-8", "ignore").lower()
        for asignatura in asignaturas:
            if asignatura.nombre.lower() in contenido:
                return Clasificacion(asignatura.nombre, "alta", "lo dice el contenido")
        return Clasificacion(None, "baja", "no se parece a ninguna")

    def resumir(self, documento: Documento) -> str:
        self.llamadas.append(("resumir", documento.nombre))
        return f"# Resumen de {documento.nombre}\n\n- Idea clave."

    def preguntas(self, documento: Documento, numero: int) -> str:
        self.llamadas.append(("preguntas", documento.nombre))
        return f"# {numero} preguntas sobre {documento.nombre}\n"
