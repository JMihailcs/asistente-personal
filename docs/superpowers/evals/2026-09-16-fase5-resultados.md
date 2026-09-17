# Etapa A — Comparación de modelos

550 corridas: 22 casos x 5 modelos x 5 repeticiones, variante `baseline`
(el prompt y las herramientas de producción, sin tocar). Cero errores y
cero timeouts.

Esta es la primera medición real de fiabilidad del proyecto. Hasta acá
lo único que había era un `xfail` que decía "a veces falla".

## Lectura

**El problema era el modelo, no el diseño.** `qwen3:8b` acierta 110 de
110 en las cinco dimensiones, con el mismo prompt y el mismo esquema de
routers donde `mistral-nemo` omite `list_name` de forma sistemática.
Queda descartada la hipótesis de que el patrón de routers o el prompt
fueran la causa.

**Los fallos son deterministas, no intermitentes.** Cada par
(caso, modelo) da 0/5 o 5/5, casi nunca algo en el medio. "A veces
falla" era una descripción equivocada: falla *siempre* en los mismos
sitios. Eso cambia el problema — no hay que pelear contra el azar sino
arreglar casos concretos.

**Cada modelo se rompe distinto, y el desglose por dimensión es lo que
lo muestra.** `llama3.1:8b` acierta 100% en argumentos y efecto pero
86% en elección de herramienta; `mistral-nemo` es al revés. Con un solo
número los dos se habrían visto como "85% y listo", que no sugiere
ningún arreglo.

**Los fallos de `llama3.1:8b` son todos de la misma clase**: `saludo`,
`capacidades` y `tarea-sin-lista-pregunta`, los tres casos donde lo
correcto es NO llamar ninguna herramienta. No es incompetente, es
demasiado ansioso. Sin los casos de "ninguna herramienta" esto no se
habría visto, y un cambio que hiciera al modelo llamar tools todo el
tiempo se habría leído como mejora.

**`qwen3:4b` no tiene razón de existir en este montaje.** Se incluyó
esperando "menos fiable pero más rápido". Salió casi tan fiable como el
8B y **70% más lento** (28.9s contra 17.1s), porque también razona
antes de responder y con menos parámetros necesita más pasos.

## Tabla

| modelo | corridas | herramienta | argumentos | efecto | respuesta | fundamentada | latencia mediana |
|---|---|---|---|---|---|---|---|
| default (mistral-nemo 12B) | 110 | 86% | 77% | 82% | 96% | 100% | 3.92s |
| hermes3:8b | 110 | 86% | 90% | 94% | 94% | 99% | 2.59s |
| llama3.1:8b | 110 | 86% | 100% | 100% | 96% | 100% | 8.02s |
| qwen3:4b | 110 | 100% | 100% | 96% | 100% | 100% | 28.87s |
| **qwen3:8b** | 110 | **100%** | **100%** | **100%** | **100%** | **100%** | 17.12s |

## Qué caso falla en cada modelo

Corridas malas sobre 5. Un punto es 5/5 correctas.

| caso | default | hermes3 | llama3.1 | qwen3:4b | qwen3:8b |
|---|---|---|---|---|---|
| accion-reiniciar-servicio | 5/5 | . | . | . | . |
| accion-vaciar-cache | . | 5/5 | . | . | . |
| capacidades | . | . | 5/5 | . | . |
| diag-procesos | 5/5 | . | . | . | . |
| fuera-de-alcance-internet | 5/5 | 4/5 | . | . | . |
| nota-buscar | . | 1/5 | . | . | . |
| nota-guardar-corta | 5/5 | 5/5 | . | 4/5 | . |
| saludo | . | . | 5/5 | . | . |
| tarea-agregar-con-lista | 5/5 | . | . | . | . |
| tarea-completar | 5/5 | . | . | . | . |
| tarea-completar-lista-larga | 5/5 | . | . | . | . |
| tarea-sin-lista-pregunta | 5/5 | 5/5 | 5/5 | . | . |

Los 10 casos restantes los aciertan los cinco modelos y se omiten.

