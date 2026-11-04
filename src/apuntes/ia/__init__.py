"""Capa de IA: un proveedor intercambiable detrás de una interfaz común.

- `proveedor.py`: la interfaz `ProveedorIA` y los tipos de resultado.
- `claude.py`: la implementación con la API de Claude (Anthropic).
- `cache.py`: un decorador que guarda respuestas para no pagar dos veces.
- `documento.py`: convierte un fichero en algo que la IA puede leer.
- `entorno.py`: lee .env y construye el proveedor configurado.

El resto del programa solo conoce `ProveedorIA`; cambiar de proveedor no
toca las acciones.
"""
