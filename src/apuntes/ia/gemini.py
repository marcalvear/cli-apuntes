"""Proveedor de IA con la API de Gemini (Google), usable gratis con una clave de AI Studio.

- Los PDF se envían tal cual (Gemini lee texto, tablas y diagramas).
- La clasificación usa salida JSON con esquema: la asignatura solo puede
  ser una de la lista o "ninguna".
- Los modelos gratuitos a veces están saturados (503) o se agota su cuota
  (429). Se prueba una lista de modelos en orden: si uno está saturado, se
  pasa al siguiente en vez de fallar.
- Los errores del SDK se traducen a errores propios con mensajes humanos.
"""

from __future__ import annotations

import importlib
import json
import os
import socket
from typing import Any

from google import genai
from google.genai import errors, types

from apuntes.config import Asignatura
from apuntes.errores import ErrorIA, IANoDisponible
from apuntes.ia.documento import Documento
from apuntes.ia.prompts import (
    NINGUNA,
    PROMPT_RESUMEN,
    SISTEMA,
    esquema_clasificacion,
    prompt_clasificacion,
    prompt_preguntas,
)
from apuntes.ia.proveedor import Clasificacion, ProveedorIA

#: De mejor a más ligero; todos tienen capa gratuita (nov. 2026).
MODELOS_POR_DEFECTO = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite")
_HOST_API = "generativelanguage.googleapis.com"
_TIEMPO_MAXIMO_MS = 120_000
#: Finales de respuesta que indican que la IA se ha negado a contestar.
_BLOQUEOS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def _errores_de_red() -> tuple[type[BaseException], ...]:
    """Errores de conexión del cliente HTTP que use el SDK (httpx o httpx2)."""
    clases: list[type[BaseException]] = [ConnectionError, TimeoutError]
    for modulo in ("httpx", "httpx2"):
        try:
            clases.append(importlib.import_module(modulo).TransportError)
        except (ImportError, AttributeError):
            continue
    return tuple(clases)


_ERRORES_RED = _errores_de_red()


def clave_gemini() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


