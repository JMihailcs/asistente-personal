# Asistente Mikha

Asistente personal que vive en esta máquina. Backend FastAPI + agente
PydanticAI sobre Ollama, con tool-calling de solo lectura, acciones
controladas por confirmación explícita, memoria persistente sobre un
vault de Obsidian, y trazas OpenTelemetry hacia Phoenix.

## Requisitos

- Python 3.11+
- Ollama corriendo localmente con un modelo con alias `default` (ver
  `ollama list` / `ollama cp <modelo> default`) y el modelo de embeddings
  `nomic-embed-text` (`ollama pull nomic-embed-text`)
- (Opcional, para ver trazas) `pip install arize-phoenix` y `phoenix serve`
- (Opcional, para correr con Docker) Docker + Docker Compose

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
```

## Próximas fases

Ver `docs/superpowers/specs/` para el contexto completo del proyecto
(gestión de tareas, calendario, interfaz web, evals/guardrails).
