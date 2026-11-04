# cli-apuntes

[![tests](https://github.com/marcalvear/cli-apuntes/actions/workflows/tests.yml/badge.svg)](https://github.com/marcalvear/cli-apuntes/actions/workflows/tests.yml)

`apuntes` es una CLI que pone orden en el material de clase: PDFs, diapositivas y
ejercicios que se acumulan en Descargas. Las acciones (mover, renombrar,
deduplicar, resumir con IA…) no están escritas en el código: se describen en un
fichero `acciones.json` que el motor interpreta.

> **Estado:** en desarrollo (v0.1.0). Ya funcionan `version`, `listar`, `init`, `acciones` y
> `validar`. `ejecutar` llega en la siguiente versión.

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

apuntes init                # crea un acciones.json de ejemplo en la carpeta actual
apuntes acciones            # lista las acciones definidas
apuntes validar             # comprueba acciones.json (código 3 si es inválido)
apuntes -c ~/otro.json acciones   # usa otro fichero de acciones
```

### Qué fichero de acciones se usa

Se usa el primero que exista de esta lista:

1. El indicado con `--config RUTA` (o `-c`).
2. El de la variable de entorno `APUNTES_CONFIG`.
3. `./acciones.json`, en la carpeta actual.
4. `~/.config/apuntes/acciones.json`, la configuración personal.

### Códigos de salida

| Código | Significado |
|---|---|
| 0 | Todo bien |
| 1 | Fallo al ejecutar (por ejemplo, la carpeta no existe) |
| 2 | Error de uso: opción o argumento incorrecto |
| 3 | `acciones.json` inválido |

## El fichero `acciones.json`

Las acciones no están en el código: se describen aquí y el motor las
interpreta. Para añadir una, basta con escribirla en el fichero y
comprobarla con `apuntes validar`. El porqué de este diseño está en
[ADR 0001](docs/adr/0001-configuracion-externa.md).

```json
{
  "version": 1,
  "asignaturas": [
    { "nombre": "Programacion", "palabras_clave": ["prog", "java", "poo"] }
  ],
  "acciones": [
    {
      "nombre": "ordenar-por-asignatura",
      "descripcion": "Mueve PDFs y diapositivas a la carpeta de su asignatura",
      "tipo": "mover",
      "filtro": { "extensiones": [".pdf", ".pptx"] },
      "destino": "Apuntes/{asignatura}"
    },
    {
      "nombre": "limpiar-temporales",
      "descripcion": "Envía a la papelera temporales de más de 7 días",
      "tipo": "borrar",
      "filtro": { "patron": "\\.tmp$", "mas_antiguo_que_dias": 7 }
    }
  ]
}
```

El ejemplo completo, con 10 acciones, es [`acciones.json`](acciones.json)
y es el mismo que crea `apuntes init`.

### Raíz del fichero

| Campo | Obligatorio | Descripción |
|---|---|---|
| `version` | sí | Versión del esquema. Ahora mismo, `1`. |
| `asignaturas` | no* | Lista de `{ "nombre", "palabras_clave" }`. *Obligatoria si alguna acción usa `{asignatura}` o es `ia-clasificar`. |
| `acciones` | sí | Lista de acciones (al menos una). |

### Campos comunes a todas las acciones

| Campo | Obligatorio | Descripción |
|---|---|---|
| `nombre` | sí | Identificador para `apuntes ejecutar NOMBRE`. Minúsculas, números y guiones, sin repetir. |
| `descripcion` | sí | Frase que se ve en `apuntes acciones`. |
| `tipo` | sí | Uno de los tipos de la tabla siguiente. |
| `origen` | no | Carpeta de trabajo. Si falta, se usa la CARPETA de la orden. Admite `~`. |
| `filtro` | no | Qué ficheros afectan a la acción (ver más abajo). Sin filtro, todos. |
| `confirmar` | no | `true` o `false`. Preguntar antes de actuar. Por defecto es `true` en las acciones destructivas. |

### Filtro

Todas las condiciones que se indiquen deben cumplirse a la vez.

| Campo | Ejemplo | Descripción |
|---|---|---|
| `extensiones` | `[".pdf", "pptx"]` | Sin distinguir mayúsculas; el punto es opcional. |
| `patron` | `"^Tema\\d+"` | [Expresión regular](https://docs.python.org/3/library/re.html) que debe aparecer en el nombre. |
| `mas_antiguo_que_dias` | `30` | Modificado hace más de N días. |
| `mas_reciente_que_dias` | `7` | Modificado hace menos de N días. |
| `recursivo` | `true` | Incluye subcarpetas (por defecto `false`). |

### Tipos de acción

| Tipo | Campos propios | Qué hace |
|---|---|---|
| `mover` | `destino`, `si_existe` | Mueve los ficheros a `destino`. |
| `copiar` | `destino`, `si_existe` | Igual que `mover`, pero conserva el original. |
| `renombrar` | `plantilla` | Cambia el nombre según la plantilla. |
| `borrar` | — | Envía a la **papelera** (nunca borra de forma definitiva). Confirma por defecto. |
| `deduplicar` | `conservar` | Detecta ficheros con el mismo contenido y envía las copias a la papelera. Confirma por defecto. |
| `archivar` | `destino` (.zip), `borrar_originales` | Comprime los ficheros en un zip. Si borra los originales, confirma. |
| `indice` | `fichero`, `titulo` | Genera un índice Markdown (por defecto `INDICE.md`) del material. |
| `ia-clasificar` | `destino` | 🤖 La IA lee el contenido, decide la asignatura y mueve el fichero. |
| `ia-resumir` | `destino` | 🤖 Crea un resumen `.md` de cada documento. |
| `ia-preguntas` | `destino`, `numero` | 🤖 Crea preguntas tipo test con solución (1 a 50; por defecto 10). |
| `pipeline` | `pasos` | Ejecuta en orden otras acciones, indicadas por su nombre. |

Más detalles:

- **`destino`** es relativo a la carpeta de trabajo, salvo que empiece por `/` o `~`.
  Admite `{asignatura}`, `{tipo}` (pdf, presentación…) y `{fecha:%Y-%m}`.
- **`si_existe`** decide qué hacer si en el destino ya hay un fichero con ese
  nombre: `renombrar` (por defecto, añade ` (2)`), `saltar` o `sobrescribir`.
- **`plantilla`** admite estos marcadores:
  - `{fecha:%Y-%m-%d}`: fecha de modificación, con
    [formato strftime](https://docs.python.org/3/library/datetime.html#format-codes).
  - `{n:03}`: contador de 3 cifras.
  - `{nombre}`: nombre original sin extensión.
  - `{ext}`: extensión original, con el punto.
  - `{asignatura}`.
- **`{asignatura}`** se deduce buscando las `palabras_clave` de cada asignatura
  en el nombre del fichero. Si ninguna encaja, el fichero no se toca. Para esos
  casos está `ia-clasificar`.

### Si el fichero tiene errores

`apuntes validar` muestra **todos** los problemas a la vez, con la ruta exacta
del campo, y sale con el código 3:

```text
Error: «acciones.json» tiene 2 problema(s):
  • acciones[0] (mover-pdf).destino: falta este campo obligatorio
  • acciones[0] (mover-pdf).destnio: campo desconocido (¿una errata?)
Pista: Comprueba el esquema en el README o ejecuta: apuntes validar
```

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

Las decisiones de diseño están documentadas en [`docs/adr/`](docs/adr/).
