# Guía de los tests

Esta guía explica **qué comprueba cada grupo de tests y por qué**. Está pensada para poder
justificar cada aserción, no para leerla de memoria.

```bash
uv run pytest                 # los 180 tests (unos 2 segundos)
uv run pytest -v              # con el nombre de cada uno
uv run pytest tests/test_motor.py -k pipeline   # solo los que contienen "pipeline"
uv run pytest --cov=apuntes --cov-report=term-missing   # cobertura (92 %)
```

## 1. Las tres reglas de todos los tests

### Regla 1: nunca se tocan ficheros reales

Cada test que necesita ficheros recibe `tmp_path`, una carpeta temporal nueva y vacía que
pytest crea para ese test y borra después:

```python
def test_mover_crea_las_carpetas_del_destino(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    origen = tmp_path / "a.pdf"  # ← dentro de la carpeta temporal
```

Así los tests no dependen de lo que haya en tu ordenador, se pueden ejecutar en cualquier orden y
nunca pueden estropear tus apuntes.

### Regla 2: nada sale del ordenador ni del test

En [`tests/conftest.py`](../tests/conftest.py) hay *fixtures* con `autouse=True`. Se aplican solas a
**todos** los tests y sustituyen lo que sería peligroso o lento:

| Fixture | Sustituye | Por qué |
|---|---|---|
| `papelera` | La Papelera real del sistema | Los tests no deben llenarte la Papelera. `PapeleraFalsa` mueve los ficheros a otra carpeta temporal y anota sus nombres en `.recibidos`, para comprobar qué se «borró» |
| `ia` | La IA real (Gemini o Claude) | No se gasta dinero ni cuota, no hace falta internet y las respuestas son siempre las mismas. `IAFalsa` ([`tests/ia_falsa.py`](../tests/ia_falsa.py)) anota cada llamada en `.llamadas` |
| `historial` | `~/.local/share/apuntes/historial.json` | El historial de pruebas no se mezcla con el tuyo |
| `_sin_credenciales_reales` | Tus variables `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`… y tu `.env` | Un test nunca debe ver tu clave real |
| `_consola_ancha` | El ancho de la consola (80 columnas) | Rich parte las líneas largas, y un mensaje podía quedar cortado justo donde el test lo busca. Pasó de verdad en Linux |

Esto se llama **inyección de dependencias**: el código real recibe la papelera, la IA o el
historial «desde fuera» (por ejemplo, `Motor(config, papelera=..., ia=...)`), y los tests le pasan
versiones falsas.

### Regla 3: cada test comprueba una sola idea, y su nombre la dice

`test_si_el_sitio_original_esta_ocupado_no_se_pisa` se entiende sin leer el código. Casi todos
siguen el patrón **preparar → actuar → comprobar** (*Arrange, Act, Assert*):

```python
def test_mover_no_pisa_un_fichero_que_aparecio_despues(tmp_path, papelera):
    origen, destino = tmp_path / "a.pdf", tmp_path / "b.pdf"  # preparar
    origen.write_text("nuevo", encoding="utf-8")
    destino.write_text("valioso", encoding="utf-8")

    with pytest.raises(FicheroError, match="ya existe"):  # actuar
        Mover(origen, destino).aplicar(papelera)

    assert destino.read_text(encoding="utf-8") == "valioso"  # comprobar: no se ha pisado
    assert origen.exists()  # y el original sigue
```

## 2. Herramientas de pytest que aparecen

| Herramienta | Qué hace | Ejemplo |
|---|---|---|
| `assert x == y` | Si no se cumple, el test falla y pytest enseña los dos valores | `assert resultado.exit_code == 3` |
| `pytest.raises(Error, match="...")` | El test **pasa solo si** se lanza esa excepción con ese texto | Comprobar que un JSON roto lanza `ConfigError` |
| `@pytest.mark.parametrize` | Ejecuta el mismo test con varios datos. Por eso hay 155 funciones pero 180 tests | `test_tipo_de_clasifica_por_extension` con 7 nombres |
| `monkeypatch` | Cambia temporalmente una variable de entorno o una función, y lo restaura al acabar | `monkeypatch.setenv("APUNTES_PROVEEDOR", "claude")` |
| `CliRunner` (de Typer) | Ejecuta la CLI como si la escribieras en la terminal y captura la salida y el código de salida | `runner.invoke(app, ["validar"])` |
| `pytest.skip` | Salta un test que no se puede hacer en ese sistema | Los enlaces simbólicos en Windows sin permisos |

## 3. Qué comprueba cada fichero

### `test_ficheros.py`: inspección de carpetas (8 funciones, 18 tests)

- **Camino feliz:** la extensión decide el tipo (`.PDF` y `.pdf` son iguales), los tamaños se
  muestran legibles (`1536` → `"1.5 KB"`) y las carpetas salen primero.
- **Casos feos:** carpeta que no existe, un fichero donde se esperaba una carpeta, y un
  **enlace roto**, que se ignora sin romper el listado.

