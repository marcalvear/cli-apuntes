# ADR 0002: Las acciones planifican operaciones; el motor las aplica

- **Estado:** aceptada
- **Fecha:** 2026-11-04

## Contexto

Las acciones de `apuntes` mueven, renombran y envían a la papelera ficheros
reales del usuario. La rúbrica y el sentido común piden:

- un modo `--simular` que enseñe *exactamente* lo que pasará;
- confirmación antes de borrar o sobrescribir;
- ningún fichero perdido ni a medias si algo falla;
- poder combinar acciones (pipelines) y probarlo todo sin tocar ficheros reales.

La forma ingenua (cada acción recorre la carpeta y llama a `shutil.move`
directamente, con un `if simular: print(...)` delante) mezcla decidir con
hacer. La simulación acaba desfasada respecto a lo que de verdad se ejecuta,
y un pipeline no se puede simular, porque el paso 2 depende de lo que haga
el paso 1.

## Decisión

Separamos **decidir** de **hacer**:

1. Cada tipo de acción (`acciones.py`) recibe los ficheros seleccionados y
   **devuelve operaciones** (`operaciones.py`: `Mover`, `Copiar`,
   `EnviarAPapelera`, `Escribir`, `CrearZip`). Nunca toca el disco.
2. El motor (`motor.py`) planifica sobre una **`Vista`**: una foto del disco
   que se actualiza con cada operación planificada. Así un pipeline se planifica
   entero y cada paso «ve» el resultado del anterior.
3. El **plan** se muestra siempre. `--simular` se detiene ahí, y la confirmación
   se pide sobre ese mismo plan.
4. `Motor.aplicar()` ejecuta las operaciones en orden. Cada una **comprueba
   antes** que el disco sigue como al planificar (el origen existe y el destino
   no lo ha ocupado nadie) y escribe de forma **atómica** (temporal +
   `os.replace`). Ante el primer fallo, el motor se detiene y lo dice.
5. Borrar es siempre **enviar a la papelera** del sistema. La papelera se
   inyecta en el motor, y en los tests es una carpeta temporal.

## Consecuencias

**A favor**

- `--simular` no puede mentir: lo que se muestra es la misma lista que luego se aplica.
- Las acciones son fáciles de probar: se comprueba el plan como datos, sin
  disco ni simulacros.
- Confirmar, simular y aplicar se programan una sola vez, en el motor, y
  sirven para todos los tipos, incluidos los futuros de IA.
- Abre la puerta a `deshacer`: cada operación aplicada se puede registrar e invertir.

**En contra**

- Hay más clases (operaciones, vista, plan) que en la versión ingenua.
- Entre planificar y aplicar el disco puede cambiar. Se mitiga con la
  comprobación previa de cada operación: si algo no cuadra, se detiene en
  lugar de pisar nada.
