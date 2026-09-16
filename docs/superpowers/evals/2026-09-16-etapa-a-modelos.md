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
