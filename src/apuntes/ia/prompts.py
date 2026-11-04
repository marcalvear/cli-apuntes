"""Instrucciones para la IA, compartidas por todos los proveedores.

Así Claude y Gemini reciben exactamente las mismas peticiones y sus
resultados son comparables.
"""

from __future__ import annotations

from typing import Any

from apuntes.config import Asignatura

NINGUNA = "ninguna"

SISTEMA = (
    "Eres un asistente de estudio para un alumno de 1.º de DAM (Desarrollo de Aplicaciones "
    "Multiplataforma) en España. Trabajas con sus apuntes, diapositivas y ejercicios. "
    "Responde siempre en español de España, con rigor técnico y sin inventar contenido "
    "que no esté en el documento."
)

PROMPT_RESUMEN = """\
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


def esquema_clasificacion(asignaturas: list[Asignatura]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "asignatura": {"type": "string", "enum": [a.nombre for a in asignaturas] + [NINGUNA]},
            "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
            "motivo": {"type": "string", "description": "Una frase que justifique la elección."},
        },
        "required": ["asignatura", "confianza", "motivo"],
        "additionalProperties": False,
    }


def prompt_clasificacion(asignaturas: list[Asignatura]) -> str:
    lineas = [
        "¿A qué asignatura pertenece este documento de clase? Asignaturas posibles:",
        "",
    ]
    for asignatura in asignaturas:
        pistas = ", ".join(asignatura.palabras_clave)
        lineas.append(f"- {asignatura.nombre}" + (f" (temas: {pistas})" if pistas else ""))
    lineas += [
        "",
        f"Si no encaja claramente en ninguna, responde «{NINGUNA}». "
        "Usa confianza «baja» si dudas entre dos.",
    ]
    return "\n".join(lineas)


def prompt_preguntas(numero: int) -> str:
    return _PROMPT_PREGUNTAS.format(numero=numero)
