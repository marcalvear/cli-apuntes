# cli-apuntes

[![tests](https://github.com/marcalvear/cli-apuntes/actions/workflows/tests.yml/badge.svg)](https://github.com/marcalvear/cli-apuntes/actions/workflows/tests.yml)

`apuntes` es una CLI que pone orden en el material de clase: PDFs, diapositivas y
ejercicios que se acumulan en Descargas. Las acciones (mover, renombrar,
deduplicar, resumir con IA…) no están escritas en el código: se describen en un
fichero `acciones.json` que el motor interpreta.

> **Versión 1.0.0.** Todas las órdenes y los 10 tipos de acción, 3 de ellos con IA
> (Gemini, gratis, o Claude). Cambios en el [CHANGELOG](CHANGELOG.md).
>
> 📋 **¿Evaluando el proyecto?** La sección [Evaluación según la rúbrica](#evaluación-según-la-rúbrica)
> enlaza cada criterio con su evidencia.

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
apuntes estado              # fichero de acciones, clave de IA, conexión y caché
apuntes -c ~/otro.json acciones   # usa otro fichero de acciones

apuntes ejecutar ordenar-todo ~/Descargas --simular   # enseña el plan sin tocar nada
apuntes ejecutar ordenar-todo ~/Descargas             # lo aplica (pide confirmación si borra)
apuntes ejecutar limpiar-temporales ~/Descargas --si  # sin preguntar, para scripts

apuntes historial           # últimas ejecuciones
apuntes deshacer --simular  # qué se desharía
apuntes deshacer            # deshace la última (o: apuntes deshacer N)
```

### Cómo trabaja `ejecutar`

1. **Planifica** todo lo que va a hacer sin tocar el disco. En un `pipeline`, cada paso
   ve los ficheros donde los dejará el anterior.
2. **Enseña el plan:** cada operación (mover, renombrar, a la papelera…) y los ficheros
   que deja sin tocar, con el motivo. Por ejemplo: «dudoso entre Bases de Datos y Programacion».
3. Con `--simular` (`-n`) **se para aquí**.
4. Si el plan es destructivo (envía algo a la papelera o reemplaza un fichero), **pregunta**.
   La respuesta por defecto es «no». `--si` (`-y`) no pregunta.
5. **Aplica** las operaciones en orden. Si una falla, por ejemplo porque alguien ha creado
   un fichero en el destino mientras tanto, se detiene e indica cuántas se hicieron. Ningún
   fichero queda a medias: se escribe en temporales y se colocan con un renombrado atómico.

Lo que se «borra» va siempre a la **Papelera** del sistema y se puede recuperar.

Ejemplo de `--simular`:

```text
Paso 3/4: ordenar-por-asignatura (mover) en /Users/marc/pruebas-tareas
#  Operación  Fichero                        Destino / detalle
1  mover      BBDD - Normalizacion 3FN.pdf   Apuntes/Bases de Datos/BBDD - Normalizacion 3FN.pdf
2  mover      Tema3_POO.pdf                  Apuntes/Programacion/Tema3_POO.pdf
  · java y sql.pdf: sin asignatura (dudoso entre Bases de Datos y Programacion); no se toca

Simulación: 11 operaciones; no se ha cambiado nada.
```

### Deshacer

Cada ejecución queda registrada en `~/.local/share/apuntes/historial.json`, también si se
interrumpe a medias. `apuntes deshacer` calcula cómo volver atrás comprobando el disco en
ese momento:

- devuelve cada fichero movido o renombrado a su sitio;
- envía a la papelera lo que creó apuntes (copias, índices, resúmenes, zips);
- restaura el contenido anterior de un fichero reemplazado;
- quita las carpetas que creó, **solo si han quedado vacías**.

Nunca pisa nada. Si un fichero ya no está, o su sitio original lo ocupa otro, lo deja como
está y avisa. Lo enviado a la papelera se recupera desde la propia Papelera, y `deshacer`
te dice qué ficheros son.

```text
Deshacer #1 ordenar-todo (2026-11-04 18:15:52, /Users/marc/pruebas-tareas)
 #  Operación       Fichero                                   Destino / detalle
 1  a la papelera   INDICE.md                                 lo creó apuntes
 2  devolver        Apuntes/Bases de Datos/java y sql.pdf     java y sql.pdf
 …
16  quitar carpeta  Apuntes/                                  si queda vacía
  · Tema3_POO (1).pdf: está en la Papelera; recupéralo desde allí
```

El diseño está explicado en el [ADR 0004](docs/adr/0004-historial-y-deshacer.md).

### Probar sin miedo

Para probar con material falso, sin tocar tus ficheros, crea una carpeta de pruebas:

```bash
uv run scripts/crear_carpeta_pruebas.py      # crea ~/pruebas-tareas
apuntes ejecutar ordenar-todo ~/pruebas-tareas --simular
uv run scripts/crear_carpeta_pruebas.py --rehacer   # vuelve a empezar
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
| 1 | Fallo al ejecutar: la carpeta no existe, la acción no existe, una operación falló o cancelaste la confirmación |
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

El ejemplo completo, con 11 acciones, es [`acciones.json`](acciones.json)
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
| `origen` | no | Carpeta de trabajo por defecto. Admite `~`. Si en la orden se indica una CARPETA, tiene prioridad; si no hay ni una ni otra, se usa la carpeta actual. |
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
| `ia-clasificar` | `destino` (con `{asignatura}`) | 🤖 La IA lee el contenido, decide la asignatura y mueve el fichero. |
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

## IA (opcional)

Tres tipos de acción usan IA. Hay dos proveedores intercambiables:

| Proveedor | Coste | Clave | Modelos |
|---|---|---|---|
| **Gemini** (por defecto) | Gratis, con límites por minuto y por día | `GEMINI_API_KEY` de [aistudio.google.com](https://aistudio.google.com) | `gemini-3.8-flash`; si está saturado, pasa a `gemini-3.6-flash` y `gemini-3.5-flash-lite` |
| **Claude** | De pago por uso | `ANTHROPIC_API_KEY` de [console.anthropic.com](https://console.anthropic.com) | `claude-opus-5-5` |

Las acciones son las mismas con cualquiera de los dos:

| Tipo | Qué hace | ¿Cuándo llama a la IA? |
|---|---|---|
| `ia-clasificar` | Lee cada PDF y lo mueve a la carpeta de su asignatura. Si no está segura, no lo toca. | Al planificar, porque necesita saber el destino |
| `ia-resumir` | Crea `tema.resumen.md` con los conceptos clave. | Al aplicar: `--simular` es gratis |
| `ia-preguntas` | Crea `tema.preguntas.md` con preguntas tipo test y sus soluciones. | Al aplicar: `--simular` es gratis |

Lee PDF (incluidas las tablas y los diagramas de las diapositivas), `.txt` y `.md`.
El resto de ficheros se saltan con un aviso.

### Configurar la clave (gratis, con Gemini)

1. En [aistudio.google.com](https://aistudio.google.com), pulsa *Get API key* y luego *Crear clave*. No pide tarjeta.
2. Copia la plantilla en tu configuración personal y pon la clave:

   ```bash
   mkdir -p ~/.config/apuntes && cp .env.example ~/.config/apuntes/.env
   ```

   ```bash
   open -e ~/.config/apuntes/.env      # GEMINI_API_KEY=tu-clave
   ```

3. Comprueba que todo está bien:

   ```bash
   apuntes estado
   ```

`~/.config/apuntes/.env` vale para cualquier carpeta y está fuera de todo repositorio. Un
`.env` en la carpeta actual también funciona, y está en `.gitignore` desde el primer commit:
**la clave nunca se sube al repositorio**.

| Variable | Para qué |
|---|---|
| `APUNTES_PROVEEDOR` | `gemini` o `claude`. Si no se indica, se usa el que tenga clave |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | La clave del proveedor |
| `APUNTES_MODELO` | Modelo preferido (opcional) |

### Sin clave o sin internet

La IA es opcional. Sin ella:

- `apuntes acciones` y `apuntes estado` avisan de qué falta;
- una acción con IA termina con un mensaje claro y el código 1;
- en un `pipeline`, **los pasos con IA se omiten y el resto se ejecuta igual**:

```text
Paso 4/5: clasificar-con-ia (ia-clasificar) en /Users/marc/pruebas-tareas
  Paso omitido: No hay conexión con la API de Gemini (¿sin internet?).
Sin IA: se omiten 1 paso(s); el resto se hace igual.
```

### Ejemplo real

En la carpeta de pruebas, con Gemini gratis, `ordenar-todo` deja a la IA los ficheros que las
palabras clave no resuelven:

```text
Paso 4/5: clasificar-con-ia (ia-clasificar) en /Users/marc/pruebas-tareas
#  Operación  Fichero           Destino / detalle
1  mover      documento(3).pdf  Apuntes/Sistemas Informaticos/documento(3).pdf
2  mover      java y sql.pdf    Apuntes/Bases de Datos/java y sql.pdf
  · apuntes-antiguos-1ESO.pdf: según la IA no es de ninguna asignatura (matemáticas de 1.º de ESO)
```

### Caché

Cada respuesta se guarda en `~/.cache/apuntes/ia.json`, asociada al contenido del fichero
y no a su nombre. Simular y luego aplicar no paga dos veces, y si una ejecución se corta,
al repetirla lo ya hecho sale gratis. Los `.resumen.md` y `.preguntas.md` que ya existen
no se regeneran: si quieres uno nuevo, borra el anterior. El diseño está explicado en el
[ADR 0003](docs/adr/0003-proveedor-ia.md).

## Evaluación según la rúbrica

Esta sección enlaza cada criterio de la rúbrica con **dónde se puede comprobar** en el
repositorio. Los tests citados se ejecutan con `uv run pytest -k NOMBRE`.

### Mínimos obligatorios

| Mínimo | Evidencia |
|---|---|
| Se instala siguiendo el README y `--help` funciona | [Instalación](#instalación): una orden, `uv tool install git+https://github.com/marcalvear/cli-apuntes`. Probado desde cero con la [release v1.0.0](https://github.com/marcalvear/cli-apuntes/releases/tag/v1.0.0) |
| Al menos 3 acciones propias en `acciones.json` | [`acciones.json`](acciones.json) tiene 11 acciones: 7 sin IA, 3 con IA y 1 pipeline que combina varias |
| Ninguna clave en el repo ni en su historial | El [primer commit](https://github.com/marcalvear/cli-apuntes/commit/4431e49) ya ignora `.env`. Las claves solo se leen del entorno ([`ia/entorno.py`](src/apuntes/ia/entorno.py)), y la plantilla es [`.env.example`](.env.example) |
| Al menos 10 commits que cuentan el proceso | Más de 60 commits en 10 [pull requests](https://github.com/marcalvear/cli-apuntes/pulls?q=is%3Apr), todos con un mensaje que explica el porqué |

### Acciones predefinidas funcionando (20 %)

| La rúbrica pide (Excelente) | Evidencia |
|---|---|
| 5 o más acciones propias útiles | 11 acciones en [`acciones.json`](acciones.json). Hay 11 tipos disponibles (10 ejecutables más `pipeline`), cada uno una clase en [`acciones.py`](src/apuntes/acciones.py) |
| Combinables | Tipo `pipeline` (por ejemplo, `ordenar-todo`, con 5 pasos). Test `test_pipeline_cada_paso_ve_el_resultado_del_anterior` |
| Salida clara: qué se ha hecho y sobre qué ficheros | Cada operación sale en una tabla con el fichero y su destino, y cada fichero que no se toca, con el motivo. Ver [Cómo trabaja `ejecutar`](#cómo-trabaja-ejecutar) |
| Sin efectos sorpresa: simulación previa | `--simular` muestra el mismo plan que luego se aplica ([ADR 0002](docs/adr/0002-planificar-y-aplicar.md)). Tests `test_planificar_no_modifica_el_disco` y `test_simular_muestra_el_plan_y_no_toca_nada` |
| Sin efectos sorpresa: confirmación antes de borrar o sobrescribir | Las acciones destructivas preguntan, y por defecto la respuesta es «no»; borrar va siempre a la Papelera. Test `test_destructiva_pide_confirmacion_y_por_defecto_no_hace_nada` |
| *(Extra)* | `apuntes deshacer` devuelve cada fichero a su sitio ([ADR 0004](docs/adr/0004-historial-y-deshacer.md)) |

### Configuración externa en `acciones.json` (15 %)

| La rúbrica pide (Excelente) | Evidencia |
|---|---|
| Esquema propio documentado en el README | [El fichero `acciones.json`](#el-fichero-accionesjson): raíz, campos comunes, filtro, los 10 tipos y las plantillas |
| El JSON se valida antes de ejecutar | Modelos Pydantic en [`config.py`](src/apuntes/config.py) y la orden `apuntes validar` |
| Los errores dicen qué campo falla | `acciones[0] (mover-pdf).destnio: campo desconocido (¿una errata?)`, con código de salida 3. Tests `test_errata_en_un_campo_se_detecta`, `test_json_mal_escrito_indica_linea_y_columna` y `test_validar_fichero_invalido_sale_con_3_y_nombra_el_campo` |
| Añadir una acción no exige tocar el código | Basta con escribirla en el JSON. Test `test_la_plantilla_de_ejemplo_es_valida` |
| ADR que justifica configuración externa y no código | [ADR 0001](docs/adr/0001-configuracion-externa.md) |

### Capa IA, secretos y modo sin red (15 %)

| La rúbrica pide (Excelente) | Evidencia |
|---|---|
| Al menos 2 acciones con IA útiles | `ia-clasificar`, `ia-resumir` e `ia-preguntas`, con dos proveedores: Gemini ([`ia/gemini.py`](src/apuntes/ia/gemini.py)) y Claude ([`ia/claude.py`](src/apuntes/ia/claude.py)). Probadas con la API real: ver [Ejemplo real](#ejemplo-real) |
| Clave en `.env`, ignorado desde el primer commit, y `.env.example` documentado | [`.gitignore`](.gitignore), [`.env.example`](.env.example) y [Configurar la clave](#configurar-la-clave-gratis-con-gemini) |
| Ninguna clave en el historial | Los tests nunca ven una clave real: la fixture `_sin_credenciales_reales` en [`tests/conftest.py`](tests/conftest.py) |
| Si no hay red, la CLI lo explica y sigue con las acciones sin IA | [Sin clave o sin internet](#sin-clave-o-sin-internet). Tests `test_sin_ia_el_pipeline_sigue_con_los_pasos_sin_ia`, `test_sin_ia_la_accion_de_ia_sale_con_1_y_lo_explica` y `test_acciones_avisa_si_falta_la_clave` |
| *(Extra)* | Caché por contenido, y `--simular` no gasta nada. Test `test_resumir_no_llama_a_la_ia_al_simular`. [ADR 0003](docs/adr/0003-proveedor-ia.md) |

### Robustez: excepciones y entradas feas (15 %)

| La rúbrica pide (Excelente) | Evidencia |
|---|---|
| Excepciones propias con mensajes humanos | [`errores.py`](src/apuntes/errores.py): `ConfigError`, `AccionNoValida`, `CarpetaNoValida`, `FicheroError`, `ErrorIA`, `IANoDisponible`, `DocumentoNoSoportado` y `EjecucionInterrumpida`. Cada una tiene mensaje, pista y código de salida |
| Ningún traceback ante errores previsibles | `_GrupoApuntes` en [`cli.py`](src/apuntes/cli.py) los convierte en mensaje más código de salida ([códigos](#códigos-de-salida)). Test `test_listar_carpeta_inexistente_sale_con_1_sin_traceback` |
| Nunca se pierde un fichero por un fallo a medias | Escritura atómica en [`disco.py`](src/apuntes/disco.py) y [`operaciones.py`](src/apuntes/operaciones.py). Tests `test_si_falla_a_medias_el_original_queda_intacto`, `test_mover_entre_discos_no_deja_el_destino_a_medias` y `test_si_el_disco_cambia_tras_planificar_se_detiene_sin_perder_nada` |
| Aserciones en desarrollo | `assert` sobre invariantes internas: por ejemplo, en [`acciones.py`](src/apuntes/acciones.py), que cada tipo tenga modelo y no se registre dos veces, y en [`ficheros.py`](src/apuntes/ficheros.py), que un tamaño no sea negativo |

### Diseño en clases y módulos (10 %)

| La rúbrica pide (Excelente) | Evidencia |
|---|---|
| Responsabilidades separadas | Interfaz, motor, acciones y proveedor de IA en módulos distintos (ver el mapa siguiente) |
| Visibilidad cuidada | Lo interno lleva `_` (`_GrupoApuntes`, `Vista._ficheros`, `_cliente_api`…). Los modelos de configuración son inmutables (`frozen=True`) |
| Métodos estáticos con sentido, como fábricas desde la configuración | `Accion.desde_config()` elige la clase según el `tipo` del JSON, y además `Configuracion.desde_fichero()`, `Documento.desde_fichero()` e `InfoFichero.desde_ruta()` |
| *(Extra)* | Patrones documentados: registro de tipos con `__init_subclass__`, decorador de caché (`ProveedorConCache`) e inyección de dependencias (papelera, IA, historial) para poder probarlo todo |

```text
src/apuntes/
├── cli.py            Interfaz (Typer + Rich): solo lee argumentos y pinta; sin lógica
├── config.py         Esquema de acciones.json (Pydantic) y búsqueda del fichero
├── motor.py          Planifica sobre una Vista virtual del disco y aplica en orden
├── acciones.py       Un tipo de acción = una clase; la fábrica es Accion.desde_config()
├── operaciones.py    Mover, Copiar, EnviarAPapelera, Escribir, GenerarConIA, CrearZip…
├── historial.py      Registro de ejecuciones y cálculo de deshacer
├── clasificador.py   Asignatura por palabras clave (sin IA)
├── ficheros.py       Inspección de carpetas (solo lectura)
├── disco.py          Escritura atómica
├── errores.py        Jerarquía de excepciones propias
└── ia/
    ├── proveedor.py  Interfaz común ProveedorIA
    ├── gemini.py     Proveedor Gemini (gratis, por defecto)
    ├── claude.py     Proveedor Claude
    ├── cache.py      Decorador con caché por huella SHA-256
    ├── prompts.py    Instrucciones comunes a los dos proveedores
    ├── documento.py  Fichero → algo que la IA pueda leer
    └── entorno.py    .env y elección de proveedor
```

### Pruebas y calidad (15 %)

| La rúbrica pide (Excelente) | Evidencia |
|---|---|
| Camino feliz y 3 casos feos | 180 tests en [`tests/`](tests/), con un 92 % de cobertura. Hay decenas de casos feos: JSON roto, ruta inexistente, disco que falla a medias, sin red, clave inválida, modelo saturado… |
| En carpetas temporales | Todos usan `tmp_path`. Fixtures que sustituyen la papelera, la IA, el historial y las credenciales: [`tests/conftest.py`](tests/conftest.py) |
| Ejecutadas en GitHub Actions | [`tests.yml`](.github/workflows/tests.yml) ejecuta `ruff` y `pytest` en Linux, macOS y Windows, con Python 3.12 y 3.13 |
| Auditadas por el alumno (sabe explicar cada aserción) | [Guía de los tests](docs/tests.md): qué comprueba cada test y por qué |

### Instalación, documentación y proceso (10 %)

| La rúbrica pide (Excelente) | Evidencia |
|---|---|
| Se instala con una orden siguiendo el README | [Instalación](#instalación), con `uv tool install` o `pipx install` |
| Release v1.0 etiquetada con changelog | [Release v1.0.0](https://github.com/marcalvear/cli-apuntes/releases/tag/v1.0.0) y [CHANGELOG.md](CHANGELOG.md) |
| Historial con ramas y PR legibles | 10 [pull requests](https://github.com/marcalvear/cli-apuntes/pulls?q=is%3Apr+is%3Amerged), uno por fase: esqueleto, configuración, motor, IA, Gemini, historial, release, evaluación, acción propia (`copiar-a-icloud`) y este recuento. `main` está protegida: todo entra por PR |

## Desarrollo

```bash
git clone https://github.com/marcalvear/cli-apuntes && cd cli-apuntes
uv sync                      # crea .venv con dependencias
uv run apuntes --help        # ejecuta la versión del código
uv run pytest                # tests
uv run ruff check . && uv run ruff format --check .
```

Los tests usan carpetas temporales y nunca tocan ficheros reales, ni la papelera, ni
la API de Claude: una IA falsa responde por ella. GitHub Actions
los ejecuta en Linux, macOS y Windows en cada push y pull request.

Qué comprueba cada test y por qué está explicado en la [guía de los tests](docs/tests.md).
Las decisiones de diseño están documentadas en [`docs/adr/`](docs/adr/), y los cambios de cada
versión, en el [CHANGELOG](CHANGELOG.md).
