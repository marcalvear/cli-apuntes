"""Esquema y carga de acciones.json.

Las acciones no están en el código: se describen en un fichero JSON que
se valida por completo *antes* de ejecutar nada. Cada tipo de acción es
un modelo Pydantic; el campo `tipo` decide qué modelo se aplica.

Todos los modelos prohíben campos desconocidos (`extra="forbid"`), así
que una errata como "destnio" se detecta en lugar de ignorarse.
"""

from __future__ import annotations

import json
import os
import re
import string
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from apuntes.errores import AccionNoValida, ConfigError

VERSION_ESQUEMA = 1
NOMBRE_FICHERO = "acciones.json"
VARIABLE_ENTORNO = "APUNTES_CONFIG"

_PATRON_NOMBRE = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# --- Piezas comunes ---------------------------------------------------------


class Filtro(_Modelo):
    """Qué ficheros afectan a una acción. Todas las condiciones deben cumplirse."""

    extensiones: list[str] | None = Field(
        default=None, min_length=1, description='Extensiones aceptadas, p. ej. [".pdf"].'
    )
    patron: str | None = Field(
        default=None, description="Expresión regular que debe encontrarse en el nombre."
    )
    mas_antiguo_que_dias: int | None = Field(default=None, ge=0)
    mas_reciente_que_dias: int | None = Field(default=None, ge=0)
    recursivo: bool = Field(default=False, description="Incluye subcarpetas.")

    @field_validator("extensiones")
    @classmethod
    def _normalizar_extensiones(cls, valor: list[str] | None) -> list[str] | None:
        """'PDF' y '.pdf' significan lo mismo: se guardan como '.pdf'."""
        if valor is None:
            return None
        normalizadas = []
        for ext in valor:
            ext = ext.strip().lower()
            if not ext or ext == ".":
                raise ValueError("hay una extensión vacía")
            normalizadas.append(ext if ext.startswith(".") else f".{ext}")
        return normalizadas

    @field_validator("patron")
    @classmethod
    def _patron_compila(cls, valor: str | None) -> str | None:
        if valor is not None:
            try:
                re.compile(valor)
            except re.error as error:
                raise ValueError(f"no es una expresión regular válida ({error})") from None
        return valor


class Asignatura(_Modelo):
    """Una asignatura y las pistas para reconocer su material."""

    nombre: str = Field(min_length=1, description="Se usa en {asignatura} y como carpeta.")
    palabras_clave: list[str] = Field(
        default_factory=list, description="Palabras que delatan la asignatura en un nombre."
    )


class _AccionBase(_Modelo):
    nombre: str = Field(pattern=_PATRON_NOMBRE, max_length=60)
    descripcion: str = Field(min_length=1, max_length=200)
    origen: str | None = Field(
        default=None, description="Carpeta de trabajo; si falta, la CARPETA de la orden."
    )
    filtro: Filtro = Field(default_factory=Filtro)
    confirmar: bool | None = Field(
        default=None, description="Preguntar antes de actuar. Por defecto depende del tipo."
    )

    #: ¿Puede borrar o sobrescribir algo? Las destructivas confirman por defecto.
    _DESTRUCTIVA: ClassVar[bool] = False
    #: ¿Necesita el proveedor de IA?
    USA_IA: ClassVar[bool] = False

    @property
    def destructiva(self) -> bool:
        return self._DESTRUCTIVA

    @property
    def debe_confirmar(self) -> bool:
        return self.destructiva if self.confirmar is None else self.confirmar


Conflicto = Literal["renombrar", "saltar", "sobrescribir"]


# --- Tipos de acción --------------------------------------------------------


MARCADORES_NOMBRE = frozenset({"fecha", "n", "nombre", "ext", "asignatura"})
MARCADORES_DESTINO = frozenset({"fecha", "asignatura", "tipo"})


def marcadores_de(plantilla: str) -> set[str]:
    """{'fecha', 'n'} para '{fecha:%Y}_{n:03}'. Lanza ValueError si está mal formada."""
    try:
        return {campo for _, campo, _, _ in string.Formatter().parse(plantilla) if campo}
    except ValueError as error:
        raise ValueError(f"plantilla mal formada ({error})") from None


def _comprobar_marcadores(plantilla: str, permitidos: frozenset[str]) -> str:
    desconocidos = marcadores_de(plantilla) - permitidos
    if desconocidos:
        validos = ", ".join(f"{{{m}}}" for m in sorted(permitidos))
        raise ValueError(f"marcador desconocido {{{sorted(desconocidos)[0]}}}; válidos: {validos}")
    return plantilla


