"""Proveedor de IA con la API de Claude (Anthropic).

- Los PDF se envían tal cual: Claude lee el texto y también tablas,
  diagramas y fórmulas de las diapositivas.
- La clasificación usa salida estructurada (JSON Schema), así que la
  respuesta siempre es una asignatura de la lista o "ninguna".
- `fallbacks: "default"`: si los filtros de seguridad del modelo rechazan
  un documento (un falso positivo con apuntes de seguridad informática, por
  ejemplo), la API reintenta con el modelo alternativo recomendado.
- Los errores del SDK se traducen a errores propios con mensajes humanos.
"""

from __future__ import annotations

import base64
import json
import os
import socket
from typing import Any
from urllib.parse import urlparse

import anthropic

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

MODELO_POR_DEFECTO = "claude-opus-5-5"
_BETA_FALLBACK = "server-side-fallback-2026-07-01"
_HOST_API = "api.anthropic.com"


class ProveedorClaude(ProveedorIA):
    def __init__(self, *, modelo: str = MODELO_POR_DEFECTO, cliente: Any | None = None) -> None:
        self.modelo = modelo
        self._cliente = cliente  # inyectable en tests; si no, se crea al usarlo

    # -- Disponibilidad --

    def comprobar(self) -> None:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise IANoDisponible(
                "La IA no está configurada: falta la clave ANTHROPIC_API_KEY.",
                pista="Copia .env.example a .env y pon tu clave (ver README, sección IA). "
                "Las acciones sin IA funcionan igual.",
            )
        if not _hay_red():
            raise IANoDisponible(
                "No hay conexión con la API de Claude (¿sin internet?).",
                pista="Las acciones sin IA funcionan igual. Vuelve a intentarlo con conexión.",
            )

    # -- Tareas --

    def clasificar(self, documento: Documento, asignaturas: list[Asignatura]) -> Clasificacion:
        assert asignaturas, "la configuración garantiza que hay asignaturas"
        texto = self._preguntar(
            documento,
            prompt_clasificacion(asignaturas),
            esfuerzo="low",
            max_tokens=4000,
            formato={"type": "json_schema", "schema": esquema_clasificacion(asignaturas)},
        )
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as error:
            raise ErrorIA(
                f"La IA devolvió una clasificación ilegible para «{documento.nombre}»."
            ) from error
        asignatura = datos["asignatura"]
        return Clasificacion(
            asignatura=None if asignatura == NINGUNA else asignatura,
            confianza=datos["confianza"],
            motivo=datos["motivo"],
        )

    def resumir(self, documento: Documento) -> str:
        return self._preguntar(documento, PROMPT_RESUMEN, esfuerzo="medium", max_tokens=16000)

    def preguntas(self, documento: Documento, numero: int) -> str:
        prompt = prompt_preguntas(numero)
        return self._preguntar(documento, prompt, esfuerzo="medium", max_tokens=16000)

    # -- Llamada a la API --

    def _cliente_api(self) -> Any:
        if self._cliente is None:
            self._cliente = anthropic.Anthropic(max_retries=3, timeout=300.0)
        return self._cliente

    def _preguntar(
        self,
        documento: Documento,
        instrucciones: str,
        *,
        esfuerzo: str,
        max_tokens: int,
        formato: dict[str, Any] | None = None,
    ) -> str:
        output_config: dict[str, Any] = {"effort": esfuerzo}
        if formato is not None:
            output_config["format"] = formato
        try:
            respuesta = self._cliente_api().beta.messages.create(
                model=self.modelo,
                max_tokens=max_tokens,
                system=SISTEMA,
                betas=[_BETA_FALLBACK],
                fallbacks="default",
                output_config=output_config,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            _bloque_documento(documento),
                            {"type": "text", "text": instrucciones},
                        ],
                    }
                ],
            )
        except anthropic.AuthenticationError:
            raise IANoDisponible(
                "La clave de la API de Claude no es válida.",
                pista="Revisa ANTHROPIC_API_KEY en tu .env (console.anthropic.com → API keys).",
            ) from None
        except anthropic.PermissionDeniedError:
            raise IANoDisponible(
                "Tu clave no tiene permiso para usar este modelo.",
                pista=f"Prueba otro modelo con APUNTES_MODELO (ahora: {self.modelo}).",
            ) from None
        except anthropic.RateLimitError:
            raise ErrorIA(
                "Has superado el límite de uso de la API de Claude.",
                pista="Espera un minuto y vuelve a lanzar la acción: lo ya hecho está en caché.",
            ) from None
        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            raise IANoDisponible(
                "Se ha perdido la conexión con la API de Claude.",
                pista="Comprueba tu conexión. Las acciones sin IA funcionan igual.",
            ) from None
        except anthropic.BadRequestError as error:
            raise ErrorIA(
                f"La API de Claude no ha aceptado «{documento.nombre}»: {error.message}"
            ) from None
        except anthropic.APIStatusError as error:
            raise ErrorIA(
                f"La API de Claude ha fallado (código {error.status_code}).",
                pista="Suele ser temporal: vuelve a intentarlo en unos minutos.",
            ) from None

        if respuesta.stop_reason == "refusal":
            raise ErrorIA(f"La IA se ha negado a procesar «{documento.nombre}».")
        if respuesta.stop_reason == "max_tokens":
            raise ErrorIA(f"La respuesta de la IA para «{documento.nombre}» ha quedado cortada.")
        texto = "".join(b.text for b in respuesta.content if b.type == "text").strip()
        if not texto:
            raise ErrorIA(f"La IA no ha devuelto texto para «{documento.nombre}».")
        return texto


def _bloque_documento(documento: Documento) -> dict[str, Any]:
    if documento.formato == "pdf":
        datos = base64.standard_b64encode(documento.contenido).decode("ascii")
        fuente = {"type": "base64", "media_type": "application/pdf", "data": datos}
    else:
        fuente = {"type": "text", "media_type": "text/plain", "data": documento.texto}
    return {"type": "document", "source": fuente, "title": documento.nombre}


def _hay_red(timeout: float = 3.0) -> bool:
    """¿Se puede abrir una conexión con la API? Con proxy no se comprueba (no sabríamos cómo)."""
    if any(os.environ.get(v) for v in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")):
        return True
    host = urlparse(os.environ.get("ANTHROPIC_BASE_URL", "")).hostname or _HOST_API
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True
    except OSError:
        return False
