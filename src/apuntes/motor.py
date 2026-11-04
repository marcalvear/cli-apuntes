"""El motor: convierte una acción de acciones.json en un plan y lo aplica.

Flujo:

    Motor.planificar(nombre, carpeta) -> Plan     (no toca el disco)
    Motor.aplicar(plan)                           (aplica operación a operación)

Para planificar un *pipeline* sin tocar nada, el motor trabaja sobre una
`Vista`: una foto del disco que se actualiza con cada operación planificada.
Así el segundo paso «ve» los ficheros donde los dejará el primero, y
`--simular` muestra exactamente lo que pasará.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from send2trash import send2trash

from apuntes.config import AccionConfig, AccionPipeline, Configuracion, Filtro
from apuntes.errores import ApuntesError, CarpetaNoValida, EjecucionInterrumpida, IANoDisponible
from apuntes.ia.proveedor import ProveedorIA
from apuntes.operaciones import (
    Copiar,
    CrearZip,
    EnviarAPapelera,
    Escribir,
    GenerarConIA,
    Mover,
    Operacion,
    Papelera,
)

#: Construye el proveedor de IA solo si alguna acción lo necesita.
FabricaIA = Callable[[], ProveedorIA]


@dataclass(frozen=True, slots=True)
class InfoVirtual:
    """Lo que el motor sabe de un fichero de la vista."""

    tamano: int
    modificado: datetime
    #: Dónde está *ahora* su contenido en el disco real (None si aún no existe).
    contenido_en: Path | None


class Vista:
    """Foto del disco que se actualiza con las operaciones planificadas."""

    def __init__(self) -> None:
        self._ficheros: dict[Path, InfoVirtual] = {}
        self._eliminados: set[Path] = set()
        self._escaneadas: dict[Path, bool] = {}  # carpeta -> recursivo

    # -- Lectura del disco --

    def escanear(self, carpeta: Path, *, recursivo: bool) -> None:
        """Incorpora los ficheros de `carpeta` (sin ocultos). Es idempotente."""
        if self._escaneadas.get(carpeta) is True or self._escaneadas.get(carpeta) is recursivo:
            return
        self._escaneadas[carpeta] = recursivo
        pendientes = [carpeta]
        while pendientes:
            actual = pendientes.pop()
            try:
                entradas = list(actual.iterdir())
            except PermissionError:
                continue  # una subcarpeta sin permiso no impide trabajar con el resto
            for entrada in entradas:
                if entrada.name.startswith("."):
                    continue
                if entrada.is_dir() and not entrada.is_symlink():
                    if recursivo:
                        pendientes.append(entrada)
                elif entrada.is_file() and entrada not in self._eliminados:
                    if entrada in self._ficheros:
                        continue
                    datos = entrada.stat()
                    self._ficheros[entrada] = InfoVirtual(
                        tamano=datos.st_size,
                        modificado=datetime.fromtimestamp(datos.st_mtime),
                        contenido_en=entrada,
                    )

    # -- Consultas --

    def existe(self, ruta: Path) -> bool:
        if ruta in self._ficheros:
            return True
        if ruta in self._eliminados:
            return False
        return ruta.exists()

    def __contains__(self, ruta: object) -> bool:
        return ruta in self._ficheros

    def info(self, ruta: Path) -> InfoVirtual:
        return self._ficheros[ruta]

    def ficheros_en(self, carpeta: Path, *, recursivo: bool) -> list[Path]:
        if recursivo:
            encontrados = [r for r in self._ficheros if r.is_relative_to(carpeta)]
        else:
            encontrados = [r for r in self._ficheros if r.parent == carpeta]
        return sorted(encontrados, key=lambda r: r.as_posix().lower())

    def nombre_libre(self, destino: Path) -> Path:
        """`destino` si está libre; si no, «nombre (2).ext», «nombre (3).ext»..."""
        if not self.existe(destino):
            return destino
        n = 2
        while True:
            candidato = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
            if not self.existe(candidato):
                return candidato
            n += 1

    # -- Actualización con lo planificado --

    def registrar(self, operacion: Operacion, *, ahora: datetime) -> None:
        match operacion:
            case Mover(origen=origen, destino=destino):
                self._ficheros[destino] = self._ficheros.pop(origen)
                self._eliminados.add(origen)
                self._eliminados.discard(destino)
            case Copiar(origen=origen, destino=destino):
                self._ficheros[destino] = self._ficheros[origen]
                self._eliminados.discard(destino)
            case EnviarAPapelera(ruta=ruta):
                self._ficheros.pop(ruta, None)
                self._eliminados.add(ruta)
            case Escribir(ruta=ruta, contenido=contenido):
                self._ficheros[ruta] = InfoVirtual(len(contenido.encode()), ahora, None)
                self._eliminados.discard(ruta)
            case GenerarConIA(ruta=ruta):
                self._ficheros[ruta] = InfoVirtual(0, ahora, None)
                self._eliminados.discard(ruta)
            case CrearZip(ruta=ruta):
                self._ficheros[ruta] = InfoVirtual(0, ahora, None)
                self._eliminados.discard(ruta)
            case _:
                raise AssertionError(f"operación desconocida: {operacion!r}")


def seleccionar(vista: Vista, carpeta: Path, filtro: Filtro, *, ahora: datetime) -> list[Path]:
    """Los ficheros de `carpeta` que cumplen todas las condiciones del filtro."""
    vista.escanear(carpeta, recursivo=filtro.recursivo)
    patron = re.compile(filtro.patron) if filtro.patron else None
    resultado = []
    for ruta in vista.ficheros_en(carpeta, recursivo=filtro.recursivo):
        info = vista.info(ruta)
        if filtro.extensiones and ruta.suffix.lower() not in filtro.extensiones:
            continue
        if patron and not patron.search(ruta.name):
            continue
        edad = ahora - info.modificado
        if filtro.mas_antiguo_que_dias is not None and edad <= timedelta(
            days=filtro.mas_antiguo_que_dias
        ):
            continue
        if filtro.mas_reciente_que_dias is not None and edad >= timedelta(
            days=filtro.mas_reciente_que_dias
        ):
            continue
        resultado.append(ruta)
    return resultado


@dataclass
class Paso:
    """Lo que hará una acción simple (o un paso de un pipeline)."""

    accion: AccionConfig
    carpeta: Path
    operaciones: list[Operacion] = field(default_factory=list)
    #: Ficheros que se dejan sin tocar y por qué.
    avisos: list[str] = field(default_factory=list)
    #: Si el paso entero se salta (p. ej. IA no disponible en un pipeline), el motivo.
    omitido: str | None = None

    @property
    def debe_confirmar(self) -> bool:
        if self.accion.confirmar is not None:
            return self.accion.confirmar and bool(self.operaciones)
        return self.accion.destructiva or any(op.destructiva for op in self.operaciones)


@dataclass
class Plan:
    accion: AccionConfig
    carpeta: Path
    pasos: list[Paso]

    @property
    def operaciones(self) -> list[Operacion]:
        return [op for paso in self.pasos for op in paso.operaciones]

    @property
    def vacio(self) -> bool:
        return not self.operaciones

    @property
    def debe_confirmar(self) -> bool:
        return any(paso.debe_confirmar for paso in self.pasos)


@dataclass
class ContextoPlan:
    """Lo que una acción necesita para planificar un paso."""

    carpeta: Path
    vista: Vista
    ahora: datetime
    configuracion: Configuracion
    paso: Paso
    _ia: Callable[[], ProveedorIA]

    def ia(self) -> ProveedorIA:
        """El proveedor de IA, ya comprobado (lanza IANoDisponible si no se puede usar)."""
        return self._ia()

    def anadir(self, operacion: Operacion) -> None:
        """Añade la operación al paso y actualiza la vista (para los siguientes ficheros)."""
        self.paso.operaciones.append(operacion)
        self.vista.registrar(operacion, ahora=self.ahora)

    def avisar(self, ruta: Path, motivo: str) -> None:
        self.paso.avisos.append(f"{_relativa(ruta, self.carpeta)}: {motivo}")


def _relativa(ruta: Path, base: Path) -> str:
    try:
        return ruta.relative_to(base).as_posix()
    except ValueError:
        return str(ruta)


class Motor:
    """Planifica y aplica acciones de una configuración ya validada."""

    def __init__(
        self,
        configuracion: Configuracion,
        *,
        papelera: Papelera | None = None,
        ahora: datetime | None = None,
        ia: FabricaIA | None = None,
    ) -> None:
        self._configuracion = configuracion
        self._papelera = papelera or _papelera_del_sistema
        self._ahora = ahora
        self._fabrica_ia = ia or _proveedor_por_defecto
        self._proveedor: ProveedorIA | None = None
        self._ia_no_disponible: IANoDisponible | None = None

    def _ia(self) -> ProveedorIA:
        """Crea y comprueba el proveedor una sola vez por ejecución."""
        if self._ia_no_disponible is not None:
            raise self._ia_no_disponible
        if self._proveedor is None:
            proveedor = self._fabrica_ia()
            try:
                proveedor.comprobar()
            except IANoDisponible as error:
                self._ia_no_disponible = error
                raise
            self._proveedor = proveedor
        return self._proveedor

    def carpeta_de(self, accion: AccionConfig, carpeta: Path | None) -> Path:
        """CARPETA de la orden > `origen` de la acción > carpeta actual."""
        if carpeta is not None:
            elegida = carpeta
        elif accion.origen is not None:
            elegida = Path(accion.origen)
        else:
            elegida = Path.cwd()
        elegida = elegida.expanduser()
        if not elegida.exists():
            raise CarpetaNoValida(f"La carpeta «{elegida}» no existe.")
        if not elegida.is_dir():
            raise CarpetaNoValida(f"«{elegida}» es un fichero, no una carpeta.")
        return elegida.resolve()

    def planificar(self, nombre: str, carpeta: Path | None = None) -> Plan:
        """Calcula todo lo que haría la acción `nombre`, sin tocar el disco."""
        from apuntes.acciones import Accion  # import local: acciones depende del motor

        principal = self._configuracion.accion(nombre)
        ahora = self._ahora or datetime.now()
        vista = Vista()
        pasos: list[Paso] = []
        es_pipeline = isinstance(principal, AccionPipeline)
        for accion_cfg in self._configuracion.pasos_de(principal):
            ejecutor = Accion.desde_config(accion_cfg)  # falla pronto si no se puede ejecutar
            carpeta_paso = self.carpeta_de(accion_cfg, carpeta)
            paso = Paso(accion=accion_cfg, carpeta=carpeta_paso)
            pasos.append(paso)
            if accion_cfg.USA_IA:
                try:
                    self._ia()
                except IANoDisponible as error:
                    if not es_pipeline:
                        raise
                    # Sin IA, el pipeline sigue con los pasos que no la necesitan.
                    paso.omitido = error.mensaje
                    continue
            contexto = ContextoPlan(carpeta_paso, vista, ahora, self._configuracion, paso, self._ia)
            ficheros = seleccionar(vista, carpeta_paso, accion_cfg.filtro, ahora=ahora)
            ejecutor.planificar(ficheros, contexto)
        return Plan(accion=principal, carpeta=self.carpeta_de(principal, carpeta), pasos=pasos)

    def aplicar(self, plan: Plan, *, al_aplicar: Callable[[Operacion], None] | None = None) -> int:
        """Aplica el plan en orden. Si una operación falla, se detiene y lo explica.

        `al_aplicar` se llama tras cada operación (para mostrar progreso).
        Devuelve cuántas operaciones se aplicaron.
        """
        aplicadas = 0
        for operacion in plan.operaciones:
            try:
                operacion.aplicar(self._papelera)
            except ApuntesError as error:  # fallo de disco o de la IA a mitad
                total = len(plan.operaciones)
                raise EjecucionInterrumpida(
                    f"{error.mensaje} Se detiene la ejecución: {aplicadas} de {total} "
                    "operaciones ya estaban hechas y el resto no se ha tocado.",
                    aplicadas=aplicadas,
                    pista="Vuelve a lanzar la acción con --simular para ver qué queda pendiente.",
                ) from error
            aplicadas += 1
            if al_aplicar is not None:
                al_aplicar(operacion)
        return aplicadas


def _proveedor_por_defecto() -> ProveedorIA:
    from apuntes.ia.entorno import crear_proveedor  # el SDK solo se importa si hace falta

    return crear_proveedor()


def _papelera_del_sistema(ruta: Path) -> None:
    send2trash(ruta)
