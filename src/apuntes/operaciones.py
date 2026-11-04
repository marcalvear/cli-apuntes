"""Operaciones atómicas sobre el disco.

Una acción nunca toca el disco directamente: produce una lista de
operaciones (un *plan*). Así el mismo plan sirve para:

- mostrarse en `--simular` sin cambiar nada,
- enseñarse antes de pedir confirmación,
- aplicarse paso a paso, deteniéndose al primer fallo.

Cada operación se asegura de no dejar ficheros a medias: lo que se
escribe va primero a un temporal de la carpeta destino y se coloca con
`os.replace`, que es atómico.
"""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import tempfile
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from apuntes.disco import escribir_atomico
from apuntes.errores import FicheroError

#: Función que envía una ruta a la papelera. Se inyecta para poder probarla.
Papelera = Callable[[Path], None]


def _relativa(ruta: Path, base: Path) -> str:
    try:
        return ruta.relative_to(base).as_posix()
    except ValueError:
        return str(ruta)


def _temporal_en(carpeta: Path, nombre: str) -> Path:
    descriptor, temporal = tempfile.mkstemp(dir=carpeta, prefix=f".{nombre}.", suffix=".tmp")
    os.close(descriptor)
    return Path(temporal)


def _copiar_atomico(origen: Path, destino: Path) -> None:
    """Copia contenido y metadatos (fecha) sin que `destino` exista nunca a medias."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = _temporal_en(destino.parent, destino.name)
    try:
        shutil.copy2(origen, temporal)
        os.replace(temporal, destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


def _mover_atomico(origen: Path, destino: Path) -> None:
    """Renombra si es posible; entre discos distintos copia de forma atómica y luego borra."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(origen, destino)
    except OSError as error:
        if error.errno != errno.EXDEV:  # EXDEV: origen y destino en discos distintos
            raise
        _copiar_atomico(origen, destino)
        origen.unlink()


class Operacion(ABC):
    """Un cambio concreto en el disco."""

    #: ¿Hace desaparecer algo (a la papelera) o lo reemplaza?
    destructiva: bool = False

    @abstractmethod
    def describir(self, base: Path) -> tuple[str, str, str]:
        """(verbo, objeto, destino) para mostrar al usuario, con rutas relativas a `base`."""

    @abstractmethod
    def _ejecutar(self, papelera: Papelera) -> None: ...

    @abstractmethod
    def registro(self) -> dict[str, object]:
        """Lo que hay que guardar en el historial para poder deshacerla.

        Se llama *antes* de aplicar, para capturar el estado previo si hace falta.
        """

    @abstractmethod
    def _comprobar(self) -> None:
        """Lanza FicheroError si las condiciones del plan ya no se cumplen."""

    def aplicar(self, papelera: Papelera) -> None:
        """Comprueba que todo sigue como al planificar y ejecuta. Errores → FicheroError."""
        self._comprobar()
        try:
            self._ejecutar(papelera)
        except FicheroError:
            raise
        except OSError as error:
            verbo, objeto, destino = self.describir(Path("/"))
            detalle = f" → {destino}" if destino else ""
            causa = error.strerror or str(error)
            raise FicheroError(f"No he podido {verbo} «{objeto}»{detalle}: {causa}.") from error


def carpetas_nuevas(ruta: Path) -> list[str]:
    """Carpetas que habrá que crear para escribir en `ruta`, de la más profunda a la raíz.

    Se guarda en el historial para que `deshacer` pueda quitarlas si quedan vacías,
    sin tocar nunca una carpeta que ya existía.
    """
    nuevas: list[str] = []
    carpeta = ruta.parent
    while not carpeta.exists() and carpeta != carpeta.parent:
        nuevas.append(str(carpeta))
        carpeta = carpeta.parent
    return nuevas