`tarea-sin-lista-pregunta` falla en 3 de 5 modelos: solo el par qwen
pregunta a qué lista va la tarea en vez de inventar una.

## Los dos bugs de mistral-nemo, ya separados

Durante esta etapa se agregaron dos casos para desconfundir el largo
del nombre de lista de la acción, que hasta entonces estaban mezclados:

- **`complete` nunca pasa `list_name`** — 0/5 con lista de una palabra
  ("Compras") y 0/5 con una de tres ("Idea de negocio"). Es específico
  de la acción.
- **`add` falla solo con "Idea de negocio"** — anda con "Casa" (una
  palabra) y con "Casa Nueva" (dos). **El largo no es la causa.** El
  pedido dice "a mi lista *de* Idea *de* negocio", con dos
  preposiciones; la hipótesis es que el modelo corta en la segunda.
  **No verificado** — haría falta un caso tipo "Lista de Compras".

Ninguno de los dos aparece en los modelos qwen.

## Validación del arnés

Se revisaron todos los fallos concretos buscando falsos positivos del
instrumento. **No se encontró ninguno**: todos los fallos marcados son
comportamientos reales del modelo. El único caso discutible es
`accion-reiniciar-servicio`, donde el modelo contesta "¿está seguro de
que desea continuar?" en vez de avisar que la acción quedó pendiente de
confirmación — el prompt pide explícitamente lo segundo, así que el
fallo es legítimo aunque la aserción (buscar la subcadena "confirm")
sea frágil.

## Pasa a la Etapa B

El plan original decía llevar los 2 mejores a probar chain-of-thought.
**Esos 2 ya están en 100%**, así que medir variantes sobre ellos no
puede mostrar nada: solo pueden empatar o empeorar.

La pregunta útil cambió. Con `qwen3:8b` al 100% en 17.1s y
`hermes3:8b` al 90% en 2.6s, la decisión real es si se paga 6,5x de
latencia por ese 10%. Lo que sí vale medir es **si el chain-of-thought
sube a `hermes3:8b` o `llama3.1:8b` al 100% conservando su ventaja de
velocidad**. Esa es la Etapa B propuesta.

---

# Etapa B — variantes de razonamiento

Corrida sobre `hermes3:8b` y `llama3.1:8b`, que eran los que tenían
margen: los dos qwen ya estaban en 100% en la Etapa A y ninguna variante
podía mejorarlos. 660 corridas (2 modelos x 3 variantes x 22 casos x 5).

## Resultado: ninguna variante mejora a ningún modelo

Seis celdas medidas, cero mejoras. Lo mejor que logra una variante es
empatar con el baseline.

| modelo / variante | herramienta | argumentos | efecto | respuesta | fundamentada | latencia |
|---|---|---|---|---|---|---|
| **hermes3 baseline** | **86%** | **90%** | 95% | 95% | 99% | **2.6s** |
| hermes3 cot_prompt | 86% | 90% | 95% | 95% | 99% | 3.6s |
| hermes3 cot_arg | 82% | 86% | 89% | 78% | 95% | 5.4s |
| hermes3 two_step | 67% | 76% | 87% | 89% | 95% | 7.3s |
| **llama3.1 baseline** | **86%** | **100%** | **100%** | 95% | 100% | **8.0s** |
| llama3.1 cot_prompt | 85% | 99% | 99% | 95% | 99% | 8.5s |
| llama3.1 cot_arg | 86% | 100% | 100% | 95% | 100% | 10.4s |
| llama3.1 two_step | 77% | 91% | 95% | 95% | 100% | 10.2s |

**Cuanto más razonamiento intermedio, peor.** En los dos modelos,
`two_step` es la peor variante, y todas son más lentas que el baseline.

- **`cot_prompt` es ruido.** Empata en los dos modelos, dentro de una
  corrida de diferencia, y cuesta latencia.
- **`cot_arg` empeora a hermes3 en las cinco dimensiones** y a llama3.1
  lo deja igual pero 30% más lento. El spec apostaba a que razonar dentro
  de la llamada "deja de competir con llamar la herramienta". Era
  incorrecto: un `motivo` obligatorio no ordena el pensamiento, agrega un
  argumento más que se puede llenar mal.
