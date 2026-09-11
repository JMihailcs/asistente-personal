# Asistente Mikha — Fase 4: Interfaz web

## Contexto

Cuarta fase del asistente personal (Fase 1: diagnóstico + acciones
confirmadas, Fase 2: memoria sobre Obsidian + Docker, Fase 3: listas de
tareas). Agrega un dashboard web con el chat, el estado de la máquina y
la memoria/tareas visibles de un vistazo.

El roadmap se reordenó a pedido del usuario: **Fase 4 interfaz web →
Fase 5 evals y guardrails → Fase 6 calendario/reuniones**. El motivo es
que la interfaz web da uso diario inmediato, y medir la fiabilidad del
modelo (Fase 5) antes de agregar otro dominio de herramientas evita
apilar calendario encima de un problema sin medir.

### Referencia visual

El usuario eligió como referencia el diseño **OPTIMIND** de Anton
Skvortsov (@anton_skv), adaptado a oscuro. Frames extraídos para
referencia durante la implementación. Lo que se toma del original:

- Superficies de muy bajo contraste, definidas por un borde de 1px y
  sombra difusa, no por relleno.
- **Un solo acento (ámbar) y siempre como luz emitida.**
- Titulares en grotesk ancha mayúscula con tracking; micro-etiquetas
  mono; mucho aire.

Lo que **no** se toma: la cantidad de espacio vacío de una landing page,
incompatible con un dashboard denso.

### La pieza central: el orbe

Lo que más le interesa al usuario del original es la animación 3D
principal. En Mikha deja de ser decoración y pasa a ser **la presencia
del asistente**: vibra cuando responde. El usuario anticipa que en algún
momento la interacción será por voz, así que el orbe se diseña desde
ahora manejado por un **`level` de 0 a 1**, hoy alimentado por la
llegada de tokens y mañana por la amplitud del audio, sin rediseñarlo.

## Decisiones

| Aspecto | Decisión |
|---|---|
| Forma | Dashboard con chat incluido (no solo chat) |
| Tema | Oscuro, adaptación del original claro |
| Frontend | React + Vite (elegido por valor de portafolio sobre la alternativa vanilla) |
| Servido por | El mismo FastAPI sirve el `dist/` compilado — mismo origen, sin CORS, un solo contenedor |
| Docker | Dockerfile multi-stage: etapa Node que buildea → copia `dist` a la imagen Python. El runtime sigue siendo un contenedor |
| Streaming | SSE con tokens, endpoint nuevo. Es el mismo canal que después sirve para voz |
| Fuentes | Self-hosted en el build, no CDN — el resto del proyecto funciona sin internet |
| Paneles | Sistema (RAM/disco/GPU), tareas, notas recientes, acciones por confirmar |

## Arquitectura

```
Frontend (React + Vite)                Backend (FastAPI)
┌────────────────────────────┐
│ Orb (Three.js)             │◄─ level ─ POST /chat/stream   (SSE, nuevo)
│  idle/thinking/speaking/   │
│  awaiting                  │
├────────────────────────────┤
│ Chat                       │◄────────── mismo SSE
├────────────────────────────┤
│ Paneles                    │
│  Sistema                   │◄─ poll 5s ─ GET /system         (nuevo)
│  Tareas                    │◄─ al `done` GET /tasks          (nuevo)
│  Notas recientes           │◄─ de cada  ─ GET /notes/recent   (nuevo)
│  Por confirmar             │◄─ turno  ── GET /actions/pending (nuevo)
└────────────────────────────┘            POST /confirm/{id}   (ya existe)
     build → dist/ ── servido como estáticos por el mismo FastAPI
```

Los 4 endpoints de lectura **no agregan lógica de negocio**: exponen por
HTTP funciones puras ya construidas y probadas (`get_ram_usage`,
`get_disk_usage`, `get_gpu_status`, `list_task_lists`, `list_tasks`,
`list_vault_notes`, y el `PendingActionStore`).

## Sistema de diseño

| Token | Valor | Uso |
|---|---|---|
| `--canvas` | `#141312` | Fondo, carbón cálido — nunca negro puro |
| `--surface` | `#1C1A18` | Tarjetas, apenas por encima del fondo |
| `--hairline` | `#2A2724` | Bordes de 1px: lo que define una tarjeta |
| `--text` | `#EDEAE6` | Texto principal |
| `--muted` | `#8A837C` | Cuerpo secundario y micro-etiquetas |
| `--amber` | `#F2A03D` | El único color, siempre como luz emitida |
| `--amber-hot` | `#FFD9A0` | Núcleo de glows |

**Regla heredada del original, a preservar literal:** el ámbar aparece
solo como luz y significa una sola cosa — *esto está vivo o te
necesita*. El orbe respondiendo, la GPU bajo carga, la acción esperando
confirmación. Nada más lleva color.

Tipografía (las tres self-hosted en el build, licencia SIL OFL):