class _AccionConDestino(_AccionBase):
    destino: str = Field(
        min_length=1,
        description="Carpeta destino; relativa a la carpeta de trabajo. Admite {asignatura}.",
    )
    si_existe: Conflicto = "renombrar"

    @field_validator("destino")
    @classmethod
    def _destino_valido(cls, valor: str) -> str:
        return _comprobar_marcadores(valor, MARCADORES_DESTINO)

    @property
    def usa_asignatura(self) -> bool:
        return "asignatura" in marcadores_de(self.destino)


class AccionMover(_AccionConDestino):
    tipo: Literal["mover"]


class AccionCopiar(_AccionConDestino):
    tipo: Literal["copiar"]


class AccionRenombrar(_AccionBase):
    tipo: Literal["renombrar"]
    plantilla: str = Field(
        min_length=1, description="Ej.: {fecha:%Y-%m-%d}_{nombre}{ext}. Ver README."
    )

    @field_validator("plantilla")
    @classmethod
    def _plantilla_valida(cls, valor: str) -> str:
        if "/" in valor or "\\" in valor:
            raise ValueError("la plantilla es para el nombre, no puede contener '/' ni '\\'")
        return _comprobar_marcadores(valor, MARCADORES_NOMBRE)

    @property
    def usa_asignatura(self) -> bool:
        return "asignatura" in marcadores_de(self.plantilla)


class AccionBorrar(_AccionBase):
    """Envía ficheros a la papelera del sistema (nunca borra de forma definitiva)."""

    tipo: Literal["borrar"]
    _DESTRUCTIVA: ClassVar[bool] = True


class AccionDeduplicar(_AccionBase):
    """Detecta ficheros con el mismo contenido y envía las copias a la papelera."""

    tipo: Literal["deduplicar"]
    conservar: Literal["mas-antiguo", "mas-reciente", "nombre-mas-corto"] = "mas-antiguo"
    _DESTRUCTIVA: ClassVar[bool] = True


class AccionArchivar(_AccionBase):
    tipo: Literal["archivar"]
    destino: str = Field(min_length=1, description="Ruta del .zip que se creará. Admite {fecha}.")
    borrar_originales: bool = False

    @field_validator("destino")
    @classmethod
    def _destino_zip(cls, valor: str) -> str:
        if not valor.lower().endswith(".zip"):
            raise ValueError("debe terminar en .zip")
        return _comprobar_marcadores(valor, frozenset({"fecha"}))

    @property
    def destructiva(self) -> bool:
        return self.borrar_originales


class AccionIndice(_AccionBase):
    """Genera un índice Markdown con el material de la carpeta."""

    tipo: Literal["indice"]
    fichero: str = Field(default="INDICE.md", min_length=1)
    titulo: str | None = None


class AccionIAClasificar(_AccionConDestino):
    """La IA lee cada fichero, decide su asignatura y lo mueve a `destino`."""

    tipo: Literal["ia-clasificar"]
    destino: str = Field(default="{asignatura}", min_length=1)
    USA_IA: ClassVar[bool] = True


class AccionIAResumir(_AccionBase):
    tipo: Literal["ia-resumir"]
    destino: str | None = Field(
        default=None, description="Carpeta de resúmenes; por defecto, junto al original."
    )
    USA_IA: ClassVar[bool] = True


class AccionIAPreguntas(_AccionBase):
    tipo: Literal["ia-preguntas"]
    destino: str | None = None
    numero: int = Field(default=10, ge=1, le=50)
    USA_IA: ClassVar[bool] = True


class AccionPipeline(_AccionBase):
    """Ejecuta varias acciones en orden sobre los mismos ficheros."""

    tipo: Literal["pipeline"]
    pasos: list[str] = Field(min_length=2, description="Nombres de otras acciones, en orden.")


AccionConfig = (
    AccionMover
    | AccionCopiar
    | AccionRenombrar
    | AccionBorrar
    | AccionDeduplicar
    | AccionArchivar
    | AccionIndice
    | AccionIAClasificar
    | AccionIAResumir
    | AccionIAPreguntas
    | AccionPipeline
)
Accion = Annotated[AccionConfig, Field(discriminator="tipo")]

TIPOS_ACCION: tuple[str, ...] = (
    "mover", "copiar", "renombrar", "borrar", "deduplicar", "archivar", "indice",
    "ia-clasificar", "ia-resumir", "ia-preguntas", "pipeline",
)  # fmt: skip


