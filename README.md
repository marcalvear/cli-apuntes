# cli-apuntes

[![tests](https://github.com/marcalvear/cli-apuntes/actions/workflows/tests.yml/badge.svg)](https://github.com/marcalvear/cli-apuntes/actions/workflows/tests.yml)

`apuntes` es una CLI que pone orden en el material de clase: PDFs, diapositivas y
ejercicios que se acumulan en Descargas. Las acciones (mover, renombrar,
deduplicar, resumir con IA…) no están escritas en el código: se describen en un
fichero `acciones.json` que el motor interpreta.

> **Estado:** en desarrollo (v0.1.0). Por ahora están disponibles `version` y `listar`.

## Instalación

Necesitas [uv](https://docs.astral.sh/uv/getting-started/installation/). Con una
sola orden queda instalado el comando `apuntes`, disponible en cualquier carpeta:

```bash
uv tool install git+https://github.com/marcalvear/cli-apuntes
```

Si prefieres pipx:

```bash
pipx install git+https://github.com/marcalvear/cli-apuntes
```

Para actualizar: `uv tool upgrade apuntes`. Para desinstalar: `uv tool uninstall apuntes`.

## Uso

```bash
apuntes --help              # todas las órdenes
apuntes version             # versión instalada
apuntes listar              # tabla de la carpeta actual
apuntes listar ~/Descargas --orden tamano   # los más grandes primero
apuntes listar . --todos    # incluye ficheros ocultos
```

### Códigos de salida

| Código | Significado |
|---|---|
| 0 | Todo bien |
| 1 | Fallo al ejecutar (por ejemplo, la carpeta no existe) |
| 2 | Error de uso: opción o argumento incorrecto |
| 3 | `acciones.json` inválido |

## Desarrollo

```bash
git clone https://github.com/marcalvear/cli-apuntes && cd cli-apuntes
uv sync                      # crea .venv con dependencias
uv run apuntes --help        # ejecuta la versión del código
uv run pytest                # tests
uv run ruff check . && uv run ruff format --check .
```

Los tests usan carpetas temporales y nunca tocan ficheros reales. GitHub Actions
los ejecuta en Linux, macOS y Windows en cada push y pull request.
