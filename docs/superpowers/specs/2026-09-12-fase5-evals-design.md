# Asistente Mikha — Fase 5: Evals

## Contexto

Continúa el roadmap (Fase 1: diagnóstico, Fase 2: memoria + Docker,
Fase 3: tareas, Fase 4: interfaz web). Esta fase construye el
instrumento de medición que el proyecto viene necesitando desde la
Fase 2.

El problema central no resuelto es la **fiabilidad del tool-calling del
modelo local**. Lo que sabemos hoy es anecdótico: colapsa a partir de
~4-5 herramientas simultáneas (medido informalmente en la Fase 2, lo
que motivó el patrón de routers), omite `list_name` con ciertas frases,
y una vez alucinó un comando `meeting` inexistente. El único termómetro
es `tests/test_tasks_integration.py::test_agent_adds_and_lists_task`,
marcado `xfail` no estricto: dice "falló" pero no dice por qué.

Esta fase reemplaza esa anécdota por números, y usa esos números para
decidir. No agrega funcionalidad de cara al usuario.

**Decisión de alcance:** los guardrails se separan a una fase
posterior. Un guardrail que valga la pena depende de qué falle de
verdad, y eso todavía no está medido. Medir primero es lo que permite
diseñarlos sobre datos en lugar de intuición.

## Decisiones

| Aspecto | Decisión |
|---|---|
| Alcance de la fase | Solo medición. Guardrails a una fase posterior |
| Forma del arnés | CLI dedicado (`mikha-eval`) con reporte, no tests de pytest |
| Veredicto | Determinista, sin juez LLM (ni local ni externo) |
| Dimensiones medidas | Cinco, una por función de `checks.py`: elección de herramienta (incluye no llamar ninguna cuando corresponde), argumentos, efecto real en disco, forma de la respuesta, y no-invención |
| Puntuación | Por dimensión y por caso, como tasa sobre N repeticiones — no un sí/no global |
| Repeticiones | 5 por caso |
| Formato de casos | YAML declarativo, fuera del paquete |
| Resultados crudos | JSONL, una línea por corrida, escrita al terminar cada una |
| Estrategia de barrido | Dos etapas: modelos primero, variantes de prompt sobre los 2 mejores |
| Modelos comparados | Baseline `mistral-nemo:12b` + `qwen3:8b`, `llama3.1:8b`, `hermes3:8b`, y un 3-4B chico |
| Variantes de prompt | `baseline`, `cot_prompt`, `cot_arg`, `two_step` |
| Impacto en producción | Ninguno hasta que los números decidan. Las variantes se construyen del lado de la eval |

### Por qué sin juez LLM

Mikha corre entera en esta máquina; un juez vía API externa rompería
ese principio y agregaría costo por corrida. Un juez local sería
ruidoso: un modelo chico puntuando produce mediciones que cambian entre
corridas sin que cambie el código, que es exactamente lo contrario de
lo que un instrumento tiene que hacer.

La no-invención, que es lo que motivaría un juez, se verifica cotejando
valores (ver "El chequeo de no-invención").

### Por qué CLI y no pytest

La fiabilidad es una tasa, no un booleano. pytest no sabe expresar
"3 de 5" ni comparar modelos: habría que inventar un contador dentro
del test y reconfigurar el entorno para cada modelo. El `xfail` actual
se mantiene como canario barato dentro de la suite.

## Arquitectura

```
evals/casos/*.yaml          (datos: qué se le pide y qué se espera)
          │
          ▼
src/asistente_mikha/evals/
  cases.py    carga y valida los YAML
  variants.py construye el agente para (modelo, variante)
  runner.py   ejecuta cada corrida en un vault temporal
  checks.py   funciones puras: historial + disco → veredicto
  report.py   JSONL → tabla
  cli.py      mikha-eval
          │
          ▼
evals/resultados/*.jsonl    (crudo, reanudable, re-analizable)
          │
          ▼
docs/superpowers/evals/*.md (reporte y recomendación, versionados)
```

La separación importante es **medir ≠ analizar**. El runner solo
produce filas crudas; el reporte las agrega. Si estuvieran pegados,
cada pregunta nueva sobre los datos costaría otra corrida de horas.

La segunda separación importante es **chequeos sin modelo**:
`checks.py` recibe el historial del turno y el estado del disco, y
devuelve veredictos. No invoca al LLM, así que tiene tests unitarios
propios que corren en milisegundos. Un instrumento de medición sin
tests mide cualquier cosa.

## Componentes

### `cases.py`

Carga `evals/casos/*.yaml` a dataclasses y valida el esquema al cargar
(un caso mal escrito tiene que fallar antes de gastar horas de
corrida, no en medio).

Vocabulario de un caso:

