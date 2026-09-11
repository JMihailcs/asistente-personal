# Asistente Mikha — Diseño general y Fase 1: Núcleo del agente

## Contexto y propósito

Proyecto de portafolio y aprendizaje: un asistente local de diagnóstico de
máquina, construido con patrones de arquitectura de nivel empresarial
(RAG, tool-calling/agentes, observabilidad, evals/guardrails), usando esta
máquina como caso de estudio real. Doble audiencia: aprendizaje profundo
propio y presentación a terceros (portafolio técnico).

Hardware de referencia: CPU Intel Xeon E5-2678 v3 (12c/24t), 32GB RAM,
GPU AMD Radeon RX 5500 con 8GB VRAM, sin Docker disponible por preferencia
del usuario (todo corre nativo). LLM local vía Ollama; modelo por defecto
`mistral-nemo:12b` (alias `default`), elegido porque es el modelo más
grande que corre casi enteramente en la VRAM disponible sin degradación
severa de velocidad (~18 tok/s vs ~6.7 tok/s de un modelo de 14B que ya
no cabe en 8GB de VRAM).

## Fases del proyecto

1. **Núcleo del agente** (este documento) — backend API, agente con
   tool-calling, cliente CLI, observabilidad instrumentada desde el
   inicio.
2. **RAG** — indexado de documentación/config/logs de la máquina,
   herramienta de búsqueda semántica para el agente.
3. **Interfaz web** — chat en navegador consumiendo la misma API que el
   CLI.
4. **Evals y guardrails** — arnés de pruebas de calidad, grounding y
   seguridad sobre todo el sistema construido en las fases anteriores.

Cada fase tiene su propio ciclo spec → plan → implementación. Este
documento cubre únicamente la Fase 1.

## Decisiones de stack (Fase 1)

| Área | Elección | Alternativas consideradas y por qué no |
|---|---|---|
| Lenguaje/backend | Python + FastAPI | — |
| Orquestación del agente | PydanticAI | LangGraph (sobra para un solo agente, curva de aprendizaje alta); Smolagents (ejecuta código arbitrario, requiere sandboxing que no encaja con el caso de uso de diagnóstico real) |
| LLM | Ollama, modelo `default` (mistral-nemo:12b) | — |
| Observabilidad | OpenTelemetry (convenciones `gen_ai.*`) + Arize Phoenix local | Langfuse self-hosted (requiere Postgres+ClickHouse+Redis+worker, demasiado pesado para la RAM disponible y para "nativo sin Docker") |
| Despliegue | Proceso único (`uvicorn`), sin contenedores | Gateway + worker separado con cola de mensajes (sobre-ingeniería para un solo usuario) |

## Arquitectura

```
CLI client ─┐
            │  HTTP/JSON
Web (Fase3)─┘
            ▼
     FastAPI app (capa API: rutas, validación Pydantic)
            ▼
     Agente (PydanticAI) ↔ Ollama
            ▼
     Registro de herramientas + capa de confirmación
            ▼
     Comandos reales del sistema (free, ps, df, systemctl, etc.)

OpenTelemetry instrumenta cada capa → Phoenix (trace viewer local)
```

Proceso único Python. El agente vive en memoria durante la vida del
proceso; cada request de chat es un turno de conversación que el agente
resuelve pudiendo llamar 0, 1 o varias herramientas antes de responder.
No hay persistencia de conversación en Fase 1 (se puede añadir después
si hace falta).

## Componentes

### Capa API (FastAPI)

Endpoints:
- `POST /chat` — envía un mensaje de usuario, recibe la respuesta del
  agente o una petición de confirmación pendiente.
- `POST /confirm/{action_id}` — aprueba o rechaza una acción controlada
  pendiente.
- `GET /health` — chequeo de salud del proceso y de la conexión a
  Ollama.

Validación de entrada/salida con modelos Pydantic — los mismos modelos
que usa el agente internamente, sin capas de traducción redundantes.

### Agente (PydanticAI)

Mantiene el historial de conversación por sesión (en memoria, indexado
por un ID de sesión simple). En cada turno decide si responde
directamente o invoca una herramienta, usando el schema de
function-calling que PydanticAI genera automáticamente a partir de las
funciones Python tipadas del registro de herramientas.

### Registro de herramientas + confirmación

Cada herramienta es una función Python tipada con un decorador que
declara su nivel de riesgo:

- `@tool(risk="read")` — diagnóstico de solo lectura (ej.
  `get_ram_usage`, `get_gpu_status`, `list_processes`). Se ejecuta de
  inmediato, sin restricciones.
- `@tool(risk="confirm")` — acciones que modifican el sistema (ej.
  `restart_service`, `clear_cache`). No se ejecutan solas: el agente
  devuelve una "acción propuesta" (con un `action_id`) al cliente, que
  debe llamar explícitamente a `POST /confirm/{action_id}` antes de que
  el comando corra de verdad.

El registro de herramientas es la única fuente de verdad: una
herramienta no registrada no existe para el LLM. No hay ejecución de
shell arbitrario ni interpretación de texto libre como comando —
este es el guardrail central de la Fase 1.

### Observabilidad (OpenTelemetry + Phoenix)

Cada turno de conversación, cada llamada a herramienta y cada llamada
al LLM genera un span con atributos `gen_ai.*` (modelo, tokens,
latencia, nombre de herramienta, resultado). Phoenix corre como
proceso local y muestra el árbol de spans completo de cada
interacción.

## Manejo de errores

- **Falla de ejecución de herramienta** (comando no encontrado, permiso
  denegado, etc.): se captura, se registra como span de error en la
  traza, y se devuelve al LLM como resultado de la herramienta — no
  como excepción no controlada. El agente decide cómo comunicarlo al
  usuario.
- **Confirmación expirada o rechazada**: las acciones pendientes tienen
  un TTL corto (~5 min); si nadie confirma se descartan. Un rechazo
  explícito se pasa al agente como resultado de la herramienta.
- **Ollama no responde**: la API devuelve un 503 claro tras 1-2
  reintentos, sin colgar el proceso.
- **Herramienta inexistente/alucinada**: se rechaza antes de intentar
  ejecutar nada, sin fallback a interpretación de texto libre.

## Testing

- **Unit tests** por herramienta, aislados; las de `risk="read"`
  corren contra la máquina real (son seguras), las de `risk="confirm"`
  se testean con el comando real mockeado.
- **Test de la capa de confirmación**: verificar que una herramienta
  `risk="confirm"` nunca se ejecuta sin pasar por `/confirm`, incluso
  si el LLM "la pide" directamente — es el test de seguridad más
  importante de esta fase.
- **Smoke test end-to-end** contra Ollama real: un par de
  conversaciones completas (mensaje → tool call → respuesta) para
  confirmar que el flujo íntegro funciona.

La Fase 4 construye sobre esta base un arnés de evals más exhaustivo;
en Fase 1 el testing solo confirma que el sistema no está roto.