def _ocupado_por_otro(origen: Path, destino: Path) -> bool:
    """¿Hay en `destino` un fichero distinto de `origen`?

    En macOS y Windows «tema.pdf» y «Tema.pdf» son el mismo fichero: cambiar
    solo mayúsculas no debe tratarse como un conflicto.
    """
    if not destino.exists():
        return False
    try:
        return not os.path.samefile(origen, destino)
    except OSError:
        return True


def _debe_existir(ruta: Path) -> None:
    if not ruta.exists():
        raise FicheroError(f"«{ruta}» ya no existe: ha cambiado desde que se planificó.")


@dataclass(frozen=True)
class Mover(Operacion):
    origen: Path
    destino: Path
    sobrescribe: bool = False
    verbo: str = "mover"

    @property
    def destructiva(self) -> bool:  # type: ignore[override]
        return self.sobrescribe

    def describir(self, base: Path) -> tuple[str, str, str]:
        destino = _relativa(self.destino, base)
        if self.verbo == "renombrar":
            destino = self.destino.name
        return (self.verbo, _relativa(self.origen, base), destino)

    def _comprobar(self) -> None:
        _debe_existir(self.origen)
        if _ocupado_por_otro(self.origen, self.destino) and not self.sobrescribe:
            raise FicheroError(f"«{self.destino}» ya existe: ha aparecido desde que se planificó.")

    def registro(self) -> dict[str, object]:
        return {
            "op": "mover",
            "origen": str(self.origen),
            "destino": str(self.destino),
            "sobrescribe": _ocupado_por_otro(self.origen, self.destino),
            "carpetas_creadas": carpetas_nuevas(self.destino),
        }

    def _ejecutar(self, papelera: Papelera) -> None:
        if _ocupado_por_otro(self.origen, self.destino):  # solo si sobrescribe
            papelera(self.destino)  # el anterior se puede recuperar de la papelera
        _mover_atomico(self.origen, self.destino)


@dataclass(frozen=True)
class Copiar(Operacion):
    origen: Path
    destino: Path
    sobrescribe: bool = False

    @property
    def destructiva(self) -> bool:  # type: ignore[override]
        return self.sobrescribe

    def describir(self, base: Path) -> tuple[str, str, str]:
        return ("copiar", _relativa(self.origen, base), _relativa(self.destino, base))

    def _comprobar(self) -> None:
        _debe_existir(self.origen)
        if self.destino.exists() and not self.sobrescribe:
            raise FicheroError(f"«{self.destino}» ya existe: ha aparecido desde que se planificó.")

    def registro(self) -> dict[str, object]:
        return {
            "op": "copiar",
            "origen": str(self.origen),
            "destino": str(self.destino),
            "sobrescribe": self.destino.exists(),
            "carpetas_creadas": carpetas_nuevas(self.destino),
        }

    def _ejecutar(self, papelera: Papelera) -> None:
        if self.destino.exists():
            papelera(self.destino)
        _copiar_atomico(self.origen, self.destino)


@dataclass(frozen=True)
class EnviarAPapelera(Operacion):
    ruta: Path
    motivo: str = ""
    destructiva = True

    def describir(self, base: Path) -> tuple[str, str, str]:
        return ("a la papelera", _relativa(self.ruta, base), self.motivo)

    def _comprobar(self) -> None:
        _debe_existir(self.ruta)

    def registro(self) -> dict[str, object]:
        return {"op": "papelera", "ruta": str(self.ruta)}

    def _ejecutar(self, papelera: Papelera) -> None:
        papelera(self.ruta)


