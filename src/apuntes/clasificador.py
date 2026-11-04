"""Deduce la asignatura de un fichero a partir de su nombre (sin IA).

Cada asignatura tiene `palabras_clave`. Se normaliza el nombre (minúsculas,
sin tildes) y se cuentan las coincidencias:

- una palabra clave corta (≤ 3 letras, como «bd» o «si») solo cuenta si
  aparece como palabra suelta: «SI_tema2.pdf» sí, «sistema.pdf» no;
- una larga cuenta también dentro de otra palabra: «normalizacion3FN».

Gana la asignatura con más coincidencias. Si hay empate o ninguna, no se
decide: es mejor no mover un fichero que moverlo a la carpeta equivocada.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from apuntes.config import Asignatura

_SEPARADORES = re.compile(r"[^a-z0-9]+")
_LONGITUD_MINIMA_SUBCADENA = 4


def normalizar(texto: str) -> str:
    """'Programación_POO' -> 'programacion_poo'."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def _palabras(texto: str) -> set[str]:
    """Separa también letras de números: 'tema3poo' -> {'tema', '3', 'poo'}."""
    trozos = _SEPARADORES.split(normalizar(texto))
    palabras: set[str] = set()
    for trozo in trozos:
        palabras.update(p for p in re.findall(r"[a-z]+|[0-9]+", trozo))
    return palabras


@dataclass(frozen=True)
class Resultado:
    asignatura: str | None
    motivo: str


class Clasificador:
    def __init__(self, asignaturas: list[Asignatura]) -> None:
        self._asignaturas = asignaturas

    def clasificar(self, nombre_fichero: str) -> Resultado:
        palabras = _palabras(nombre_fichero)
        texto = " ".join(_SEPARADORES.split(normalizar(nombre_fichero))).strip()
        puntos: dict[str, int] = {}
        for asignatura in self._asignaturas:
            claves = [asignatura.nombre, *asignatura.palabras_clave]
            total = sum(self._coincide(clave, palabras, texto) for clave in claves)
            if total:
                puntos[asignatura.nombre] = total

        if not puntos:
            return Resultado(None, "no encaja con ninguna asignatura")
        mejor = max(puntos.values())
        ganadoras = sorted(n for n, p in puntos.items() if p == mejor)
        if len(ganadoras) > 1:
            return Resultado(None, f"dudoso entre {' y '.join(ganadoras)}")
        return Resultado(ganadoras[0], f"{mejor} coincidencia(s)")

    @staticmethod
    def _coincide(clave: str, palabras: set[str], texto: str) -> bool:
        clave = " ".join(_SEPARADORES.split(normalizar(clave))).strip()
        if not clave:
            return False
        if " " in clave:  # «bases de datos» se busca como frase
            return f" {clave} " in f" {texto} "
        if clave in palabras:
            return True
        return len(clave) >= _LONGITUD_MINIMA_SUBCADENA and clave in texto.replace(" ", "")
