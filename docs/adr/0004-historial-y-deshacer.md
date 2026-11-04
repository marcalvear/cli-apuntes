# ADR 0004: Historial de ejecuciones y `deshacer` calculado desde el disco

- **Estado:** aceptada
- **Fecha:** 2026-11-04

## Contexto

`--simular` y la confirmación evitan sorpresas *antes* de actuar. Pero el usuario
puede darse cuenta *después* de que una acción no era lo que quería: una
plantilla de nombre mal pensada o una carpeta equivocada. Ordenar 200 PDF a
mano para volver atrás no es una opción.

## Decisión

1. **Cada operación sabe describirse** (`Operacion.registro()`). El registro se
   toma *justo antes* de aplicarla, para capturar el estado previo:
   - si el destino estaba ocupado;
   - qué carpetas habrá que crear;
   - el contenido anterior de un fichero de texto que se va a reemplazar.
2. **El motor guarda cada ejecución** en `~/.local/share/apuntes/historial.json`
   (`XDG_DATA_HOME`), escrito de forma atómica. Guarda las 50 últimas, y también
   las interrumpidas, con lo que llegó a hacerse.
3. **`deshacer` calcula las inversas en orden contrario y comprobando el disco en
   ese momento**, no fiándose solo del registro:
   - si un fichero ya no está donde lo dejamos, o su sitio original está
     ocupado, **no se toca** y se avisa;
   - las copias, índices, resúmenes y zips creados se envían a la papelera;
   - un fichero reemplazado recupera su contenido anterior;
   - las carpetas que creó la acción se quitan **solo si han quedado vacías**,
     de dentro afuera. Una carpeta que ya existía nunca se toca.
4. **Lo enviado a la papelera no se recupera automáticamente**, porque cada
   sistema operativo guarda la papelera de una forma distinta. Se avisa de
   qué ficheros son para recuperarlos desde la Papelera.
5. `deshacer` muestra el plan inverso, admite `--simular` y `--si`, y pide
   confirmación (por defecto, «no»). Para aplicar usa el mismo
   `aplicar_en_orden` que `ejecutar`: las mismas comprobaciones y la misma
   escritura atómica.

## Consecuencias

- Deshacer es **idempotente frente a fallos**: si se interrumpe a medias, la
  ejecución no se marca como deshecha, y al repetirlo se recalcula desde el
  disco y solo se hace lo que falta.
- El historial guarda rutas, no contenidos, salvo el texto anterior de los
  ficheros reemplazados (índices pequeños). No crece sin límite.
- Recuperar lo que hay en la papelera sigue siendo manual. Es un compromiso
  aceptable: borrar ya era la única operación que pedía confirmación siempre.
