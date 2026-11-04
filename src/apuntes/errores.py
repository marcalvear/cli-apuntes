"""Excepciones propias de apuntes.

Cada error previsible tiene su clase y su código de salida. La interfaz
(cli.py) las captura y muestra el mensaje sin traceback; cualquier otra
excepción es un fallo de programación y sí debe verse.
"""


class ApuntesError(Exception):
    """Error previsible: se muestra al usuario con un mensaje humano."""

    codigo_salida: int = 1

    def __init__(self, mensaje: str, *, pista: str | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.pista = pista


class CarpetaNoValida(ApuntesError):
    """La carpeta indicada no existe, no es una carpeta o no se puede leer."""


class ConfigError(ApuntesError):
    """acciones.json no existe, no es JSON válido o no cumple el esquema.

    `problemas` lista cada fallo con la ruta del campo, p. ej.
    "acciones[2] (limpiar).filtro.extensiones: debe ser una lista".
    """

    codigo_salida = 3

    def __init__(
        self, mensaje: str, *, problemas: list[str] | None = None, pista: str | None = None
    ) -> None:
        super().__init__(mensaje, pista=pista)
        self.problemas = problemas or []


class AccionNoValida(ApuntesError):
    """Se pidió ejecutar una acción que no existe en la configuración."""


class FicheroError(ApuntesError):
    """Una operación sobre el disco falló (permisos, disco lleno, fichero desaparecido...)."""


class ErrorIA(ApuntesError):
    """La IA respondió con un error o no pudo procesar un documento."""


class IANoDisponible(ErrorIA):
    """No se puede usar la IA: falta la clave, no hay red o la clave no es válida.

    Nunca impide usar las acciones sin IA.
    """


class DocumentoNoSoportado(ErrorIA):
    """El fichero no se puede enviar a la IA (tipo no soportado o demasiado grande)."""


class EjecucionInterrumpida(ApuntesError):
    """Una operación falló a mitad de un plan: las anteriores ya se aplicaron."""

    def __init__(self, mensaje: str, *, aplicadas: int, pista: str | None = None) -> None:
        super().__init__(mensaje, pista=pista)
        self.aplicadas = aplicadas
