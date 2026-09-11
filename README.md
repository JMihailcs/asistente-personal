# Asistente Mikha — Fase 1: Núcleo del agente

Asistente local de diagnóstico de máquina. Backend FastAPI + agente
PydanticAI sobre Ollama, con tool-calling de solo lectura, acciones
controladas por confirmación explícita, y trazas OpenTelemetry hacia
Phoenix.

## Requisitos

- Python 3.11+
- Ollama corriendo localmente con un modelo con alias `default` (ver
  `ollama list` / `ollama cp <modelo> default`)
- (Opcional, para ver trazas) `pip install arize-phoenix` y `phoenix serve`

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Correr el backend

```bash
uvicorn asistente_mikha.main:app --reload
```

## Correr la interfaz de tracing (opcional)

```bash
phoenix serve
# UI en http://localhost:6006
```

## Correr el CLI

```bash
mikha
# o: python -m asistente_mikha.cli
```

## Tests

```bash
pytest -m "not integration"   # rápidos, no requieren Ollama
pytest -m integration         # requieren `ollama serve` con el modelo 'default'
pytest                        # todo
```

## Próximas fases

Ver `docs/superpowers/specs/2026-09-10-agente-nucleo-design.md` para el
contexto completo del proyecto (RAG, interfaz web, evals/guardrails).