### `test_config.py`: el esquema de `acciones.json` (26 tests)

Es el fichero más importante para el criterio de configuración externa.

- `test_la_plantilla_de_ejemplo_es_valida`: el `acciones.json` que crea `init` siempre es válido
  y tiene al menos 5 acciones y 2 con IA. Si alguien lo rompe, el test falla.
- `test_el_acciones_json_del_repo_es_la_plantilla`: el fichero de la raíz del repo y el de `init`
  no pueden divergir.
- **Casos feos, uno por cada error posible**, y todos comprueban el **mensaje exacto**, porque la
  rúbrica pide que «los errores digan qué campo falla»:

  ```python
  def test_errata_en_un_campo_se_detecta():
      ...
      assert problemas_de(config(accion)) == [
          "acciones[0] (mover-pdf).destino: falta este campo obligatorio",
          "acciones[0] (mover-pdf).destnio: campo desconocido (¿una errata?)",
      ]
  ```

  Se cubren el JSON roto (con línea y columna), la versión desconocida, un tipo inventado, una
  regex inválida, días negativos, nombres repetidos, un pipeline con pasos inexistentes, un
  fichero que no es UTF-8… La función auxiliar `problemas_de` comprueba además que el código de
  salida es **3**.
- `test_localizar_respeta_la_prioridad`: el orden en que se busca el fichero (`--config` >
  `$APUNTES_CONFIG` > `./acciones.json` > `~/.config/apuntes/`). Usa `monkeypatch` para fingir otro
  `HOME`.

### `test_disco.py`: escritura atómica (3 tests)

El más interesante es `test_si_falla_a_medias_el_original_queda_intacto`. **Simula** que el disco
falla justo antes de colocar el fichero nuevo, sustituyendo `os.replace` por una función que lanza
un error, y comprueba dos cosas:

```python
assert ruta.read_text(encoding="utf-8") == "contenido original"  # no se ha perdido nada
assert list(tmp_path.iterdir()) == [ruta]  # ni queda el temporal
```

Es la prueba de «nunca se pierde un fichero por un fallo a medias».

### `test_operaciones.py`: cada operación por separado (10 tests)

Mover, copiar, papelera, escribir y zip. Lo importante son los casos feos:

- **No pisar:** si en el destino aparece un fichero después de planificar, `Mover` se niega.
- **Mover entre discos que falla a mitad:** se simulan los errores `EXDEV` («otro disco») y
  `ENOSPC` («disco lleno»). El original sigue intacto y en el destino no queda nada.
- **Copiar conserva la fecha** (`st_mtime`): importa porque `renombrar-con-fecha` la usa.
- **El zip guarda rutas relativas** y comprimir **no** borra los originales, porque eso es otra
  operación.

### `test_motor.py`: el motor y los 7 tipos sin IA (20 tests)

- `test_planificar_no_modifica_el_disco`: planificar (o sea, `--simular`) **no toca nada**. Se
  compara el contenido de la carpeta antes y después, y se comprueba que la papelera no ha
  recibido nada.
- Un test por tipo de acción, de principio a fin. Por ejemplo, `test_deduplicar_conserva_el_mas_antiguo`
  crea tres copias iguales y una distinta **del mismo tamaño**, para comprobar que se compara el
  contenido y no solo el tamaño.
- **Idempotencia:** `test_renombrar_dos_veces_no_cambia_nada` y el del índice. Repetir una acción
  sin cambios no hace nada.
- `test_pipeline_cada_paso_ve_el_resultado_del_anterior`: al **planificar** el pipeline, el índice
  ya enlaza el PDF en su carpeta nueva, aunque todavía no se ha movido nada. Es la prueba de la
  `Vista` virtual (ADR 0002).
- `test_si_el_disco_cambia_tras_planificar_se_detiene_sin_perder_nada`: entre planificar y
  aplicar, «alguien» crea un fichero en el destino. El motor aplica la primera operación, se
  detiene en la segunda con `EjecucionInterrumpida` («1 de 2 operaciones») y no pisa el fichero
  ajeno.

### `test_clasificador.py`: asignatura por palabras clave (5 funciones, 9 tests)

Por qué `"si"` (Sistemas Informáticos) **no** debe encajar con `sistema_solar.pdf`: las claves
cortas solo cuentan como palabra suelta. Y si hay empate (`java y sql.pdf`), no se decide.

### `test_ia.py`: la capa de IA (19 funciones, 26 tests)

- **Documento:** qué ficheros se pueden enviar (PDF, `.txt`, `.md`) y qué casos se rechazan con un
  mensaje claro: `.pptx`, un PDF falso, un fichero que no es UTF-8, un fichero vacío.
- **Caché:** que la segunda ejecución no llama a la IA (`falsa.llamadas` solo tiene una entrada),
  que cambiar las asignaturas sí vuelve a preguntar y que una caché dañada no es un error.
