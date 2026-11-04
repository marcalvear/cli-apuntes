"""Los tipos de acción: cada uno sabe convertir unos ficheros en operaciones.

Cada clase se registra con su `tipo` de acciones.json, y la fábrica
`Accion.desde_config()` elige la clase correcta. Añadir un tipo nuevo es
escribir una subclase; el motor y la CLI no cambian.

Las acciones solo *planifican*: añaden operaciones al contexto y nunca
tocan el disco.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

from apuntes import config as cfg
from apuntes.clasificador import Clasificador
from apuntes.errores import AccionNoValida, DocumentoNoSoportado
from apuntes.ficheros import tamano_legible, tipo_de
from apuntes.ia.documento import Documento
from apuntes.motor import ContextoPlan
from apuntes.operaciones import Copiar, CrearZip, EnviarAPapelera, Escribir, GenerarConIA, Mover


class Accion(ABC):
    """Base de todos los tipos de acción."""

    _registro: ClassVar[dict[str, type[Accion]]] = {}
    tipo: ClassVar[str]

    def __init_subclass__(cls, *, tipo: str | None = None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if tipo is not None:
            assert tipo in cfg.TIPOS_ACCION, f"tipo sin modelo en config.py: {tipo}"
            assert tipo not in Accion._registro, f"tipo registrado dos veces: {tipo}"
            cls.tipo = tipo
            Accion._registro[tipo] = cls

    def __init__(self, config: cfg.AccionConfig) -> None:
        self.config = config

    @staticmethod
    def desde_config(config: cfg.AccionConfig) -> Accion:
        """Fábrica: la clase que ejecuta el `tipo` de esta acción de acciones.json."""
        clase = Accion._registro.get(config.tipo)
        if clase is None:
            if config.USA_IA:
                raise AccionNoValida(
                    f"La acción «{config.nombre}» usa IA ({config.tipo}), "
                    "que todavía no está disponible en esta versión."
                )
            raise AccionNoValida(f"El tipo «{config.tipo}» no se puede ejecutar directamente.")
        return clase(config)

    @abstractmethod
    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        """Añade a `ctx` las operaciones necesarias para los `ficheros` seleccionados."""


# --- Utilidades comunes -----------------------------------------------------


def _resolver(plantilla: str, carpeta: Path, **valores: object) -> Path:
    """Aplica marcadores a una ruta. Relativa → dentro de la carpeta de trabajo."""
    ruta = Path(plantilla.format(**valores)).expanduser()
    return ruta if ruta.is_absolute() else carpeta / ruta


def _asignatura(ruta: Path, ctx: ContextoPlan) -> str | None:
    resultado = Clasificador(ctx.configuracion.asignaturas).clasificar(ruta.name)
    if resultado.asignatura is None:
        ctx.avisar(ruta, f"sin asignatura ({resultado.motivo}); no se toca")
    return resultado.asignatura


def _destino_con_conflicto(
    destino: Path, ctx: ContextoPlan, origen: Path, politica: cfg.Conflicto
) -> tuple[Path | None, bool]:
    """Aplica `si_existe`. Devuelve (destino final o None si se salta, ¿sobrescribe?)."""
    if not ctx.vista.existe(destino):
        return destino, False
    if politica == "saltar":
        ctx.avisar(origen, f"ya existe «{destino.name}» en el destino; se salta")
        return None, False
    if politica == "sobrescribir":
        return destino, True
    return ctx.vista.nombre_libre(destino), False


# --- Tipos ------------------------------------------------------------------


class _MoverOCopiar(Accion):
    config: cfg.AccionMover | cfg.AccionCopiar

    @abstractmethod
    def _operacion(self, origen: Path, destino: Path, sobrescribe: bool) -> Mover | Copiar: ...

    def _asignatura_de(self, origen: Path, ctx: ContextoPlan) -> str | None:
        """Por defecto, por palabras clave del nombre. ia-clasificar lo sobrescribe."""
        return _asignatura(origen, ctx)

    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        for origen in ficheros:
            asignatura = self._asignatura_de(origen, ctx) if self.config.usa_asignatura else None
            if self.config.usa_asignatura and asignatura is None:
                continue
            carpeta_destino = _resolver(
                self.config.destino,
                ctx.carpeta,
                asignatura=asignatura,
                tipo=tipo_de(origen),
                fecha=ctx.vista.info(origen).modificado,
            )
            destino = carpeta_destino / origen.name
            if destino == origen:
                continue  # ya está en su sitio
            destino, sobrescribe = _destino_con_conflicto(
                destino, ctx, origen, self.config.si_existe
            )
            if destino is not None:
                ctx.anadir(self._operacion(origen, destino, sobrescribe))


class MoverFicheros(_MoverOCopiar, tipo="mover"):
    def _operacion(self, origen: Path, destino: Path, sobrescribe: bool) -> Mover:
        return Mover(origen, destino, sobrescribe=sobrescribe)


class CopiarFicheros(_MoverOCopiar, tipo="copiar"):
    def _operacion(self, origen: Path, destino: Path, sobrescribe: bool) -> Copiar:
        return Copiar(origen, destino, sobrescribe=sobrescribe)


class RenombrarFicheros(Accion, tipo="renombrar"):
    config: cfg.AccionRenombrar

    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        # El contador {n} sigue el orden cronológico: tema 1 antes que tema 2.
        ordenados = sorted(ficheros, key=lambda r: (ctx.vista.info(r).modificado, r.name))
        n = 0
        for origen in ordenados:
            asignatura = _asignatura(origen, ctx) if self.config.usa_asignatura else None
            if self.config.usa_asignatura and asignatura is None:
                continue
            n += 1
            nuevo = self.config.plantilla.format(
                fecha=ctx.vista.info(origen).modificado,
                n=n,
                nombre=origen.stem,
                ext=origen.suffix,
                asignatura=asignatura,
            ).strip()
            if not nuevo or nuevo.startswith("."):
                ctx.avisar(origen, f"la plantilla da un nombre no válido («{nuevo}»); se salta")
                continue
            destino = origen.with_name(nuevo)
            if destino == origen:
                continue
            if destino.name.lower() != origen.name.lower():  # cambiar solo mayúsculas no choca
                destino = ctx.vista.nombre_libre(destino)
            ctx.anadir(Mover(origen, destino, verbo="renombrar"))


class BorrarFicheros(Accion, tipo="borrar"):
    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        for ruta in ficheros:
            ctx.anadir(EnviarAPapelera(ruta))


def _huella(ruta: Path) -> str:
    resumen = hashlib.sha256()
    with ruta.open("rb") as fichero:
        for bloque in iter(lambda: fichero.read(1 << 20), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


class DeduplicarFicheros(Accion, tipo="deduplicar"):
    config: cfg.AccionDeduplicar

    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        # Primero por tamaño (gratis) y solo si coincide, por contenido (SHA-256).
        por_tamano: dict[int, list[Path]] = defaultdict(list)
        for ruta in ficheros:
            info = ctx.vista.info(ruta)
            if info.contenido_en is not None and info.tamano > 0:
                por_tamano[info.tamano].append(ruta)

        for candidatos in por_tamano.values():
            if len(candidatos) < 2:
                continue
            por_huella: dict[str, list[Path]] = defaultdict(list)
            for ruta in candidatos:
                contenido = ctx.vista.info(ruta).contenido_en
                assert contenido is not None
                try:
                    por_huella[_huella(contenido)].append(ruta)
                except OSError:
                    ctx.avisar(ruta, "no se puede leer; no se compara")
            for grupo in por_huella.values():
                if len(grupo) < 2:
                    continue
                original = min(grupo, key=self._criterio(ctx))
                for copia in grupo:
                    if copia != original:
                        motivo = f"copia de {original.name}"
                        ctx.anadir(EnviarAPapelera(copia, motivo=motivo))

    def _criterio(self, ctx: ContextoPlan) -> Callable[[Path], tuple[object, ...]]:
        """Clave de ordenación: el mínimo es el fichero que se conserva."""
        conservar = self.config.conservar
        if conservar == "mas-reciente":
            return lambda r: (-ctx.vista.info(r).modificado.timestamp(), r.name)
        if conservar == "nombre-mas-corto":
            return lambda r: (len(r.name), r.name)
        return lambda r: (ctx.vista.info(r).modificado, len(r.name), r.name)


class ArchivarFicheros(Accion, tipo="archivar"):
    config: cfg.AccionArchivar

    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        zip_destino = _resolver(self.config.destino, ctx.carpeta, fecha=ctx.ahora)
        ficheros = [f for f in ficheros if f != zip_destino and f.suffix.lower() != ".zip"]
        if not ficheros:
            return
        zip_destino = ctx.vista.nombre_libre(zip_destino)
        entradas = tuple((f, f.relative_to(ctx.carpeta).as_posix()) for f in ficheros)
        ctx.anadir(CrearZip(zip_destino, entradas))
        if self.config.borrar_originales:
            for fichero in ficheros:
                ctx.anadir(EnviarAPapelera(fichero, motivo=f"guardado en {zip_destino.name}"))


class CrearIndice(Accion, tipo="indice"):
    config: cfg.AccionIndice

    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        indice = _resolver(self.config.fichero, ctx.carpeta)
        ficheros = [f for f in ficheros if f != indice]
        contenido = self._markdown(ficheros, ctx)
        existe = ctx.vista.existe(indice)
        if existe and _contenido_actual(indice, ctx) == contenido:
            return  # ya está al día: repetir la acción no cambia nada
        ctx.anadir(Escribir(indice, contenido, sobrescribe=existe))

    def _markdown(self, ficheros: list[Path], ctx: ContextoPlan) -> str:
        titulo = self.config.titulo or f"Índice de {ctx.carpeta.name}"
        lineas = [
            f"# {titulo}",
            "",
            f"_Generado por apuntes el {ctx.ahora:%Y-%m-%d} · {len(ficheros)} ficheros._",
        ]
        grupos: dict[str, list[Path]] = defaultdict(list)
        for fichero in ficheros:
            relativa = fichero.relative_to(ctx.carpeta)
            grupos[relativa.parent.as_posix()].append(fichero)
        for grupo in sorted(grupos, key=lambda g: (g != ".", g.lower())):
            nombre_grupo = "Carpeta principal" if grupo == "." else grupo
            lineas += ["", f"## {nombre_grupo}", "", "| Fichero | Tipo | Tamaño | Fecha |"]
            lineas.append("|---|---|---:|---|")
            for fichero in grupos[grupo]:
                info = ctx.vista.info(fichero)
                enlace = quote(fichero.relative_to(ctx.carpeta).as_posix())
                nombre = fichero.name.replace("|", "\\|")
                lineas.append(
                    f"| [{nombre}]({enlace}) | {tipo_de(fichero)} | "
                    f"{tamano_legible(info.tamano)} | {info.modificado:%Y-%m-%d} |"
                )
        return "\n".join(lineas) + "\n"


def _contenido_actual(ruta: Path, ctx: ContextoPlan) -> str | None:
    """El texto que hay ahora en `ruta` según la vista (None si no se puede leer)."""
    contenido_en = ctx.vista.info(ruta).contenido_en if ruta in ctx.vista else ruta
    if contenido_en is None:
        return None
    try:
        return contenido_en.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# --- Tipos con IA -----------------------------------------------------------


def _documento(ruta: Path, ctx: ContextoPlan) -> Documento | None:
    """Lee el fichero para la IA; si no se puede, avisa y devuelve None."""
    contenido_en = ctx.vista.info(ruta).contenido_en
    if contenido_en is None:
        ctx.avisar(ruta, "se crea en este mismo plan; la IA lo leerá en la próxima ejecución")
        return None
    try:
        return Documento.desde_fichero(contenido_en, nombre=ruta.name)
    except DocumentoNoSoportado as error:
        ctx.avisar(ruta, error.mensaje)
        return None


#: Ficheros que genera apuntes: la IA nunca los resume ni los clasifica.
SUFIJOS_GENERADOS = (".resumen.md", ".preguntas.md")


def _es_generado(ruta: Path) -> bool:
    return ruta.name.lower().endswith(SUFIJOS_GENERADOS)


class ClasificarConIA(MoverFicheros, tipo="ia-clasificar"):
    """Como `mover` a {asignatura}, pero la asignatura la decide la IA leyendo el contenido.

    Se llama a la IA al planificar (hace falta para saber el destino); la caché
    evita pagar dos veces entre `--simular` y la ejecución real.
    """

    config: cfg.AccionIAClasificar  # type: ignore[assignment]

    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        super().planificar([f for f in ficheros if not _es_generado(f)], ctx)

    def _asignatura_de(self, origen: Path, ctx: ContextoPlan) -> str | None:
        documento = _documento(origen, ctx)
        if documento is None:
            return None
        clasificacion = ctx.ia().clasificar(documento, ctx.configuracion.asignaturas)
        if clasificacion.asignatura is None:
            ctx.avisar(origen, f"según la IA no es de ninguna asignatura ({clasificacion.motivo})")
            return None
        if not clasificacion.fiable:
            ctx.avisar(
                origen,
                f"la IA duda ({clasificacion.asignatura}, confianza baja: "
                f"{clasificacion.motivo}); no se toca",
            )
            return None
        return clasificacion.asignatura


class _GenerarDocumento(Accion):
    """Base de las acciones que escriben un .md generado por la IA junto a cada documento."""

    config: cfg.AccionIAResumir | cfg.AccionIAPreguntas
    sufijo: ClassVar[str]

    @abstractmethod
    def _tarea(self) -> str: ...

    @abstractmethod
    def _generar(self, ctx: ContextoPlan, documento: Documento) -> str: ...

    def planificar(self, ficheros: list[Path], ctx: ContextoPlan) -> None:
        for origen in ficheros:
            if _es_generado(origen):
                continue  # no se resume un resumen
            destino = self.config.destino
            carpeta = _resolver(destino, ctx.carpeta) if destino else origen.parent
            salida = carpeta / f"{origen.stem}{self.sufijo}"
            if ctx.vista.existe(salida):
                continue  # ya generado: no se vuelve a pagar (bórralo para regenerarlo)
            documento = _documento(origen, ctx)
            if documento is None:
                continue
            ctx.anadir(
                GenerarConIA(
                    salida,
                    tarea=f"{self._tarea()} de {origen.name}",
                    generar=lambda d=documento: self._generar(ctx, d),
                )
            )


class ResumirConIA(_GenerarDocumento, tipo="ia-resumir"):
    sufijo = ".resumen.md"

    def _tarea(self) -> str:
        return "resumen"

    def _generar(self, ctx: ContextoPlan, documento: Documento) -> str:
        return ctx.ia().resumir(documento)


class PreguntasConIA(_GenerarDocumento, tipo="ia-preguntas"):
    sufijo = ".preguntas.md"
    config: cfg.AccionIAPreguntas

    def _tarea(self) -> str:
        return f"{self.config.numero} preguntas"

    def _generar(self, ctx: ContextoPlan, documento: Documento) -> str:
        return ctx.ia().preguntas(documento, self.config.numero)


def tipos_ejecutables() -> frozenset[str]:
    """Los tipos de acciones.json que ya tienen clase que los ejecute."""
    return frozenset(Accion._registro)