class ProveedorGemini(ProveedorIA):
    def __init__(
        self, *, modelos: tuple[str, ...] = MODELOS_POR_DEFECTO, cliente: Any | None = None
    ) -> None:
        assert modelos, "hace falta al menos un modelo"
        self._modelos = modelos
        self.modelo = modelos[0]  # el preferido identifica las respuestas en la caché
        self._cliente = cliente  # inyectable en tests; si no, se crea al usarlo

    # -- Disponibilidad --

    def comprobar(self) -> None:
        if not clave_gemini():
            raise IANoDisponible(
                "La IA no está configurada: falta la clave GEMINI_API_KEY.",
                pista="Crea una gratis en aistudio.google.com y ponla en ~/.config/apuntes/.env "
                "(ver README, sección IA). Las acciones sin IA funcionan igual.",
            )
        if not _hay_red():
            raise IANoDisponible(
                "No hay conexión con la API de Gemini (¿sin internet?).",
                pista="Las acciones sin IA funcionan igual. Vuelve a intentarlo con conexión.",
            )

    # -- Tareas --

    def clasificar(self, documento: Documento, asignaturas: list[Asignatura]) -> Clasificacion:
        assert asignaturas, "la configuración garantiza que hay asignaturas"
        texto = self._preguntar(
            documento,
            prompt_clasificacion(asignaturas),
            max_tokens=4000,
            esquema=esquema_clasificacion(asignaturas),
        )
        try:
            datos = json.loads(texto)
            asignatura, confianza, motivo = datos["asignatura"], datos["confianza"], datos["motivo"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise ErrorIA(
                f"La IA devolvió una clasificación ilegible para «{documento.nombre}»."
            ) from error
        if confianza not in ("alta", "media", "baja"):
            confianza = "baja"
        return Clasificacion(
            asignatura=None if asignatura == NINGUNA else asignatura,
            confianza=confianza,
            motivo=str(motivo),
        )

    def resumir(self, documento: Documento) -> str:
        return self._preguntar(documento, PROMPT_RESUMEN, max_tokens=16000)

    def preguntas(self, documento: Documento, numero: int) -> str:
        return self._preguntar(documento, prompt_preguntas(numero), max_tokens=16000)

    # -- Llamada a la API --

    def _cliente_api(self) -> Any:
        if self._cliente is None:
            opciones = types.HttpOptions(
                timeout=_TIEMPO_MAXIMO_MS,
                # Pocos reintentos: si un modelo está saturado, mejor pasar al siguiente.
                retry_options=types.HttpRetryOptions(attempts=2),
            )
            self._cliente = genai.Client(api_key=clave_gemini(), http_options=opciones)
        return self._cliente

    def _preguntar(
        self,
        documento: Documento,
        instrucciones: str,
        *,
        max_tokens: int,
        esquema: dict[str, Any] | None = None,
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=SISTEMA,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if esquema else None,
            response_json_schema=esquema,
        )
        contenido = [_parte_documento(documento), instrucciones]
        saturados: list[str] = []
        for modelo in self._modelos:
            try:
                respuesta = self._cliente_api().models.generate_content(
                    model=modelo, contents=contenido, config=config
                )
            except errors.ClientError as error:
                if error.code == 429:  # cuota gratuita agotada en este modelo: probamos otro
                    saturados.append(f"{modelo} (sin cuota)")
                    continue
                if error.code == 404:  # modelo retirado: probamos el siguiente
                    saturados.append(f"{modelo} (no existe)")
                    continue
                raise _traducir_error_cliente(error, documento) from None
            except errors.ServerError:
                saturados.append(f"{modelo} (saturado)")
                continue
            except _ERRORES_RED:
                raise IANoDisponible(
                    "Se ha perdido la conexión con la API de Gemini.",
                    pista="Comprueba tu conexión. Las acciones sin IA funcionan igual.",
                ) from None
            return _texto_de(respuesta, documento)

        raise ErrorIA(
            "Ningún modelo de Gemini ha podido responder ahora mismo: "
            + ", ".join(saturados)
            + ".",
            pista="La capa gratuita tiene límites por minuto y por día: espera un poco y vuelve "
            "a lanzar la acción (lo ya hecho está en caché).",
        )


def _traducir_error_cliente(error: errors.ClientError, documento: Documento) -> ErrorIA:
    texto = str(error).lower()
    if error.code in (401, 403) or "api key" in texto or "api_key" in texto:
        return IANoDisponible(
            "La clave de Gemini no es válida o no tiene permiso.",
            pista="Revisa GEMINI_API_KEY en ~/.config/apuntes/.env "
            "(aistudio.google.com → API keys).",
        )
    return ErrorIA(
        f"La API de Gemini no ha aceptado «{documento.nombre}» (código {error.code}).",
        pista="Si el PDF es muy grande o está dañado, prueba con otro.",
    )


def _texto_de(respuesta: Any, documento: Documento) -> str:
    candidatos = getattr(respuesta, "candidates", None) or []
    final = getattr(candidatos[0], "finish_reason", None) if candidatos else None
    nombre_final = getattr(final, "name", str(final or ""))
    if nombre_final in _BLOQUEOS or not candidatos:
        raise ErrorIA(f"La IA se ha negado a procesar «{documento.nombre}».")
    if nombre_final == "MAX_TOKENS":
        raise ErrorIA(f"La respuesta de la IA para «{documento.nombre}» ha quedado cortada.")
    texto = (respuesta.text or "").strip()
    if not texto:
        raise ErrorIA(f"La IA no ha devuelto texto para «{documento.nombre}».")
    return texto


def _parte_documento(documento: Documento) -> Any:
    if documento.formato == "pdf":
        return types.Part.from_bytes(data=documento.contenido, mime_type="application/pdf")
    return types.Part.from_text(text=f"Documento «{documento.nombre}»:\n\n{documento.texto}")


def _hay_red(timeout: float = 3.0) -> bool:
    """¿Se puede abrir una conexión con la API? Con proxy no se comprueba."""
    if any(os.environ.get(v) for v in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")):
        return True
    try:
        with socket.create_connection((_HOST_API, 443), timeout=timeout):
            return True
    except OSError:
        return False
