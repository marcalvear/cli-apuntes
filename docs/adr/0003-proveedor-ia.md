# ADR 0003: La IA es un proveedor intercambiable, opcional y con caché

- **Estado:** aceptada
- **Fecha:** 2026-11-04

## Contexto

Tres acciones necesitan IA: clasificar un PDF por su contenido, resumirlo y
generar preguntas de repaso. Requisitos:

- la clave nunca puede llegar al repositorio;
- sin red o sin clave, la CLI debe explicarlo y seguir funcionando con las
  acciones que no usan IA;
- `--simular` no debería costar dinero si se puede evitar;
- los tests no pueden depender de la red ni gastar dinero.

## Decisión

1. **Interfaz `ProveedorIA`** (`ia/proveedor.py`) con cuatro métodos:
   `comprobar`, `clasificar`, `resumir` y `preguntas`. Las acciones solo
   conocen esta interfaz. Hay dos implementaciones reales:
   - `ProveedorGemini`, la de por defecto, usable gratis con una clave de AI Studio;
   - `ProveedorClaude`, de pago.

   `APUNTES_PROVEEDOR` elige entre las dos y, en los tests, se usa `IAFalsa`.
   Los prompts están en `ia/prompts.py` y son los mismos para los dos proveedores.
2. **Los PDF se envían tal cual**, sin extraer el texto en local, porque
   Claude también lee tablas, diagramas y código de las diapositivas.
3. **Clasificación con salida estructurada:** un JSON Schema cuyo campo
   `asignatura` es un `enum` con las asignaturas de `acciones.json` más
   `"ninguna"`. La respuesta no puede inventarse una asignatura. Si la
   confianza es baja, el fichero no se mueve.
4. **La IA se llama al aplicar, no al planificar**, en `ia-resumir` e
   `ia-preguntas` (operación `GenerarConIA`), así que `--simular` es gratis.
   `ia-clasificar` necesita la respuesta para saber el destino y sí llama al
   planificar.
5. **Caché** (`ProveedorConCache`, patrón decorador), indexada por la huella
   SHA-256 del contenido, el modelo y los parámetros. Simular y luego aplicar
   no paga dos veces, y repetir tras un fallo no repite lo ya hecho.
6. **Disponibilidad comprobada una vez y en local:** `comprobar()` mira si hay
   clave y si se puede abrir una conexión con la API (3 s). Si falla:
   - la acción con IA termina con un mensaje y el código 1;
   - en un pipeline, el paso con IA se omite y el resto se ejecuta;
   - `apuntes acciones` y `apuntes estado` avisan.
7. **Secretos:** la clave se lee de `ANTHROPIC_API_KEY`, en un `.env` local o
   en `~/.config/apuntes/.env`. `.env` está en `.gitignore` desde el primer
   commit y `.env.example` documenta qué poner. El SDK solo se importa si
   alguna acción usa IA.
8. **Fallbacks por defecto** (`fallbacks: "default"`): si los filtros de
   seguridad del modelo rechazan un documento (un falso positivo con apuntes
   de seguridad informática, por ejemplo), la API lo reintenta con el modelo
   alternativo recomendado.

## Consecuencias

- Cambiar de proveedor (otro modelo, una IA local) es escribir otra clase,
  sin tocar las acciones.
- Los tests prueban la lógica de IA sin red: el SDK se sustituye por un
  cliente falso que comprueba qué petición se enviaría.
- La caché ocupa disco (`~/.cache/apuntes/ia.json`). Se puede borrar sin
  riesgo, y `apuntes estado` dice dónde está.
- La comprobación de red es aproximada: con un proxy no se comprueba. Si la
  conexión cae a mitad, el error se traduce igualmente a un mensaje humano y
  el motor se detiene sin dejar ficheros a medias.

## Actualización (2026-11-04): Gemini como proveedor por defecto

La API de Claude es de pago, y para un proyecto de clase hace falta una opción
gratuita. Se añadió `ProveedorGemini`, que **no exigió tocar ni las acciones, ni el
motor, ni la caché**: es la prueba práctica de que la interfaz común era la
decisión correcta.

La capa gratuita de Gemini satura a veces un modelo (503) o agota su cuota (429).
Por eso el proveedor prueba una lista de modelos gratuitos en orden y, si uno
falla, no lo vuelve a intentar durante esa ejecución. En la prueba real, con
`gemini-3.8-flash` saturado, la clasificación pasó sola a `gemini-3.6-flash` y
acertó los tres casos difíciles.
