# ADR 0001: Las acciones se definen en un fichero externo (acciones.json)

- **Estado:** aceptada
- **Fecha:** 2026-11-04

## Contexto

`apuntes` ejecuta acciones sobre el material de clase: mover PDFs a su
asignatura, renombrar con fecha, quitar duplicados, resumir con IA… Cada
persona organiza sus apuntes a su manera (otras asignaturas, otras carpetas,
otros criterios), y esas preferencias cambian a lo largo del curso.

Hay dos formas de dar soporte a eso:

1. **Acciones en el código:** una función por acción (`ordenar_descargas()`,
   `limpiar_temporales()`…), con las rutas y extensiones escritas dentro.
2. **Acciones en configuración:** el código solo sabe ejecutar unos pocos
   *tipos* genéricos (mover, renombrar, borrar…). Las acciones concretas son
   datos de un fichero JSON que escribe el usuario.

## Decisión

Usamos la opción 2. El código define **11 tipos** de acción
(`config.py` y, al ejecutar, una clase por tipo). Las acciones concretas
viven en `acciones.json`, que:

- tiene un campo `version` para poder cambiar el formato en el futuro sin
  romper los ficheros antiguos;
- se valida entero con Pydantic **antes** de ejecutar nada, de forma que un
  error no deja la carpeta a medio organizar;
- prohíbe campos desconocidos para que una errata (`destnio`) se detecte en
  lugar de ignorarse;
- se busca en `--config`, `$APUNTES_CONFIG`, `./acciones.json` y
  `~/.config/apuntes/acciones.json`, por ese orden.

## Consecuencias

**A favor**

- Añadir o cambiar una acción no exige tocar Python, ni reinstalar, ni saber
  programar: basta editar el JSON y ejecutar `apuntes validar`.
- Varias acciones reutilizan el mismo código probado. Un `mover` de PDFs y
  otro de diapositivas son la misma clase con datos distintos, así que cada
  tipo se prueba una vez y sirve para infinitas acciones.
- Las acciones se combinan con `pipeline` sin escribir código nuevo.
- Las acciones peligrosas son visibles y revisables: se lee en el fichero qué
  borra y con qué filtro, y las destructivas confirman por defecto.
- La misma CLI vale para cualquier usuario. Cada uno tiene su `acciones.json`
  y el ejemplo se genera con `apuntes init`.

**En contra y cómo lo mitigamos**

- *Un JSON puede estar mal escrito.* → Validación completa con mensajes que
  nombran el campo (`acciones[2] (limpiar).filtro.extensiones: debe ser una
  lista`) y código de salida 3.
- *Solo se puede hacer lo que permiten los tipos existentes.* → Los tipos son
  genéricos y combinables. Si hace falta uno nuevo, se añade una clase y su
  modelo, sin tocar el resto.
- *El esquema hay que documentarlo.* → Está en el README, campo a campo, y la
  plantilla de `apuntes init` sirve de ejemplo vivo. Un test comprueba que la
  plantilla siempre es válida.

## Alternativas descartadas

- **YAML o TOML:** son más cómodos de escribir a mano, pero JSON no necesita
  dependencias extra y es el formato que pide el enunciado.
- **Python como configuración (un `acciones.py`):** daría toda la flexibilidad,
  pero ejecutaría código arbitrario y no se podría validar antes de ejecutar.