@dataclass(frozen=True)
class Escribir(Operacion):
    """Crea (o reemplaza) un fichero de texto generado por apuntes, como INDICE.md."""

    ruta: Path
    contenido: str
    sobrescribe: bool = False

    def describir(self, base: Path) -> tuple[str, str, str]:
        verbo = "actualizar" if self.sobrescribe else "crear"
        return (verbo, _relativa(self.ruta, base), f"{len(self.contenido.splitlines())} líneas")

    def _comprobar(self) -> None:
        if self.ruta.exists() and not self.sobrescribe:
            raise FicheroError(f"«{self.ruta}» ya existe: ha aparecido desde que se planificó.")

    def registro(self) -> dict[str, object]:
        anterior = None
        if self.ruta.exists():  # se guarda para poder restaurarlo (son índices pequeños)
            try:
                anterior = self.ruta.read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                anterior = None
        return {
            "op": "escribir",
            "ruta": str(self.ruta),
            "anterior": anterior,
            "carpetas_creadas": carpetas_nuevas(self.ruta),
        }

    def _ejecutar(self, papelera: Papelera) -> None:
        escribir_atomico(self.ruta, self.contenido)


@dataclass(frozen=True)
class GenerarConIA(Operacion):
    """Escribe un fichero cuyo contenido genera la IA *al aplicar*, no al planificar.

    Así `--simular` no gasta nada: solo dice qué se generaría.
    """

    ruta: Path
    tarea: str  # «resumen», «10 preguntas»...
    generar: Callable[[], str] = field(compare=False, repr=False)

    def describir(self, base: Path) -> tuple[str, str, str]:
        return ("generar con IA", _relativa(self.ruta, base), self.tarea)

    def _comprobar(self) -> None:
        if self.ruta.exists():
            raise FicheroError(f"«{self.ruta}» ya existe: ha aparecido desde que se planificó.")

    def registro(self) -> dict[str, object]:
        return {
            "op": "generar",
            "ruta": str(self.ruta),
            "carpetas_creadas": carpetas_nuevas(self.ruta),
        }

    def _ejecutar(self, papelera: Papelera) -> None:
        contenido = self.generar()  # puede lanzar ErrorIA: el motor lo informa
        escribir_atomico(self.ruta, contenido if contenido.endswith("\n") else contenido + "\n")


@dataclass(frozen=True)
class QuitarCarpetaVacia(Operacion):
    """Solo la usa `deshacer`: quita una carpeta que creó apuntes, si ha quedado vacía."""

    ruta: Path

    def describir(self, base: Path) -> tuple[str, str, str]:
        return ("quitar carpeta", _relativa(self.ruta, base) + "/", "si queda vacía")

    def _comprobar(self) -> None:
        pass  # si no existe o no está vacía, simplemente no se quita

    def registro(self) -> dict[str, object]:
        return {"op": "quitar-carpeta", "ruta": str(self.ruta)}

    def _ejecutar(self, papelera: Papelera) -> None:
        with contextlib.suppress(OSError):  # rmdir falla si no está vacía: es lo que queremos
            self.ruta.rmdir()


@dataclass(frozen=True)
class CrearZip(Operacion):
    ruta: Path
    #: (fichero en disco, nombre dentro del zip)
    entradas: tuple[tuple[Path, str], ...]

    def describir(self, base: Path) -> tuple[str, str, str]:
        return ("comprimir", f"{len(self.entradas)} ficheros", _relativa(self.ruta, base))

    def _comprobar(self) -> None:
        for fichero, _ in self.entradas:
            _debe_existir(fichero)
        if self.ruta.exists():
            raise FicheroError(f"«{self.ruta}» ya existe: ha aparecido desde que se planificó.")

    def registro(self) -> dict[str, object]:
        return {
            "op": "zip",
            "ruta": str(self.ruta),
            "carpetas_creadas": carpetas_nuevas(self.ruta),
        }

    def _ejecutar(self, papelera: Papelera) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = _temporal_en(self.ruta.parent, self.ruta.name)
        try:
            with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for fichero, nombre in self.entradas:
                    zf.write(fichero, nombre)
            with zipfile.ZipFile(temporal) as zf:  # verificamos antes de dar el zip por bueno
                if zf.testzip() is not None:
                    raise FicheroError(f"El zip «{self.ruta}» ha salido dañado; no lo guardo.")
            os.replace(temporal, self.ruta)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