- **ProveedorClaude con un cliente falso:** sin red, se comprueba **qué petición se enviaría** (el
  PDF, el esquema cerrado y `fallbacks`) y cómo se traduce cada error: 401 → «la clave no es
  válida», 429 → «límite de uso», sin conexión…
- `test_resumir_no_llama_a_la_ia_al_simular`: `assert ia.llamadas == []` después de planificar.
  Es la prueba de que `--simular` es gratis.
- `test_sin_ia_el_pipeline_sigue_con_los_pasos_sin_ia`: el criterio «si no hay red, la CLI lo
  explica y sigue». El paso de IA aparece como omitido, y el `.tmp` sí se ha enviado a la papelera.

### `test_gemini.py`: el proveedor Gemini (19 funciones, 23 tests)

Como los de Claude, con un cliente falso. Además:

- `test_si_un_modelo_falla_se_usa_el_siguiente`: ante un 503, un 429 o un 404, la petición pasa al
  modelo siguiente. Se comprueba en `cliente.peticiones` que se intentaron `modelo-a` y `modelo-b`.
- `test_un_modelo_saturado_no_se_reintenta_en_la_misma_ejecucion`: lo que mejoramos tras la prueba
  real.
- La elección de proveedor según las variables de entorno.

### `test_historial.py`: historial y deshacer (19 tests)

- `test_deshacer_mover_devuelve_los_ficheros_y_quita_las_carpetas_creadas`: después de deshacer,
  la carpeta es **idéntica** a como estaba (`contenido(tmp_path) == antes`).
- Casos feos: un fichero borrado después, el sitio original ocupado, una carpeta que ya existía o
  en la que guardaste algo, deshacer dos veces, un historial dañado.

### `test_cli.py`: la CLI como la usa una persona (26 tests)

Aquí se comprueban los **códigos de salida** de la rúbrica (0 bien, 1 fallo, 2 uso, 3
configuración) y que **nunca aparece un traceback**:

```python
def test_listar_carpeta_inexistente_sale_con_1_sin_traceback(runner, tmp_path):
    resultado = runner.invoke(app, ["listar", str(tmp_path / "fantasma")])
    assert resultado.exit_code == 1
    assert "no existe" in resultado.output
    assert "Traceback" not in resultado.output
```

También se comprueba que la confirmación funciona: con Intro (no) no se toca nada, con `y` se
aplica y con `--si` ni se pregunta.

## 4. CI: los tests en tres sistemas

[`.github/workflows/tests.yml`](../.github/workflows/tests.yml) ejecuta `ruff` y `pytest` en
**Linux, macOS y Windows**, con Python 3.12 y 3.13, en cada push y en cada PR. Ya nos ha salvado dos
veces:

1. En **Linux**, Rich partía un mensaje largo justo donde el test lo buscaba. Se arregló con
   `_consola_ancha`.
2. En **Windows**, `read_text()` sin codificación usa cp1252 y no UTF-8, y fallaba con las tildes.
   Ahora el CI ejecuta pytest con `PYTHONWARNDEFAULTENCODING=1`, y `pyproject.toml` convierte ese
   aviso en error: cualquier lectura o escritura sin `encoding="utf-8"` falla en todos los sistemas.

## 5. Preguntas que te pueden hacer

**¿Por qué no pruebas con la IA de verdad?** Porque un test tiene que dar siempre el mismo
resultado, ser rápido y no costar dinero. La IA real responde distinto cada vez, puede estar
saturada y gasta cuota. Lo que se prueba es **nuestra** lógica: qué le enviamos, cómo
interpretamos la respuesta y qué hacemos si falla. La IA real la probamos a mano en
`~/pruebas-tareas` (ver README).

**¿Qué es un «caso feo»?** Una entrada o situación que no es la normal: un fichero que no existe,
un JSON roto, un disco que falla, la falta de red. Hay decenas, y el criterio pide al menos 3.

**¿Cómo sabes que un test sirve para algo?** Porque falla cuando el código está mal. Por ejemplo,
`test_resumir_no_regenera_lo_ya_hecho` descubrió un bug real: `ia-resumir` resumía sus propios
resúmenes. Haz la prueba: rompe a propósito una línea (cambia `"renombrar"` por `"saltar"` en
`si_existe`) y verás qué tests se ponen en rojo.

**¿Qué es una fixture?** Una función que prepara algo que los tests necesitan, como una carpeta,
una IA falsa o un `CliRunner`. El test la recibe como parámetro, por su nombre, y pytest se la da
hecha.

**¿Qué es `monkeypatch`?** Una fixture de pytest para cambiar algo solo durante un test, como una
variable de entorno o una función, y que se restaure solo al terminar.

**¿Qué cobertura tenéis y qué significa?** Un 92 %: es el porcentaje de líneas del código que
algún test ejecuta. Una cobertura alta no garantiza que no haya bugs, pero sí que casi todo el
código se ha ejecutado al menos una vez en un test que comprueba algo.