```yaml
id: agregar-tarea-con-lista-explicita
mensaje: "Agrega la tarea 'comprar granos de cafe' a mi lista de Idea de negocio."
prepara:                      # estado inicial del vault (opcional)
  tareas:
    Casa: ["lavar los platos"]
espera:
  herramienta: tasks          # nombre, o `ninguna`
  argumentos:                 # subconjunto; solo se comparan las claves presentes
    action: add
    list_name: "Idea de negocio"
  archivos:                   # efecto real en disco (opcional)
    - patron: "Tareas/*.md"
      contiene: "comprar granos de cafe"
  respuesta_contiene: []      # subcadenas obligatorias (opcional)
  respuesta_pregunta: false   # exige un signo de interrogación (opcional)
  fundamentada: true          # activa el chequeo de no-invención
```

`herramienta: ninguna` es un caso de primera clase, no la ausencia de
expectativa: cubre saludos, preguntas de capacidades, y pedidos fuera
de alcance.

### `variants.py`

Construye `(agente, forma de ejecutar el turno)` para cada variante.
Ninguna toca el código de producción.

- **`baseline`** — `build_agent()` tal como está hoy.
- **`cot_prompt`** — mismo agente, con una instrucción de razonar paso
  a paso agregada al system prompt.
- **`cot_arg`** — cada herramienta del registro se envuelve con un
  parámetro `motivo: str` obligatorio, que el modelo llena antes de los
  argumentos reales.
- **`two_step`** — dos turnos: el primero contra un agente **sin
  herramientas registradas** que devuelve un plan en texto; el segundo
  contra el agente normal con ese plan en el contexto. Quitarle las
  herramientas al planificador es deliberado: si las tiene, la variante
  degenera en el baseline con pasos de más.

**Mecanismo de `cot_arg`, verificado en vivo contra pydantic-ai
2.42.0:** no alcanza con asignar `__signature__` al wrapper —
pydantic-ai construye el esquema desde `typing.get_type_hints()`, así
que hay que asignar **también** `__annotations__`. Con ambos, el
esquema resultante es:

```
sin envolver: params = ['action', 'list_name']           required = ['action']
envuelta:     params = ['motivo', 'action', 'list_name'] required = ['motivo', 'action']
```

### `runner.py`

Por cada combinación (modelo × variante × caso × repetición):

1. Vault temporal aislado, más el estado inicial que pida `prepara`.
2. Sesión de agente nueva (sin historial arrastrado entre corridas).
3. Ejecuta el turno, con timeout.
4. Extrae las llamadas reales inspeccionando los `ToolCallPart` del
   historial — **no** parseando el texto de la respuesta.
5. Pasa historial y estado del disco a `checks.py`.
6. Escribe una línea JSONL con: modelo, variante, caso, repetición,
   veredicto por dimensión, latencia, herramientas invocadas con sus
   argumentos, y la respuesta completa.

Guardar la respuesta completa y los argumentos crudos es lo que permite
re-analizar sin volver a correr.

**Reanudable:** al arrancar lee el JSONL existente y saltea las
combinaciones ya hechas. Una interrupción no cuesta la corrida entera.

### `checks.py`

Funciones puras, una por dimensión, cada una devolviendo un veredicto
con su motivo:

- `eligio_herramienta` — la herramienta llamada coincide con la
  esperada. Si se esperaba `ninguna`, no se llamó ninguna.
- `argumentos_correctos` — los pares clave/valor esperados están
  presentes. Comparación de subconjunto: los argumentos extra no
  penalizan. Texto normalizado (minúsculas, espacios colapsados,
  acentos plegados) para no castigar "Idea de negocio" vs "idea de
  negocio", que es la misma lista.
- `efecto_correcto` — los archivos declarados existen y contienen lo
  declarado.
- `respuesta_ok` — subcadenas obligatorias y, si se pidió, que haya
  pregunta.
- `fundamentada` — ver abajo.

### El chequeo de no-invención

La regla más delicada del arnés. Comparar literalmente daría **falsos
fallos**: si la herramienta devuelve `31.23` y el modelo dice "unos 31
GB", eso está bien, no es invención.

El chequeo extrae los números de la respuesta y exige que cada uno se
corresponda con algún valor devuelto por la herramienta, con tolerancia
de redondeo (coincide si redondear el valor de la herramienta a 0 o 1
decimales da el número de la respuesta, o si la diferencia relativa es
menor al 2%). Los números que no se corresponden con nada son
invención.

Excepciones necesarias, porque son lenguaje y no datos:
- Números que coinciden con la cantidad de elementos de una colección
  devuelta ("tenés 3 listas").
- Enteros del 0 al 10 cuando aparecen en palabras o como ordinales.

Estas reglas son precisamente por qué `checks.py` no habla con ningún
modelo: `31.23 → "31 GB"` debe pasar y `31.23 → "45 GB"` debe fallar, y
eso se prueba en milisegundos.

### `report.py` y `cli.py`

El reporte agrega el JSONL a una tabla Markdown: filas por modelo o
variante, columnas por dimensión, celdas con la tasa de acierto, más
una columna de **latencia mediana**. Debajo, la lista de fallos
concretos con el caso y el motivo.

CLI:

```
mikha-eval --modelos mistral-nemo:12b,qwen3:8b --variantes baseline \
           --repeticiones 5 --salida evals/resultados/etapa-a.jsonl
mikha-eval reporte evals/resultados/etapa-a.jsonl
```

## Los casos

Unos 20, repartidos:

