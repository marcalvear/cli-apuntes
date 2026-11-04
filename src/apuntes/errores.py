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
