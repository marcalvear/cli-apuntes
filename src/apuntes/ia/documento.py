"""Un fichero preparado para enviarlo a la IA."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from apuntes.errores import DocumentoNoSoportado

MAX_PDF_BYTES = 32 * 1024 * 1024  # límite de la API por petición
MAX_TEXTO_CARACTERES = 500_000  # ~125k tokens: de sobra para unos apuntes
EXTENSIONES_TEXTO = frozenset({".txt", ".md"})
EXTENSIONES_SOPORTADAS = frozenset({".pdf"}) | EXTENSIONES_TEXTO


@dataclass(frozen=True)
class Documento:
    nombre: str
    #: "pdf" (se envía tal cual, la IA ve texto e imágenes) o "texto".
    formato: str
    contenido: bytes

    @property
    def huella(self) -> str:
        """SHA-256 del contenido: identifica el documento aunque cambie de nombre."""
        return hashlib.sha256(self.contenido).hexdigest()

    @property
    def texto(self) -> str:
        assert self.formato == "texto", "solo los documentos de texto tienen .texto"
        return self.contenido.decode("utf-8")

    @staticmethod
    def soportado(ruta: Path) -> bool:
        return ruta.suffix.lower() in EXTENSIONES_SOPORTADAS

    @staticmethod
    def desde_fichero(ruta: Path, *, nombre: str | None = None) -> Documento:
        """Fábrica: lee y valida el fichero. Lanza DocumentoNoSoportado con el motivo."""
        extension = ruta.suffix.lower()
        nombre = nombre or ruta.name
        if extension not in EXTENSIONES_SOPORTADAS:
            tipo = extension or "sin extensión"
            raise DocumentoNoSoportado(f"«{nombre}»: la IA solo lee PDF, .txt y .md (es {tipo}).")
        try:
            contenido = ruta.read_bytes()
        except OSError as error:
            raise DocumentoNoSoportado(f"No puedo leer «{nombre}»: {error.strerror}.") from error

        if extension == ".pdf":
            if not contenido.startswith(b"%PDF"):
                raise DocumentoNoSoportado(f"«{nombre}» no es un PDF válido.")
            if len(contenido) > MAX_PDF_BYTES:
                raise DocumentoNoSoportado(f"«{nombre}» pesa más de 32 MB, el máximo de la API.")
            return Documento(nombre, "pdf", contenido)

        try:
            texto = contenido.decode("utf-8")
        except UnicodeDecodeError:
            raise DocumentoNoSoportado(f"«{nombre}» no es texto UTF-8.") from None
        if len(texto) > MAX_TEXTO_CARACTERES:
            raise DocumentoNoSoportado(
                f"«{nombre}» es demasiado largo para enviarlo entero ({len(texto)} caracteres)."
            )
        if not texto.strip():
            raise DocumentoNoSoportado(f"«{nombre}» está vacío.")
        return Documento(nombre, "texto", contenido)