# --- Fichero completo -------------------------------------------------------


class Configuracion(_Modelo):
    """El contenido completo y validado de acciones.json."""

    version: Literal[1]
    asignaturas: list[Asignatura] = Field(default_factory=list)
    acciones: list[Accion] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherencia(self) -> Self:
        nombres = [a.nombre for a in self.acciones]
        repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
        if repetidos:
            raise ValueError(f"nombres de acción repetidos: {', '.join(repetidos)}")

        nombres_asignaturas = [a.nombre for a in self.asignaturas]
        if len(set(nombres_asignaturas)) != len(nombres_asignaturas):
            raise ValueError("hay asignaturas con el mismo nombre")

        if not self.asignaturas:
            for accion in self.acciones:
                if isinstance(accion, AccionIAClasificar) or getattr(
                    accion, "usa_asignatura", False
                ):
                    raise ValueError(
                        f"la acción '{accion.nombre}' usa asignaturas, pero falta la lista "
                        "'asignaturas' en el fichero"
                    )

        por_nombre = {a.nombre: a for a in self.acciones}
        for accion in self.acciones:
            if isinstance(accion, AccionPipeline):
                for paso in accion.pasos:
                    if paso not in por_nombre:
                        raise ValueError(
                            f"el pipeline '{accion.nombre}' usa '{paso}', que no existe"
                        )
                    if isinstance(por_nombre[paso], AccionPipeline):
                        raise ValueError(
                            f"el pipeline '{accion.nombre}' no puede incluir "
                            f"otro pipeline ('{paso}')"
                        )
        return self

    # -- Consultas --

    def accion(self, nombre: str) -> AccionConfig:
        """Devuelve la acción con ese nombre o lanza AccionNoValida con sugerencias."""
        for accion in self.acciones:
            if accion.nombre == nombre:
                return accion
        disponibles = ", ".join(a.nombre for a in self.acciones)
        raise AccionNoValida(
            f"No hay ninguna acción llamada «{nombre}».",
            pista=f"Acciones disponibles: {disponibles}. Lista completa con: apuntes acciones",
        )

    def pasos_de(self, accion: AccionConfig) -> Iterator[AccionConfig]:
        """Las acciones simples que componen `accion` (ella misma si no es pipeline)."""
        if isinstance(accion, AccionPipeline):
            for paso in accion.pasos:
                yield self.accion(paso)
        else:
            yield accion

    # -- Fábricas --

    @classmethod
    def desde_texto(cls, texto: str, *, origen: str = NOMBRE_FICHERO) -> Configuracion:
        """Valida el texto de un acciones.json. Lanza ConfigError con todos los problemas."""
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as error:
            raise ConfigError(
                f"«{origen}» no es JSON válido: {_traducir_json(error.msg)} "
                f"(línea {error.lineno}, columna {error.colno}).",
                pista="Revisa comas, comillas dobles y llaves en esa zona.",
            ) from None

        if not isinstance(datos, dict):
            raise ConfigError(f"«{origen}» debe contener un objeto JSON {{ ... }} en la raíz.")
        version = datos.get("version")
        if version is not None and version != VERSION_ESQUEMA:
            raise ConfigError(
                f"«{origen}» usa la versión de esquema {version!r} y esta versión de apuntes "
                f"solo entiende la {VERSION_ESQUEMA}.",
                pista="Actualiza apuntes o revisa el campo 'version'.",
            )
        try:
            return cls.model_validate(datos)
        except ValidationError as error:
            problemas = [_describir(e, datos) for e in error.errors()]
            raise ConfigError(
                f"«{origen}» tiene {len(problemas)} problema(s):",
                problemas=problemas,
                pista="Comprueba el esquema en el README o ejecuta: apuntes validar",
            ) from None

    @classmethod
    def desde_fichero(cls, ruta: Path) -> Configuracion:
        """Lee y valida un acciones.json del disco."""
        ruta = ruta.expanduser()
        try:
            texto = ruta.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ConfigError(
                f"No encuentro el fichero de acciones «{ruta}».",
                pista="Crea uno de ejemplo con: apuntes init  (o indica otro con --config RUTA)",
            ) from None
        except IsADirectoryError:
            raise ConfigError(f"«{ruta}» es una carpeta, no un fichero de acciones.") from None
        except UnicodeDecodeError:
            raise ConfigError(f"«{ruta}» no es un fichero de texto UTF-8.") from None
        except OSError as error:
            raise ConfigError(f"No puedo leer «{ruta}»: {error.strerror}.") from None
        return cls.desde_texto(texto, origen=str(ruta))


