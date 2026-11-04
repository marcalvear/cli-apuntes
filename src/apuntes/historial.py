"""Historial de ejecuciones y cómo deshacerlas.

Cada vez que `ejecutar` aplica operaciones, se guarda en
~/.local/share/apuntes/historial.json qué se hizo exactamente: qué fichero
se movió de dónde a dónde, qué se creó... Incluso si la ejecución se
interrumpe a medias, queda registrado lo que llegó a hacerse.

`deshacer` lee ese registro y calcula las operaciones inversas, en orden
contrario. Se calculan comprobando el disco *ahora*: si un fichero ya no
está donde lo dejamos, o su sitio original está ocupado, no se toca y se
avisa. Deshacer nunca pisa nada.

Hay cosas que no se pueden deshacer automáticamente. Lo enviado a la
papelera se recupera desde la propia Papelera, y se avisa de ello.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from apuntes.disco import escribir_atomico
from apuntes.errores import ApuntesError
from apuntes.operaciones import EnviarAPapelera, Escribir, Mover, Operacion, QuitarCarpetaVacia

MAX_EJECUCIONES = 50
Estado = Literal["completa", "interrumpida", "deshecha"]


def ruta_por_defecto() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "apuntes" / "historial.json"


@dataclass
class Ejecucion:
    id: int
    fecha: str  # ISO 8601
    accion: str
    carpeta: str
    operaciones: list[dict[str, object]]
    estado: Estado = "completa"

    @property
    def deshacible(self) -> bool:
        return self.estado != "deshecha" and bool(self.operaciones)


@dataclass
class Deshacer:
    """Plan para deshacer una ejecución: operaciones inversas y lo que no se puede."""

    ejecucion: Ejecucion
    operaciones: list[Operacion] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


class Historial:
    def __init__(self, ruta: Path | None = None) -> None:
        self._ruta = ruta or ruta_por_defecto()

    # -- Lectura y escritura --

    def ejecuciones(self) -> list[Ejecucion]:
        """De la más antigua a la más reciente. Un historial dañado se trata como vacío."""
        try:
            datos = json.loads(self._ruta.read_text("utf-8"))
            return [Ejecucion(**e) for e in datos]
        except (OSError, ValueError, TypeError):
            return []

    def _guardar_todas(self, ejecuciones: list[Ejecucion]) -> None:
        recientes = ejecuciones[-MAX_EJECUCIONES:]
        texto = json.dumps([asdict(e) for e in recientes], ensure_ascii=False, indent=1)
        escribir_atomico(self._ruta, texto)

    def registrar(
        self, accion: str, carpeta: Path, operaciones: list[dict[str, object]], estado: Estado
    ) -> Ejecucion:
        todas = self.ejecuciones()
        ejecucion = Ejecucion(
            id=(todas[-1].id + 1) if todas else 1,
            fecha=datetime.now().isoformat(timespec="seconds"),
            accion=accion,
            carpeta=str(carpeta),
            operaciones=operaciones,
            estado=estado,
        )
        self._guardar_todas([*todas, ejecucion])
        return ejecucion

    def marcar_deshecha(self, id_: int) -> None:
        todas = self.ejecuciones()
        for ejecucion in todas:
            if ejecucion.id == id_:
                ejecucion.estado = "deshecha"
        self._guardar_todas(todas)

    # -- Deshacer --

    def buscar(self, id_: int | None = None) -> Ejecucion | None:
        """La ejecución `id_`, o la última que se pueda deshacer."""
        todas = self.ejecuciones()
        if id_ is None:
            return next((e for e in reversed(todas) if e.deshacible), None)
        for ejecucion in todas:
            if ejecucion.id == id_:
                if not ejecucion.deshacible:
                    raise ApuntesError(f"La ejecución #{id_} ya estaba deshecha.")
                return ejecucion
        raise ApuntesError(
            f"No hay ninguna ejecución #{id_} en el historial.",
            pista="Consulta los números con: apuntes historial",
        )

    @staticmethod
    def planificar_deshacer(ejecucion: Ejecucion) -> Deshacer:
        """Las operaciones inversas, en orden contrario, comprobando el disco actual."""
        plan = Deshacer(ejecucion)
        ocupadas: set[Path] = set()  # destinos que el propio plan ya va a ocupar
        carpetas: set[Path] = set()
        for registro in reversed(ejecucion.operaciones):
            _inversa(registro, plan, ocupadas)
            creadas = registro.get("carpetas_creadas")
            if isinstance(creadas, list):
                carpetas.update(Path(str(c)) for c in creadas)
        # Al final, y de la más profunda a la más externa: así primero se vacían.
        for carpeta in sorted(carpetas, key=lambda c: len(c.parts), reverse=True):
            if carpeta.is_dir():
                plan.operaciones.append(QuitarCarpetaVacia(carpeta))
        return plan


def _inversa(registro: dict[str, object], plan: Deshacer, ocupadas: set[Path]) -> None:
    tipo = registro.get("op")

    def avisar(motivo: str) -> None:
        plan.avisos.append(motivo)

    if tipo == "mover":
        donde_esta, de_donde_vino = Path(str(registro["destino"])), Path(str(registro["origen"]))
        if not donde_esta.exists():
            avisar(f"{donde_esta.name}: ya no está en «{donde_esta.parent}»; no se puede devolver")
            return
        mismo = de_donde_vino.exists() and _mismo_fichero(donde_esta, de_donde_vino)
        if (de_donde_vino.exists() and not mismo) or de_donde_vino in ocupadas:
            avisar(f"{de_donde_vino.name}: su sitio original está ocupado; no se toca")
            return
        plan.operaciones.append(Mover(donde_esta, de_donde_vino, verbo="devolver"))
        ocupadas.add(de_donde_vino)
        if registro.get("sobrescribe"):
            avisar(f"{donde_esta.name}: el fichero que reemplazó está en la Papelera")
    elif tipo in ("copiar", "generar", "zip"):
        creado = Path(str(registro["destino" if tipo == "copiar" else "ruta"]))
        if creado.exists():
            plan.operaciones.append(EnviarAPapelera(creado, motivo="lo creó apuntes"))
        if tipo == "copiar" and registro.get("sobrescribe"):
            avisar(f"{creado.name}: el fichero que reemplazó la copia está en la Papelera")
    elif tipo == "escribir":
        ruta = Path(str(registro["ruta"]))
        anterior = registro.get("anterior")
        if isinstance(anterior, str):
            plan.operaciones.append(Escribir(ruta, anterior, sobrescribe=ruta.exists()))
        elif ruta.exists():
            plan.operaciones.append(EnviarAPapelera(ruta, motivo="lo creó apuntes"))
    elif tipo == "papelera":
        avisar(f"{Path(str(registro['ruta'])).name}: está en la Papelera; recupéralo desde allí")
    else:
        avisar(f"operación desconocida en el historial ({tipo!r}); se ignora")


def _mismo_fichero(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)  # cambio solo de mayúsculas en macOS/Windows
    except OSError:
        return False
