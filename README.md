# Asistente Mikha

Asistente personal que vive en esta máquina. Backend FastAPI + agente
PydanticAI sobre Ollama, con tool-calling de solo lectura, acciones
controladas por confirmación explícita, memoria persistente sobre un
vault de Obsidian, y trazas OpenTelemetry hacia Phoenix.

## Requisitos

- Python 3.11+
- Ollama corriendo localmente con un modelo con alias `default` y el
  modelo de embeddings `nomic-embed-text`. El modelo recomendado es
  `qwen3:8b` (`ollama pull qwen3:8b && ollama cp qwen3:8b default`): en
  la Fase 5 fue el unico que acerto todos los casos de tool-calling. Mikha
  le apaga el razonamiento para responder en ~4s en lugar de ~17s; ver
  `docs/superpowers/evals/2026-09-16-fase5-resultados.md`. El alias se
  puede apuntar a otro modelo sin tocar codigo. Embeddings:
  `ollama pull nomic-embed-text`.
- En esta maquina Ollama corre como servicio de sistema y guarda los
  modelos en `/var/lib/ollama`: `sudo systemctl enable --now ollama`. Un
  `ollama serve` lanzado a mano como tu usuario lee `~/.ollama` y no ve
  esos modelos.
- (Opcional, para ver trazas) `pip install arize-phoenix` y `phoenix serve`
- (Opcional, para correr con Docker) Docker + Docker Compose
- (Solo para desarrollar el frontend) Node 22+ — el build de
  produccion lo hace el Dockerfile por su cuenta

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Correr el backend (nativo)

```bash
uvicorn asistente_mikha.main:app --reload
```

## Correr con Docker (backend + Phoenix)

Ollama se queda corriendo nativo en el host (por la aceleración GPU).
El backend y Phoenix corren en contenedores:

```bash
docker compose up --build
```

Esto expone el backend en `http://localhost:8000` (igual que corriendo
`uvicorn` nativo) y Phoenix en `http://localhost:6006`. El vault de
Obsidian se monta desde `~/Obsidian/Mikha` — las notas que Mikha guarde
desde el contenedor son visibles inmediatamente en la app de Obsidian
del host.

**Importante:** para que el contenedor del backend alcance a Ollama,
este debe escuchar en todas las interfaces, no solo en `localhost`:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

(Esto también expone Ollama a tu red local sin autenticación — aceptable
en una red doméstica de confianza, pero tenlo presente.)

El CLI (`mikha`) sigue corriendo nativo sin cambios, sin importar si el
backend está en Docker o no.

## Correr la interfaz de tracing (opcional, si no usas Docker)

```bash
phoenix serve
# UI en http://localhost:6006
```

## Correr el CLI

```bash
mikha
# o: python -m asistente_mikha.cli
```

## Memoria (Obsidian)

Pídele a Mikha que guarde o busque notas ("Guarda una nota titulada...",
"Busca en mis notas sobre..."). Las notas se guardan como archivos
Markdown en `~/Obsidian/Mikha` (o la ruta en `MIKHA_VAULT_PATH`), listos
para abrir directamente en la app de Obsidian.

También puedes pedirle que edite o elimine una nota. Nunca lo hace de
inmediato: deja el cambio pendiente hasta que lo confirmes.

## Tareas

Pídele a Mikha que agregue, liste o complete tareas, o que te diga qué
listas de tareas tenés ("Agrega la tarea... a mi lista de...", "Qué
tareas tengo en mi lista de...", "Marca como hecha la tarea..."). Las
listas se organizan por tema o meta (ej. "Casa", "Idea de negocio") y
se guardan como checkboxes de Markdown en `<vault>/Tareas/<lista>.md`.
Editar o eliminar una tarea también requiere confirmación explícita.
Decile siempre a qué lista va la tarea. Si no lo decís, el modelo
actual inventa una lista en vez de preguntar: es el único caso que se
pierde al apagarle el razonamiento para que responda rápido (ver la
sección de evals). Hay un guardrail pendiente para atraparlo.

## Configuración por variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Dónde vive Ollama |
| `PHOENIX_ENDPOINT` | `http://localhost:6006/v1/traces` | Colector de trazas |
| `MIKHA_VAULT_PATH` | `~/Obsidian/Mikha` | Vault de notas |

## Tests

```bash
pytest -m "not integration"   # rápidos, no requieren Ollama
pytest -m integration         # requieren `ollama serve` con los modelos 'default' y 'nomic-embed-text'
pytest                        # todo

cd frontend && npm test       # tests del dashboard (vitest)
```

GitHub Actions (`.github/workflows/ci.yml`) corre en cada PR y en cada push
a `main` los tests rápidos de Python, el lint y los tests del frontend. Las
pruebas `integration` no corren en CI porque requieren Ollama.

## Interfaz web

El dashboard se sirve desde el mismo backend en `http://localhost:8000`:
el chat con streaming, el orbe que vibra mientras el asistente responde,
y paneles con el estado de la maquina, tus tareas, tus notas recientes y
las acciones esperando confirmacion. Los paneles de tareas y notas
tienen botones "editar" y "eliminar": solo proponen el cambio, que queda
en "por confirmar" hasta que lo apruebes.

Para desarrollar el frontend con recarga en vivo, con el backend
corriendo aparte:

```bash
cd frontend
npm install
npm run dev
```

Vite levanta en otro puerto y hace proxy de la API al backend en el 8000.
El build de produccion no hay que correrlo a mano: el Dockerfile tiene una
etapa de Node que lo hace y copia el resultado a la imagen final.

## Evals

El arnés mide qué tan confiable es el tool-calling del agente, por
dimensión y como tasa sobre repeticiones:

```bash
mikha-eval correr --modelos default --variantes baseline --repeticiones 5 \
  --salida evals/resultados/corrida.jsonl
mikha-eval reporte evals/resultados/corrida.jsonl --por caso
```

Los casos están en `evals/casos/*.yaml`. El barrido es reanudable: si se
corta, el mismo comando saltea lo ya hecho.

## Próximas fases

Ver `docs/superpowers/specs/` para el contexto completo del proyecto
(evals/guardrails, calendario/reuniones).