- **`two_step` es el peor en los dos.** El planificador corre sin
  herramientas a propósito y escribe el plan de memoria; ese plan entra
  al ejecutor con formato de instrucción. Cuando alucina no se corrige,
  contamina. En llama3.1 agrega cuatro casos fallados nuevos que el
  baseline acertaba.

## La hipótesis de llama3.1 quedó refutada

Sus tres fallos del baseline son todos "no debería haber llamado ninguna
herramienta" (`saludo`, `capacidades`, `tarea-sin-lista-pregunta`). La
esperanza era que razonar antes frenara esa ansiedad. **No lo hace**:
los mismos tres casos fallan 5/5 con `cot_prompt` y con `cot_arg`. Es
carácter del modelo, no falta de razonamiento.

## Sobre los 12 errores

11 de las 660 corridas terminaron en `UnexpectedModelBehavior` de
pydantic-ai (el modelo emitió argumentos inválidos varias veces y se
agotaron los reintentos) y 1 en timeout. Son comportamiento real del
modelo, casi todos en `hermes3` con `cot_arg` y `two_step`, así que
suman a la conclusión en vez de contaminarla.

Limitación del arnés a corregir: hoy un error cuenta como fallo en las
cinco dimensiones, lo que infla un poco la caída de `fundamentada` en
esas celdas. Convendría registrarlo como fallo de elección/argumentos y
dejar las otras dimensiones como no evaluables.

---

# Experimento C — qwen3:8b con el razonamiento apagado

Etapa B deja una hipótesis sin aislar: el razonamiento agregado por
fuera estorba, pero `qwen3:8b`, que razona por entrenamiento, acierta
110/110. ¿Ese 100% viene del thinking o del modelo?

Variante `no_think`: `openai_reasoning_effort="none"`. Por el endpoint
`/v1` de Ollama 0.34 es el único control que funciona; `think: false` y
`/no_think` en el mensaje se ignoran (verificado).

| | herramienta | argumentos | efecto | respuesta | fundamentada | latencia |
|---|---|---|---|---|---|---|
| qwen3:8b con thinking | 100% | 100% | 100% | 100% | 100% | 17.1s |
| **qwen3:8b sin thinking** | **95%** | **100%** | **100%** | **95%** | **100%** | **3.9s** |
| mistral-nemo (producción) | 86% | 77% | 82% | 95% | 100% | 3.9s |

**Sin thinking, qwen3:8b le gana al modelo de producción en todas las
dimensiones a la misma latencia exacta**, y es 4,4x más rápido que con
thinking.

Falla un solo caso, 5 de 5: `tarea-sin-lista-pregunta`. Ante "Agrega la
tarea comprar leche", en vez de preguntar a qué lista va, inventa
`list_name: "compras"`.

**Lectura refinada:** la capacidad de llamar herramientas bien viene del
modelo; lo que agrega el thinking, en estos casos, es darse cuenta de
que falta un dato y preguntar. Es un solo tipo de situación sobre 22
casos: no prueba que sea lo único que aporta el thinking, solo que es lo
único que estos casos detectan.

Ese fallo **no lo atrapa la validación de argumentos existente**: el
modelo pasa un `list_name` válido, solo que inventado. Se atraparía con
un guardrail que pida confirmación al agregar a una lista inexistente en
vez de crearla en silencio. Queda para la fase de guardrails.

## Conclusión de la fase

1. El problema de fiabilidad era el modelo, no el diseño de routers ni
   el prompt.
2. El chain-of-thought agregado por fuera no sirve en este montaje:
   cero mejoras en seis celdas, y las formas más elaboradas empeoran.
3. Hay dos opciones reales para producción:
   - `qwen3:8b` **con** thinking: 100% en todo, 17.1s por respuesta.
   - `qwen3:8b` **sin** thinking: 21/22 casos perfectos, 3.9s, igual
     latencia que hoy. Pierde solo el caso de preguntar por un dato
     faltante, cubrible con un guardrail.

Elegir entre las dos es una decisión de producto (latencia contra ese
caso), no de fiabilidad.
