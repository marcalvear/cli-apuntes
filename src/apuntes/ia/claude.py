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
from apuntes.ia.proveedor import Clasificacion, ProveedorIA

MODELO_POR_DEFECTO = "claude-opus-5-5"
_BETA_FALLBACK = "server-side-fallback-2026-07-01"
_HOST_API = "api.anthropic.com"
_NINGUNA = "ninguna"

_SISTEMA = (
    "Eres un asistente de estudio para un alumno de 1.º de DAM (Desarrollo de Aplicaciones "
    "Multiplataforma) en España. Trabajas con sus apuntes, diapositivas y ejercicios. "
    "Responde siempre en español de España, con rigor técnico y sin inventar contenido "
    "que no esté en el documento."
)

_PROMPT_RESUMEN = """\
Resume este documento de clase para estudiar. Formato Markdown:

# <título del tema>

**En una frase:** <de qué trata>

## Conceptos clave
Lista con cada concepto en negrita y una explicación breve y precisa.

## Ideas importantes
Lo que más probablemente caiga en el examen, en viñetas.

## Ejemplo
Un ejemplo breve sacado del documento (código en bloque ``` con su lenguaje si lo hay).

Extensión: lo justo para repasar el tema en 5 minutos. Responde solo con el Markdown."""

_PROMPT_PREGUNTAS = """\
Crea {numero} preguntas tipo test para repasar este documento de clase.

Reglas:
- 4 opciones (a, b, c, d) y una sola correcta; distractores plausibles, no absurdos.
- Mezcla preguntas de concepto, de aplicar (qué hace este código, qué se usaría...) y de detalle.
- Todo debe poder responderse con el documento.

Formato Markdown:

# Preguntas de repaso: <título del tema>

**1.** <enunciado>
- a) ...
- b) ...
- c) ...
- d) ...

(... el resto de preguntas ...)

---

## Soluciones
**1. <letra>)** <por qué es la correcta, en una línea>

Responde solo con el Markdown."""


def _esquema_clasificacion(asignaturas: list[Asignatura]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "asignatura": {"type": "string", "enum": [a.nombre for a in asignaturas] + [_NINGUNA]},
            "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
            "motivo": {"type": "string", "description": "Una frase que justifique la elección."},
        },
        "required": ["asignatura", "confianza", "motivo"],
        "additionalProperties": False,
    }


def _prompt_clasificacion(asignaturas: list[Asignatura]) -> str:
    lineas = [
        "¿A qué asignatura pertenece este documento de clase? Asignaturas posibles:",
        "",
    ]
    for asignatura in asignaturas:
        pistas = ", ".join(asignatura.palabras_clave)
        lineas.append(f"- {asignatura.nombre}" + (f" (temas: {pistas})" if pistas else ""))
    lineas += [
        "",
        f"Si no encaja claramente en ninguna, responde «{_NINGUNA}». "
        "Usa confianza «baja» si dudas entre dos.",
    ]
    return "\n".join(lineas)


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
            _prompt_clasificacion(asignaturas),
            esfuerzo="low",
            max_tokens=4000,
            formato={"type": "json_schema", "schema": _esquema_clasificacion(asignaturas)},
        )
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as error:
            raise ErrorIA(
                f"La IA devolvió una clasificación ilegible para «{documento.nombre}»."
            ) from error
        asignatura = datos["asignatura"]
        return Clasificacion(
            asignatura=None if asignatura == _NINGUNA else asignatura,
            confianza=datos["confianza"],
            motivo=datos["motivo"],
        )

    def resumir(self, documento: Documento) -> str:
        return self._preguntar(documento, _PROMPT_RESUMEN, esfuerzo="medium", max_tokens=16000)

    def preguntas(self, documento: Documento, numero: int) -> str:
        prompt = _PROMPT_PREGUNTAS.format(numero=numero)
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
                system=_SISTEMA,
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