| Rol | Fuente | Uso |
|---|---|---|
| Titulares | **Space Grotesk** | Mayúsculas con tracking amplio; es el grotesk técnico más cercano al original |
| Cuerpo | **Inter** | Texto de chat y descripciones |
| Micro-etiquetas | **JetBrains Mono** | `RAM`, `GPU`, timestamps, duraciones, contadores |

## Layout

```
┌──────────────────────────────────────────────────────────┐
│  MIKHA                                    ● 06:11:22     │
├────────────────────────────────────┬─────────────────────┤
│                                    │  SISTEMA            │
│              ◉  (orbe)             │  RAM / GPU / DISCO  │
│                                    ├─────────────────────┤
├────────────────────────────────────┤  POR CONFIRMAR      │
│  chat + métricas por turno         ├─────────────────────┤
│  ┌──────────────────────────────┐  │  TAREAS             │
│  │ input                        │  ├─────────────────────┤
│  └──────────────────────────────┘  │  NOTAS RECIENTES    │
└────────────────────────────────────┴─────────────────────┘
```

El panel "por confirmar" solo existe cuando hay algo pendiente, y es la
única parte de la UI que interrumpe visualmente — porque es la única que
requiere al usuario.

## Componentes

### Orbe (`orb.js`, Three.js, sin React adentro)

Sistema de partículas sobre una esfera, desplazadas por ruido,
renderizadas con blending aditivo. API: `createOrb(canvas) → {
setState, setLevel, dispose }`. El wrapper de React es delgado; la
lógica de animación no conoce React. Eso es lo que hace que el cambio a
voz sea de una línea del lado de quien llama.

Estados:
- `idle` — respiración lenta, desplazamiento bajo, tenue
- `thinking` — pulso más rápido y tenso, sin `level` aún
- `speaking` — desplazamiento y brillo escalan con `level`
- `awaiting` — ámbar sostenido y brillante, lento

`level` se calcula en la capa de chat como seguidor de envolvente: cada
token empuja (`level = min(1, level + k)`), un loop de animación decae
(`level *= 0.92` por frame).

Requisitos no opcionales: tope de partículas, respetar
`prefers-reduced-motion`, y pausar el loop cuando la pestaña no está
visible (si no, consume GPU de fondo indefinidamente).

### Chat

Consume el SSE con dos tipos de evento: `token` (delta de texto) y
`done` (payload final con `pending_action_ids`, `duration_seconds`,
`queried_at`). Renderiza el texto en streaming y luego la línea de
métricas. Al recibir `done`, dispara el refetch de los paneles de
tareas, notas y confirmaciones.

### Paneles

`SystemPanel` hace polling cada 5s (llamadas locales baratas a psutil);
los otros cargan al montar y tras cada `done` — que es cuando pueden
haber cambiado. Los botones de confirmación usan el `/confirm/{id}` que
ya existe.

### Backend

`POST /chat/stream` debe preservar el ciclo de vida del turno actual:
`start_turn_tracking()` → stream → `collect_turn_actions()` al cerrar,
más el span de OpenTelemetry equivalente al de `run_turn`. El
`StaticFiles` se monta al final, para no tapar las rutas de API.

## Manejo de errores

- **SSE cortado a mitad**: el mensaje queda marcado incompleto y el orbe
  vuelve a `idle`. Nunca una respuesta truncada que parezca terminada.
- **Backend caído**: los paneles muestran estado desconectado, **no
  ceros** — un "0 GB de RAM" miente, un "sin conexión" no.
- **Sin `rocm-smi`**: el panel de GPU lo informa (la función ya devuelve
  `{available: false, reason}`), en vez de dibujar una barra vacía.
- **Confirmar una acción expirada**: el endpoint ya devuelve 409; la UI
  lo informa y recarga.

## Testing

- **Backend**: pytest para los 4 endpoints de lectura y para el SSE
  (secuencia de eventos y que el evento final traiga los
  `pending_action_ids`).
- **Frontend**: Vitest + Testing Library para el manejo del stream (con
  `fetch` mockeado) y el render de paneles. El orbe recibe un smoke test
  de montaje/destrucción sin dejar el loop colgado — no un test visual.

  Nota: el cliente consume el SSE con `fetch()` +
  `response.body.getReader()` y parseo manual, **no con `EventSource`**,
  porque `EventSource` solo hace GET y el chat manda un cuerpo por POST.
  Detectado al escribir el plan de implementación.
- Sin automatización de navegador en esta fase.

## Pendiente registrado para fases posteriores

**Chain-of-thought en el modelo** — pedido explícitamente por el usuario
durante esta fase, para "después". Encaja en la Fase 5 (evals): el
problema central no resuelto del proyecto es que el modelo local invoca
herramientas de forma poco confiable (colapsa a partir de ~4-5
herramientas simultáneas; omite argumentos obligatorios con ciertas
frases), y hacerlo razonar antes de responder es una mitigación
plausible que todavía no se probó. Debe medirse ahí junto con modelos
alternativos, no aplicarse a ciegas. El test marcado `xfail` en
`tests/test_tasks_integration.py` es el termómetro existente.
