# Changelog

Todos los cambios relevantes de `apuntes` se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto
usa [versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido

- `copiar-a-icloud`: añade una copia de los documentos en PDF de los apuntes de clase al almacenamiento en la nube de iCloud. Los PDFs se ordenan por asignaturas en la carpeta iCloud. También evita copiar un mismo archivo dos veces saltándose la copia del fichero repetido.

### Corregido

- Las dependencias tienen ahora un límite superior de versión. Una instalación nueva con
  `uv tool install` descargaba `google-genai` 3.0, una versión mayor que no se había probado
  y que muestra avisos `SyntaxWarning` la primera vez que se usa la IA.
- README: instrucciones para crear `~/.config/apuntes/.env` sin tener clonado el repositorio,
  y recuentos de pasos, tests y pull requests corregidos.

## [1.0.0] - 2026-11-04

Primera versión estable.

### Órdenes

- `apuntes listar [CARPETA]`: tabla con nombre, tipo, tamaño y fecha. Admite `--todos` y `--orden`.
- `apuntes init`: crea un `acciones.json` de ejemplo con 10 acciones y las asignaturas de 1.º de
  DAM. Nunca sobrescribe un fichero existente sin `--forzar`, y entonces guarda una copia `.bak`.
- `apuntes acciones`: lista las acciones, marca las que piden confirmación y las que usan IA, y
  avisa si falta la clave.
- `apuntes validar`: comprueba `acciones.json` y dice exactamente qué campo falla.
- `apuntes ejecutar NOMBRE [CARPETA]`: muestra siempre el plan antes de actuar.
  - `--simular` (`-n`) solo enseña el plan, sin tocar nada.
  - Si el plan es destructivo, pide confirmación, y por defecto la respuesta es «no».
  - `--si` (`-y`) aplica sin preguntar, para scripts.
- `apuntes historial` y `apuntes deshacer [N]`: deshacen una ejecución devolviendo cada fichero a
  su sitio, sin pisar nada.
- `apuntes estado`: comprueba de un vistazo el fichero de acciones, el `.env`, la clave de IA, la
  conexión y la caché.
- `apuntes version` y la opción global `--config RUTA`.

### Acciones configurables en `acciones.json`

- 10 tipos de acción:
  - sin IA: `mover`, `copiar`, `renombrar` (con plantilla), `borrar` (a la papelera),
    `deduplicar` (por SHA-256), `archivar` (zip verificado) e `indice` (Markdown);
  - con IA: `ia-clasificar`, `ia-resumir` e `ia-preguntas`;
  - `pipeline`, que encadena varias acciones.
- Filtros por extensión, expresión regular, antigüedad y recursividad.
- `{asignatura}` se deduce por palabras clave del nombre del fichero. Si duda, no mueve el fichero.
- El esquema se valida entero antes de ejecutar, con Pydantic. Los errores indican la ruta exacta
  del campo, por ejemplo `acciones[2] (limpiar).filtro.extensiones`, y la orden sale con el
  código 3.
- El fichero se busca en `--config`, `$APUNTES_CONFIG`, `./acciones.json` y
  `~/.config/apuntes/acciones.json`, por ese orden.

### Seguridad

- Ninguna acción toca el disco al planificar. `--simular` muestra exactamente lo que se aplicará.
- Borrar es siempre enviar a la Papelera del sistema; nunca se borra de forma definitiva.
- Las escrituras son atómicas: se escribe en un temporal y luego se renombra. Si algo falla a
  medias, ningún fichero queda a medias.
- Antes de cada operación se comprueba que el disco no ha cambiado desde que se planificó.
- Las claves de IA van en `.env`, que está en `.gitignore` desde el primer commit.

### IA

- Dos proveedores intercambiables con la misma interfaz: **Gemini**, el de por defecto, con capa
  gratuita, y **Claude**, de pago. Se elige con `APUNTES_PROVEEDOR`.
- Los PDF se envían tal cual, y la clasificación usa salida estructurada con la lista cerrada de
  asignaturas.
- Si un modelo gratuito de Gemini está saturado, se pasa automáticamente al siguiente.
- Caché por contenido: no se paga dos veces por el mismo PDF, y `--simular` es gratis para
  resumir y para generar preguntas.
- Sin clave o sin red, la CLI lo explica y sigue funcionando: en un pipeline, los pasos con IA
  se omiten.

### Calidad

- 180 tests con pytest y un 92 % de cobertura, sin red, sin IA real y sin tocar ficheros reales.
- GitHub Actions ejecuta `ruff` y `pytest` en Linux, macOS y Windows, con Python 3.12 y 3.13.
- Decisiones de diseño documentadas en 4 ADR (`docs/adr/`) y guía de los tests en
  [`docs/tests.md`](docs/tests.md).

[1.0.0]: https://github.com/marcalvear/cli-apuntes/releases/tag/v1.0.0