- **Herramienta y argumentos** — agregar tarea con lista explícita,
  listar tareas, completar tarea, listar listas, guardar nota, buscar
  notas, RAM, disco, GPU, procesos, reiniciar servicio, vaciar caché.
- **Efecto real** — el `.md` escrito con su texto; la tarea tachada; la
  acción de sistema **pendiente y no ejecutada**.
- **Ninguna herramienta** — un saludo, "¿qué podés hacer?", y
  "agendame una reunión el martes" (fuera de alcance; el modelo ya
  alucinó un comando `meeting` una vez).
- **Pedir en vez de adivinar** — "agrega comprar leche" sin lista: se
  espera `herramienta: ninguna` más `respuesta_pregunta: true`.
- **No inventar** — preguntar por RAM y por el contenido de una nota
  guardada, con `fundamentada: true`.

## Estrategia de barrido

La grilla completa son 5 modelos × 4 variantes = 20 combinaciones;
con 20 casos × 5 repeticiones son 2000 corridas, del orden de 5 horas.

Se corre en dos etapas:

- **Etapa A** — los 5 modelos con la variante `baseline`. 500 corridas,
  ~1.2 h. Responde: *¿el problema es el modelo?*
- **Etapa B** — los 2 mejores de la Etapa A × las 3 variantes de
  chain-of-thought. 600 corridas, ~1.5 h. Responde: *¿razonar ayuda?*

Total ~2.7 h, y cada etapa contesta una pregunta distinta, así que se
puede frenar entre medio si la Etapa A ya fue concluyente.

**Riesgo aceptado:** un modelo mediocre con el prompt actual podría ser
excelente con chain-of-thought y quedar afuera de la Etapa B. Se
considera poco probable, y es barato de revisar después si algún número
queda raro.

## Manejo de errores

- **Ollama caído o modelo no descargado**: se detecta *antes* de
  empezar el barrido, verificando que cada modelo pedido exista.
  Fallar a las dos horas porque falta un modelo es inaceptable.
- **Timeout de una corrida**: se registra como fila con veredicto de
  timeout y se sigue. Una corrida colgada no puede tumbar el barrido.
- **Excepción dentro de un turno**: se registra con su traza en la fila
  y se sigue.
- **Caso mal formado**: falla al cargar, antes de la primera corrida.

Principio general: nada aborta un barrido de horas salvo que el usuario
lo corte.

## Testing

- **Unit tests de `checks.py`** sin Ollama, sobre historiales y estados
  de disco construidos a mano. Incluyen explícitamente los casos borde
  de la no-invención (redondeo aceptado, invención detectada).
- **Unit tests de `cases.py`**: un YAML válido carga; uno inválido
  falla con un mensaje que dice qué campo está mal.
- **Unit test de `variants.py`** para `cot_arg`: el esquema de la
  herramienta envuelta incluye `motivo` como obligatorio y conserva los
  argumentos originales. Sin invocar ningún modelo.
- **Unit test del runner** con un modelo de prueba (`TestModel` de
  pydantic-ai), verificando que una corrida produce su fila JSONL y que
  el reanudado saltea lo ya hecho.
- **Test de reporte**: un JSONL conocido produce las tasas esperadas.

El arnés se testea como cualquier otro componente. Los barridos reales
contra Ollama son corridas manuales, no tests.

## Entregables

1. El arnés con sus tests.
2. Los ~20 casos escritos.
3. **El baseline medido**: por primera vez un número en lugar de "a
   veces falla".
4. Reporte de la Etapa A (comparación de modelos), versionado en
   `docs/superpowers/evals/`.
5. Reporte de la Etapa B (variantes de chain-of-thought).
6. Una recomendación escrita **y aplicada**: promover a producción lo
   que haya ganado, o dejar constancia de que no ganó nada. Un reporte
   que nadie aplica es un reporte.
7. El `xfail` de `test_tasks_integration.py` resuelto: retirado si algo
   lo arregla, o con su razón actualizada a un número medido.

Es un resultado válido que ninguna variante le gane al baseline. En ese
caso la fase concluye que el chain-of-thought no ayuda en este montaje
y que el camino es cambiar de modelo — información que hoy no tenemos.

## Fuera de alcance

- **Guardrails** — fase siguiente, diseñados sobre estos datos.
- **Juez LLM**, local o externo.
- **Integración con CI** — no hay CI en este proyecto y montarlo no es
  lo que esta fase necesita.
- **Fine-tuning** de cualquier modelo.
- Cambios de funcionalidad de cara al usuario.

## Pendiente registrado para fases posteriores

**Guardrails en runtime**, informados por esta medición. Candidatos que
ya se anticipan, a confirmar con los datos: rechazar llamadas a
herramientas inexistentes antes de intentar ejecutarlas (hoy ya lo
cubre el registro), reintentar una vez cuando el modelo omite un
argumento obligatorio en vez de devolverle `missing_argument` al
usuario, y validar que la respuesta no contenga cifras que ninguna
herramienta devolvió — este último es exactamente el chequeo
`fundamentada` de esta fase, promovido de instrumento de medición a
defensa en producción.