def localizar(explicita: Path | None = None, *, cwd: Path | None = None) -> Path:
    """Decide qué acciones.json usar, por orden de prioridad:

    1. La ruta de --config.
    2. La variable de entorno APUNTES_CONFIG.
    3. ./acciones.json en la carpeta actual.
    4. ~/.config/apuntes/acciones.json (configuración del usuario).

    Si no existe ninguna, devuelve ./acciones.json para que el error lo nombre.
    """
    if explicita is not None:
        return explicita.expanduser()
    if entorno := os.environ.get(VARIABLE_ENTORNO):
        return Path(entorno).expanduser()
    local = (cwd or Path.cwd()) / NOMBRE_FICHERO
    if local.exists():
        return local
    usuario = Path.home() / ".config" / "apuntes" / NOMBRE_FICHERO
    if usuario.exists():
        return usuario
    return local


# --- Mensajes de error humanos ---------------------------------------------

_TRADUCCIONES_JSON = {
    "Expecting ',' delimiter": "falta una coma",
    "Expecting ':' delimiter": "faltan los dos puntos ':'",
    "Expecting value": "se esperaba un valor",
    "Expecting property name enclosed in double quotes": (
        "los nombres de campo van entre comillas dobles (o sobra una coma)"
    ),
    "Unterminated string starting at": "una cadena no tiene comilla de cierre",
    "Extra data": "sobra contenido después del objeto principal",
}

_TRADUCCIONES_PYDANTIC = {
    "missing": "falta este campo obligatorio",
    "extra_forbidden": "campo desconocido (¿una errata?)",
    "string_type": "debe ser un texto",
    "int_type": "debe ser un número entero",
    "int_parsing": "debe ser un número entero",
    "bool_type": "debe ser true o false",
    "bool_parsing": "debe ser true o false",
    "list_type": "debe ser una lista [ ... ]",
    "dict_type": "debe ser un objeto { ... }",
    "model_type": "debe ser un objeto { ... }",
    "too_short": "no puede estar vacío",
    "string_too_short": "no puede estar vacío",
    "string_too_long": "es demasiado largo",
    "string_pattern_mismatch": "solo minúsculas, números y guiones (p. ej. ordenar-descargas)",
    "greater_than_equal": "no puede ser negativo",
    "less_than_equal": "es demasiado grande",
    "union_tag_invalid": "tipo desconocido",
    "union_tag_not_found": "falta el campo 'tipo'",
}


def _traducir_json(mensaje: str) -> str:
    return _TRADUCCIONES_JSON.get(mensaje, mensaje)


def _describir(error: Any, datos: dict[str, Any]) -> str:
    """Convierte un error de Pydantic en 'acciones[2] (nombre).campo: explicación'."""
    loc = list(error["loc"])
    partes: list[str] = []
    i = 0
    while i < len(loc):
        clave = loc[i]
        if clave == "acciones" and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            indice = loc[i + 1]
            etiqueta = f"acciones[{indice}]"
            try:
                nombre = datos["acciones"][indice].get("nombre")
            except (KeyError, IndexError, TypeError, AttributeError):
                nombre = None
            if isinstance(nombre, str) and nombre:
                etiqueta += f" ({nombre})"
            partes.append(etiqueta)
            i += 2
            if i < len(loc) and loc[i] in TIPOS_ACCION:  # Pydantic añade el 'tipo' a la ruta
                i += 1
            continue
        if isinstance(clave, int):
            partes[-1:] = [f"{partes[-1]}[{clave}]"] if partes else [f"[{clave}]"]
        else:
            partes.append(str(clave))
        i += 1

    ruta = ".".join(partes) or "general"
    tipo = error["type"]
    if tipo == "union_tag_invalid":
        explicacion = f"tipo desconocido; válidos: {', '.join(TIPOS_ACCION)}"
    elif tipo == "literal_error" and partes == ["version"]:
        explicacion = f"debe ser {VERSION_ESQUEMA}"
    elif tipo == "literal_error":
        esperado = error.get("ctx", {}).get("expected", "")
        explicacion = f"valor no permitido; válidos: {esperado}"
    elif tipo == "value_error":
        explicacion = str(error.get("ctx", {}).get("error", error["msg"]))
    else:
        explicacion = _TRADUCCIONES_PYDANTIC.get(tipo, error["msg"])
    return f"{ruta}: {explicacion}"
