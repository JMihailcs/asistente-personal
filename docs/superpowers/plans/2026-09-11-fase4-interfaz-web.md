# Fase 4 — Interfaz Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un dashboard web oscuro con el chat en streaming, el orbe 3D como presencia del asistente, y paneles de estado de máquina, tareas, notas y confirmaciones pendientes.

**Architecture:** Backend FastAPI gana un endpoint SSE (`/chat/stream`) y cuatro endpoints de lectura que exponen funciones puras ya existentes. Frontend React + Vite compilado a estáticos y servido por el mismo FastAPI (mismo origen, un solo contenedor, Dockerfile multi-stage). El orbe es un módulo Three.js sin React adentro, manejado por `state` + `level` (0..1).

**Tech Stack:** FastAPI `StreamingResponse` (SSE a mano, sin dependencia nueva de Python), React 18 + Vite, Three.js, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-11-fase4-interfaz-web-design.md`

## Global Constraints

- **El ámbar (`#F2A03D`) es el único color y siempre significa "esto está vivo o te necesita"**: el orbe respondiendo, una métrica bajo carga, una acción esperando confirmación, el ítem activo. Nada más lleva color.
- Tokens de diseño exactos: `--canvas #141312`, `--surface #1C1A18`, `--hairline #2A2724`, `--text #EDEAE6`, `--muted #8A837C`, `--amber #F2A03D`, `--amber-hot #FFD9A0`.
- Fuentes self-hosted en el build (Space Grotesk titulares, Inter cuerpo, JetBrains Mono micro-etiquetas). **Nunca cargar fuentes desde un CDN** — el proyecto funciona sin internet.
- Los endpoints de lectura **no agregan lógica de negocio**: llaman funciones puras ya existentes y probadas.
- El endpoint de streaming debe preservar el ciclo de vida del turno: `start_turn_tracking()` → stream → `collect_turn_actions()`, más el span de OpenTelemetry.
- Ante backend caído, los paneles muestran estado desconectado, **nunca ceros**.
- El orbe debe respetar `prefers-reduced-motion` y pausar su loop cuando la pestaña no está visible.

**Desviación del spec, ya decidida:** el spec dice "EventSource mockeado" para los tests del stream. `EventSource` solo hace GET y nuestro chat manda un cuerpo por POST, así que el cliente usa `fetch()` + `response.body.getReader()` con parseo SSE manual, y los tests mockean `fetch`.

---

## Task 1: Streaming en el agente

**Files:**
- Modify: `src/asistente_mikha/agent.py`
- Test: `tests/test_agent_stream_integration.py`

**Interfaces:**
- Consumes: `start_turn_tracking`, `collect_turn_actions` (ya existentes), `get_tracer`.
- Produces: `run_turn_stream(session_id: str, message: str) -> AsyncIterator[str | AgentTurnResult]` — un generador asíncrono que emite `str` por cada delta de texto y, como último elemento, un `AgentTurnResult` con la respuesta completa y los `pending_action_ids`.

- [ ] **Step 1: Escribir el test de integración (falla primero)**

`tests/test_agent_stream_integration.py`:
```python
import pytest

from asistente_mikha.agent import (
    AgentTurnResult,
    reset_sessions_for_tests,
    run_turn_stream,
)


@pytest.fixture(autouse=True)
def _clean_sessions():
    reset_sessions_for_tests()
    yield
    reset_sessions_for_tests()


@pytest.mark.integration
async def test_run_turn_stream_emits_deltas_then_result():
    deltas: list[str] = []
    final: AgentTurnResult | None = None

    async for item in run_turn_stream("stream-test", "Decime hola en una frase corta."):
        if isinstance(item, AgentTurnResult):
            final = item
        else:
            deltas.append(item)

    assert deltas, "se esperaba al menos un delta de texto"
    assert final is not None, "se esperaba un AgentTurnResult como ultimo elemento"
    assert final.reply == "".join(deltas)
    assert isinstance(final.pending_action_ids, list)
```

Run: `pytest tests/test_agent_stream_integration.py -v -m integration`
Expected: FAIL con `ImportError: cannot import name 'run_turn_stream'`.

- [ ] **Step 2: Implementar**

Agregar al final de `src/asistente_mikha/agent.py` (y agregar `from typing import AsyncIterator` arriba):

```python
async def run_turn_stream(session_id: str, message: str) -> AsyncIterator[str | AgentTurnResult]:
    """Emite deltas de texto y, como ultimo elemento, el AgentTurnResult completo."""
    start_turn_tracking()
    session = get_or_create_session(session_id)
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.turn.stream") as span:
        span.set_attribute("gen_ai.request.model", DEFAULT_MODEL_NAME)
        span.set_attribute("mikha.session_id", session_id)
        parts: list[str] = []
        async with session.agent.run_stream(
            message, message_history=session.history
        ) as result:
            async for delta in result.stream_text(delta=True):
                parts.append(delta)
                yield delta
            session.history = result.all_messages()
        reply = "".join(parts)
        span.set_attribute("gen_ai.response.text_length", len(reply))
    yield AgentTurnResult(reply=reply, pending_action_ids=collect_turn_actions())
```

- [ ] **Step 3: Verificar (con Ollama corriendo)**

Run: `pytest tests/test_agent_stream_integration.py -v -m integration`
Expected: 1 passed. Si el modelo no responde de forma util, revisar que `ollama serve` este activo con el modelo `default`; no debilitar las aserciones.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/agent.py tests/test_agent_stream_integration.py
git commit -m "feat: streaming de tokens en el agente"
```

---

## Task 2: Listar acciones pendientes + endpoints de lectura

**Files:**
- Modify: `src/asistente_mikha/confirmation.py`
- Modify: `src/asistente_mikha/api/models.py`
- Modify: `src/asistente_mikha/api/routes.py`
- Test: `tests/test_confirmation.py` (ampliar)
- Test: `tests/test_api_panels.py`

**Interfaces:**
- Consumes: `get_ram_usage`, `get_disk_usage`, `get_gpu_status` de `asistente_mikha.tools.diagnostics`; `list_task_lists`, `list_tasks` de `asistente_mikha.memory.tasks`; `list_vault_notes` de `asistente_mikha.memory.vault`; `get_vault_path` de `asistente_mikha.config`.
- Produces: `PendingActionStore.list_pending() -> list[PendingAction]`; endpoints `GET /system`, `GET /tasks`, `GET /notes/recent`, `GET /actions/pending`.

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar a `tests/test_confirmation.py`:
```python
def test_list_pending_returns_only_pending_actions():
    store = PendingActionStore()
    register_implementation("dummy_tool", lambda: {"ok": True})
    a = store.create("dummy_tool", {})
    b = store.create("dummy_tool", {})
    store.reject(b.action_id)

    pending = store.list_pending()

    assert [p.action_id for p in pending] == [a.action_id]


def test_list_pending_excludes_expired():
    current = {"t": 1000.0}
    store = PendingActionStore(ttl_seconds=5.0, clock=lambda: current["t"])
    store.create("dummy_tool", {})
    current["t"] += 10.0

    assert store.list_pending() == []
```

`tests/test_api_panels.py`:
```python
import pytest
from fastapi.testclient import TestClient

from asistente_mikha.confirmation import (
    get_default_store,
    register_implementation,
    reset_default_store_for_tests,
)
from asistente_mikha.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.reset_indexer_for_tests()
    reset_default_store_for_tests()
    with TestClient(app) as test_client:
        yield test_client
    memory_tools.reset_indexer_for_tests()
    reset_default_store_for_tests()


def test_system_endpoint_returns_all_three_readings(client):
    body = client.get("/system").json()

    assert body["ram"]["total_gb"] > 0
    assert body["disk"]["path"] == "/"
    assert "available" in body["gpu"]


def test_tasks_endpoint_returns_lists_with_items(client):
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")

    body = client.get("/tasks").json()

    assert body["lists"] == [
        {"name": "Casa", "tasks": [{"text": "lavar los platos", "done": False}]}
    ]


def test_tasks_endpoint_empty_when_no_lists(client):
    assert client.get("/tasks").json() == {"lists": []}


def test_notes_recent_returns_newest_first(client, tmp_path):
    from asistente_mikha.memory.vault import write_note

    write_note(tmp_path, "Vieja", "contenido viejo")
    write_note(tmp_path, "Nueva", "contenido nuevo")

    body = client.get("/notes/recent").json()

    titles = [n["title"] for n in body["notes"]]
    assert set(titles) == {"Vieja", "Nueva"}
    assert len(body["notes"]) <= 5


def test_pending_actions_endpoint(client):
    register_implementation("dummy_tool", lambda: {"ok": True})
    action = get_default_store().create("dummy_tool", {"service_name": "wireplumber"})

    body = client.get("/actions/pending").json()

    assert body["actions"] == [
        {
            "action_id": action.action_id,
            "tool_name": "dummy_tool",
            "kwargs": {"service_name": "wireplumber"},
        }
    ]
```

Run: `pytest tests/test_confirmation.py tests/test_api_panels.py -v`
Expected: FAIL — `AttributeError: 'PendingActionStore' object has no attribute 'list_pending'` y 404 en los endpoints nuevos.

- [ ] **Step 2: Agregar `list_pending` al store**

En `src/asistente_mikha/confirmation.py`, dentro de `PendingActionStore`, después de `get`:

```python
    def list_pending(self) -> list[PendingAction]:
        return [
            action
            for action_id in list(self._actions)
            if (action := self.get(action_id)) is not None
            and action.status == ActionStatus.PENDING
        ]
```

- [ ] **Step 3: Agregar los modelos de respuesta**

En `src/asistente_mikha/api/models.py`:

```python
class SystemResponse(BaseModel):
    ram: dict[str, Any]
    disk: dict[str, Any]
    gpu: dict[str, Any]


class TaskItemResponse(BaseModel):
    text: str
    done: bool


class TaskListResponse(BaseModel):
    name: str
    tasks: list[TaskItemResponse]


class TasksResponse(BaseModel):
    lists: list[TaskListResponse]


class NoteResponse(BaseModel):
    title: str
    created: str
    excerpt: str


class NotesResponse(BaseModel):
    notes: list[NoteResponse]


class PendingActionResponse(BaseModel):
    action_id: str
    tool_name: str
    kwargs: dict[str, Any]


class PendingActionsResponse(BaseModel):
    actions: list[PendingActionResponse]
```

- [ ] **Step 4: Agregar los endpoints**

En `src/asistente_mikha/api/routes.py`, agregar los imports necesarios y los cuatro endpoints:

```python
from asistente_mikha.config import get_vault_path
from asistente_mikha.memory.tasks import list_task_lists, list_tasks
from asistente_mikha.memory.vault import list_vault_notes
from asistente_mikha.tools.diagnostics import (
    get_disk_usage,
    get_gpu_status,
    get_ram_usage,
)
```

```python
RECENT_NOTES_LIMIT = 5


@router.get("/system", response_model=SystemResponse)
async def system() -> SystemResponse:
    return SystemResponse(
        ram=get_ram_usage(), disk=get_disk_usage("/"), gpu=get_gpu_status()
    )


@router.get("/tasks", response_model=TasksResponse)
async def all_tasks() -> TasksResponse:
    vault_path = get_vault_path()
    lists = []
    for name in list_task_lists(vault_path):
        task_list = list_tasks(vault_path, name)
        if task_list is None:
            continue
        lists.append(
            TaskListResponse(
                name=task_list.name,
                tasks=[
                    TaskItemResponse(text=item.text, done=item.done)
                    for item in task_list.items
                ],
            )
        )
    return TasksResponse(lists=lists)


@router.get("/notes/recent", response_model=NotesResponse)
async def recent_notes() -> NotesResponse:
    notes = list_vault_notes(get_vault_path())
    notes.sort(key=lambda n: n.created, reverse=True)
    return NotesResponse(
        notes=[
            NoteResponse(title=n.title, created=n.created, excerpt=n.content[:160])
            for n in notes[:RECENT_NOTES_LIMIT]
        ]
    )


@router.get("/actions/pending", response_model=PendingActionsResponse)
async def pending_actions() -> PendingActionsResponse:
    return PendingActionsResponse(
        actions=[
            PendingActionResponse(
                action_id=a.action_id, tool_name=a.tool_name, kwargs=a.kwargs
            )
            for a in get_default_store().list_pending()
        ]
    )
```

- [ ] **Step 5: Verificar**

Run: `pytest tests/test_confirmation.py tests/test_api_panels.py -v`
Expected: todos pasan.

- [ ] **Step 6: Commit**

```bash
git add src/asistente_mikha/confirmation.py src/asistente_mikha/api tests/test_confirmation.py tests/test_api_panels.py
git commit -m "feat: endpoints de lectura para los paneles del dashboard"
```

---

## Task 3: Endpoint SSE `/chat/stream`

**Files:**
- Modify: `src/asistente_mikha/api/routes.py`
- Test: `tests/test_api_stream.py`

**Interfaces:**
- Consumes: `run_turn_stream`, `AgentTurnResult` (Task 1).
- Produces: `POST /chat/stream` → `text/event-stream` con eventos `token` (`{"text": "..."}`) y un evento final `done` (`{"reply", "pending_action_ids", "duration_seconds", "queried_at"}`).

- [ ] **Step 1: Escribir el test (falla primero)**

`tests/test_api_stream.py`:
```python
import json

import pytest
from fastapi.testclient import TestClient

from asistente_mikha.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.reset_indexer_for_tests()

    async def fake_stream(session_id: str, message: str):
        from asistente_mikha.agent import AgentTurnResult

        yield "Hola "
        yield "mundo"
        yield AgentTurnResult(reply="Hola mundo", pending_action_ids=["abc123"])

    monkeypatch.setattr("asistente_mikha.api.routes.run_turn_stream", fake_stream)
    with TestClient(app) as test_client:
        yield test_client
    memory_tools.reset_indexer_for_tests()


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        name, payload = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
        if name is not None:
            events.append((name, payload))
    return events


def test_chat_stream_emits_tokens_then_done(client):
    response = client.post("/chat/stream", json={"session_id": "s1", "message": "hola"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["token", "token", "done"]
    assert [p["text"] for name, p in events if name == "token"] == ["Hola ", "mundo"]

    done = events[-1][1]
    assert done["reply"] == "Hola mundo"
    assert done["pending_action_ids"] == ["abc123"]
    assert done["duration_seconds"] >= 0
    assert done["queried_at"]
```

Run: `pytest tests/test_api_stream.py -v`
Expected: FAIL con 404 (el endpoint no existe todavía).

- [ ] **Step 2: Implementar**

En `src/asistente_mikha/api/routes.py`, agregar los imports (`json`, `AsyncIterator` de `typing`, `StreamingResponse` de `fastapi.responses`, y `run_turn_stream`/`AgentTurnResult` de `asistente_mikha.agent`) y el endpoint:

```python
def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    async def event_source() -> AsyncIterator[str]:
        queried_at = datetime.now()
        started = time.perf_counter()
        async for item in run_turn_stream(request.session_id, request.message):
            if isinstance(item, AgentTurnResult):
                yield _sse(
                    "done",
                    {
                        "reply": item.reply,
                        "pending_action_ids": item.pending_action_ids,
                        "duration_seconds": time.perf_counter() - started,
                        "queried_at": queried_at.isoformat(),
                    },
                )
            else:
                yield _sse("token", {"text": item})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 3: Verificar**

Run: `pytest tests/test_api_stream.py -v`
Expected: 1 passed.

- [ ] **Step 4: Verificar contra Ollama real (manual)**

Run:
```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id":"curl-test","message":"Decime hola en una frase corta."}'
```
Expected: los eventos `token` llegan de a poco (no todos juntos al final), y cierra con un evento `done`. Requiere `uvicorn asistente_mikha.main:app` corriendo y Ollama activo.

- [ ] **Step 5: Commit**

```bash
git add src/asistente_mikha/api/routes.py tests/test_api_stream.py
git commit -m "feat: endpoint SSE de chat con streaming de tokens"
```

---

## Task 4: Scaffold del frontend, servido por FastAPI y Docker

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`, `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/src/styles/tokens.css`
- Modify: `src/asistente_mikha/main.py`
- Modify: `Dockerfile`
- Modify: `.dockerignore`
- Test: `tests/test_static_serving.py`

**Interfaces:**
- Produces: el build de Vite en `frontend/dist/`, servido por FastAPI en `/`; los tokens CSS como única fuente de verdad de color/tipografía para las tareas siguientes.

- [ ] **Step 1: Crear el proyecto Vite**

```bash
cd /home/mikhail/Proyectos/Asistente_Mikha
npm create vite@latest frontend -- --template react
cd frontend && npm install && npm install three && npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Configurar Vite**

`frontend/vite.config.js`:
```javascript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const API_ROUTES = ['/chat', '/system', '/tasks', '/notes', '/actions', '/confirm', '/health'];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      API_ROUTES.map((route) => [route, { target: 'http://localhost:8000', changeOrigin: true }]),
    ),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.js'],
    globals: true,
  },
});
```

`frontend/src/test-setup.js`:
```javascript
import '@testing-library/jest-dom';
```

- [ ] **Step 3: Tokens de diseño**

`frontend/src/styles/tokens.css`:
```css
:root {
  --canvas: #141312;
  --surface: #1c1a18;
  --hairline: #2a2724;
  --text: #edeae6;
  --muted: #8a837c;
  --amber: #f2a03d;
  --amber-hot: #ffd9a0;

  --font-display: 'Space Grotesk', system-ui, sans-serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;

  --radius: 14px;
  --gap: 16px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--canvas);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 14px;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.label {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

.display {
  font-family: var(--font-display);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* El ambar es luz emitida, nunca relleno plano. */
.live { color: var(--amber); text-shadow: 0 0 12px rgba(242, 160, 61, 0.45); }
```

Las fuentes se agregan como archivos locales en `frontend/public/fonts/` con `@font-face` en este mismo archivo. **No usar Google Fonts ni ningún CDN.** Si los archivos de fuente no están disponibles al implementar, usar los fallbacks de sistema ya declarados en las variables y reportarlo como concern — no sustituir por un CDN.

- [ ] **Step 4: Shell mínima de la app**

`frontend/src/main.jsx`:
```jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './styles/tokens.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`frontend/src/App.jsx` (shell provisional; el layout real llega en la Task 8):
```jsx
export default function App() {
  return (
    <main style={{ padding: 24 }}>
      <h1 className="display">Mikha</h1>
      <p className="label">interfaz web</p>
    </main>
  );
}
```

- [ ] **Step 5: Servir el build desde FastAPI**

En `src/asistente_mikha/main.py`:
```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
```

Y al final del archivo, **después** de `app.include_router(router)`, para no tapar las rutas de API:
```python
# Se monta al final a proposito: StaticFiles en "/" capturaria las rutas de
# API si se montara antes. En desarrollo el dist puede no existir todavia.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
```

- [ ] **Step 6: Test de que la API sigue respondiendo con el mount puesto**

`tests/test_static_serving.py`:
```python
from fastapi.testclient import TestClient

from asistente_mikha.main import app


def test_api_routes_still_reachable_with_static_mount():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
```

Run: `pytest tests/test_static_serving.py -v`
Expected: 1 passed (con o sin `dist/` presente).

- [ ] **Step 7: Buildear y verificar el servido**

```bash
cd frontend && npm run build && cd ..
source .venv/bin/activate && uvicorn asistente_mikha.main:app &
sleep 3
curl -s http://localhost:8000/ | head -5
curl -s http://localhost:8000/health
```
Expected: `/` devuelve el HTML del build y `/health` sigue devolviendo el JSON. Matar el uvicorn después.

- [ ] **Step 8: Dockerfile multi-stage**

`Dockerfile`:
```dockerfile
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .
COPY --from=frontend /build/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "asistente_mikha.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Agregar a `.dockerignore`:
```
frontend/node_modules/
frontend/dist/
```

Nota: `FRONTEND_DIST` se resuelve como `parents[2]/frontend/dist`. Dentro de la imagen, `src/asistente_mikha/main.py` vive en `/app/src/asistente_mikha/`, así que `parents[2]` es `/app` y el path da `/app/frontend/dist`, que es donde el `COPY --from` deja el build. Verificarlo en el Step 9, no asumirlo.

- [ ] **Step 9: Verificar en Docker**

```bash
docker compose up --build -d
sleep 8
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ | head -3
docker compose down
```
Expected: `/health` devuelve `{"status":"ok",...}` y `/` devuelve el HTML del build. Si `/` da 404, el path de `FRONTEND_DIST` no coincide dentro de la imagen — corregirlo antes de seguir.

- [ ] **Step 10: Commit**

```bash
git add frontend .dockerignore Dockerfile src/asistente_mikha/main.py tests/test_static_serving.py
git commit -m "feat: scaffold del frontend React servido por FastAPI"
```

---

## Task 5: El orbe

**Files:**
- Create: `frontend/src/orb/orb.js`, `frontend/src/orb/Orb.jsx`
- Test: `frontend/src/orb/orb.test.js`

**Interfaces:**
- Produces: `createOrb(canvas) -> { setState, setLevel, dispose }` con estados `'idle' | 'thinking' | 'speaking' | 'awaiting'`; componente `<Orb state level />`.

- [ ] **Step 1: Escribir el smoke test (falla primero)**

`frontend/src/orb/orb.test.js`:
```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createOrb } from './orb.js';

// Three.js necesita WebGL, que jsdom no provee: se mockea el renderer.
vi.mock('three', async () => {
  const actual = await vi.importActual('three');
  return {
    ...actual,
    WebGLRenderer: class {
      setPixelRatio() {}
      setSize() {}
      render() {}
      dispose() {}
      domElement = { width: 100, height: 100 };
    },
  };
});

describe('createOrb', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  });

  it('expone la API mínima', () => {
    const orb = createOrb(document.createElement('canvas'));
    expect(typeof orb.setState).toBe('function');
    expect(typeof orb.setLevel).toBe('function');
    expect(typeof orb.dispose).toBe('function');
    orb.dispose();
  });

  it('cancela su loop de animación al destruirse', () => {
    const orb = createOrb(document.createElement('canvas'));
    orb.dispose();
    expect(cancelAnimationFrame).toHaveBeenCalled();
  });

  it('acepta niveles fuera de rango sin romperse', () => {
    const orb = createOrb(document.createElement('canvas'));
    expect(() => { orb.setLevel(-5); orb.setLevel(42); }).not.toThrow();
    orb.dispose();
  });
});
```

Run: `cd frontend && npx vitest run src/orb/orb.test.js`
Expected: FAIL — el módulo no existe.

- [ ] **Step 2: Implementar el orbe**

`frontend/src/orb/orb.js`:
```javascript
import * as THREE from 'three';

const PARTICLE_COUNT = 2000;

const STATE_PARAMS = {
  idle: { amp: 0.02, speed: 0.3, opacity: 0.45 },
  thinking: { amp: 0.06, speed: 1.4, opacity: 0.75 },
  speaking: { amp: 0.18, speed: 2.2, opacity: 1.0 },
  awaiting: { amp: 0.04, speed: 0.5, opacity: 1.0 },
};

export function createOrb(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.z = 3.2;

  // Distribucion de Fibonacci: puntos repartidos parejo sobre la esfera.
  const base = new Float32Array(PARTICLE_COUNT * 3);
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  for (let i = 0; i < PARTICLE_COUNT; i += 1) {
    const y = 1 - (i / (PARTICLE_COUNT - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    const x = Math.cos(theta) * r;
    const z = Math.sin(theta) * r;
    base.set([x, y, z], i * 3);
    positions.set([x, y, z], i * 3);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  const material = new THREE.PointsMaterial({
    size: 0.035,
    color: new THREE.Color('#f2a03d'),
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });

  const points = new THREE.Points(geometry, material);
  scene.add(points);

  let state = 'idle';
  let level = 0;
  let time = 0;
  let rafId = null;

  const reduceMotion =
    typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function resize() {
    const { clientWidth, clientHeight } = canvas;
    if (!clientWidth || !clientHeight) return;
    renderer.setSize(clientWidth, clientHeight, false);
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
  }

  function frame() {
    time += 0.016;
    const params = STATE_PARAMS[state] || STATE_PARAMS.idle;
    const drive = state === 'speaking' ? level : 1;
    const array = geometry.attributes.position.array;

    for (let i = 0; i < PARTICLE_COUNT; i += 1) {
      const i3 = i * 3;
      const bx = base[i3];
      const by = base[i3 + 1];
      const bz = base[i3 + 2];
      const noise = Math.sin(time * params.speed + bx * 4) * Math.cos(time * params.speed + by * 4);
      const scale = 1 + noise * params.amp * drive;
      array[i3] = bx * scale;
      array[i3 + 1] = by * scale;
      array[i3 + 2] = bz * scale;
    }

    geometry.attributes.position.needsUpdate = true;
    material.opacity = params.opacity * (0.7 + 0.3 * drive);
    points.rotation.y += 0.0015;
    renderer.render(scene, camera);
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (rafId === null) rafId = requestAnimationFrame(frame);
  }

  function stop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  // Si la pestaña no esta visible, no tiene sentido quemar GPU de fondo.
  function onVisibility() {
    if (document.hidden) stop();
    else start();
  }

  resize();
  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', onVisibility);

  if (reduceMotion) {
    renderer.render(scene, camera);
  } else {
    start();
  }

  return {
    setState(next) {
      if (next in STATE_PARAMS) state = next;
    },
    setLevel(next) {
      const value = Number(next);
      level = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
    },
    dispose() {
      stop();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
    },
  };
}
```

- [ ] **Step 3: El wrapper de React**

`frontend/src/orb/Orb.jsx`:
```jsx
import { useEffect, useRef } from 'react';
import { createOrb } from './orb.js';

export default function Orb({ state = 'idle', level = 0 }) {
  const canvasRef = useRef(null);
  const orbRef = useRef(null);

  useEffect(() => {
    orbRef.current = createOrb(canvasRef.current);
    return () => {
      orbRef.current?.dispose();
      orbRef.current = null;
    };
  }, []);

  useEffect(() => { orbRef.current?.setState(state); }, [state]);
  useEffect(() => { orbRef.current?.setLevel(level); }, [level]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />;
}
```

- [ ] **Step 4: Verificar**

Run: `cd frontend && npx vitest run src/orb/orb.test.js`
Expected: 3 passed.

- [ ] **Step 5: Verificar visualmente (manual)**

Poner `<Orb state="speaking" level={0.8} />` temporalmente en `App.jsx` con un contenedor de 400x400, correr `npm run dev`, y confirmar en el navegador que se ve un orbe de partículas ámbar animado. Revertir el cambio en `App.jsx` después.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/orb
git commit -m "feat: orbe 3D como presencia del asistente"
```

---

## Task 6: Chat con streaming y el orbe conectado

**Files:**
- Create: `frontend/src/api.js`, `frontend/src/chat/useChatStream.js`, `frontend/src/chat/Chat.jsx`
- Test: `frontend/src/chat/useChatStream.test.js`

**Interfaces:**
- Consumes: `POST /chat/stream` (Task 3); `<Orb>` (Task 5).
- Produces: `useChatStream()` → `{ messages, send, state, level, error }` donde `state` es el estado del orbe y `level` el 0..1 del seguidor de envolvente.

- [ ] **Step 1: Escribir el test (falla primero)**

`frontend/src/chat/useChatStream.test.js`:
```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useChatStream } from './useChatStream.js';

function sseResponse(chunks) {
  const encoder = new TextEncoder();
  return {
    ok: true,
    body: {
      getReader() {
        let i = 0;
        return {
          read: async () =>
            i < chunks.length
              ? { done: false, value: encoder.encode(chunks[i++]) }
              : { done: true, value: undefined },
          releaseLock() {},
        };
      },
    },
  };
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});

describe('useChatStream', () => {
  it('acumula los tokens y cierra con el evento done', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([
      'event: token\ndata: {"text":"Hola "}\n\n',
      'event: token\ndata: {"text":"mundo"}\n\n',
      'event: done\ndata: {"reply":"Hola mundo","pending_action_ids":[],"duration_seconds":1.2,"queried_at":"2026-09-11T10:00:00"}\n\n',
    ])));

    const { result } = renderHook(() => useChatStream());
    await act(async () => { await result.current.send('hola'); });

    await waitFor(() => expect(result.current.state).toBe('idle'));
    const last = result.current.messages.at(-1);
    expect(last.role).toBe('assistant');
    expect(last.text).toBe('Hola mundo');
    expect(last.durationSeconds).toBe(1.2);
    expect(last.incomplete).toBeFalsy();
  });

  it('marca el mensaje como incompleto si el stream corta sin done', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([
      'event: token\ndata: {"text":"a medio "}\n\n',
    ])));

    const { result } = renderHook(() => useChatStream());
    await act(async () => { await result.current.send('hola'); });

    await waitFor(() => expect(result.current.state).toBe('idle'));
    expect(result.current.messages.at(-1).incomplete).toBe(true);
  });

  it('reporta error si el backend no responde', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('sin conexion'); }));

    const { result } = renderHook(() => useChatStream());
    await act(async () => { await result.current.send('hola'); });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.state).toBe('idle');
  });
});
```

Run: `cd frontend && npx vitest run src/chat/useChatStream.test.js`
Expected: FAIL — el módulo no existe.

- [ ] **Step 2: Implementar el hook**

`frontend/src/chat/useChatStream.js`:
```javascript
import { useCallback, useEffect, useRef, useState } from 'react';

const LEVEL_BUMP = 0.35;
const LEVEL_DECAY = 0.92;

function parseSSE(buffer) {
  // Devuelve [eventos completos, resto sin terminar].
  const blocks = buffer.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events = [];
  for (const block of blocks) {
    let name = null;
    let data = null;
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) name = line.slice(7);
      else if (line.startsWith('data: ')) {
        try { data = JSON.parse(line.slice(6)); } catch { data = null; }
      }
    }
    if (name) events.push({ name, data });
  }
  return [events, rest];
}

export function useChatStream() {
  const [messages, setMessages] = useState([]);
  const [state, setState] = useState('idle');
  const [level, setLevel] = useState(0);
  const [error, setError] = useState(null);
  const levelRef = useRef(0);
  const rafRef = useRef(null);

  // Seguidor de envolvente: cada token empuja el nivel, el loop lo decae.
  // Manana esta misma senal la alimenta la amplitud del audio.
  useEffect(() => {
    function tick() {
      levelRef.current *= LEVEL_DECAY;
      setLevel(levelRef.current);
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  const send = useCallback(async (text) => {
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', text }]);
    setState('thinking');

    let response;
    try {
      response = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: 'web', message: text }),
      });
    } catch (err) {
      setError(err.message || 'sin conexion con el backend');
      setState('idle');
      return;
    }

    if (!response.ok || !response.body) {
      setError(`el backend respondio ${response.status}`);
      setState('idle');
      return;
    }

    setMessages((prev) => [...prev, { role: 'assistant', text: '', incomplete: true }]);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let sawDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const [events, rest] = parseSSE(buffer);
      buffer = rest;

      for (const event of events) {
        if (event.name === 'token') {
          setState('speaking');
          levelRef.current = Math.min(1, levelRef.current + LEVEL_BUMP);
          setMessages((prev) => {
            const next = [...prev];
            const last = { ...next[next.length - 1] };
            last.text += event.data?.text ?? '';
            next[next.length - 1] = last;
            return next;
          });
        } else if (event.name === 'done') {
          sawDone = true;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = {
              role: 'assistant',
              text: event.data.reply,
              durationSeconds: event.data.duration_seconds,
              queriedAt: event.data.queried_at,
              pendingActionIds: event.data.pending_action_ids ?? [],
            };
            return next;
          });
          setState(
            (event.data.pending_action_ids ?? []).length > 0 ? 'awaiting' : 'idle',
          );
        }
      }
    }

    if (!sawDone) {
      // El stream corto a mitad: se deja marcado, nunca se muestra como completo.
      setError('la respuesta se corto antes de terminar');
      setState('idle');
    }
  }, []);

  return { messages, send, state, level, error };
}
```

- [ ] **Step 3: El componente de chat**

`frontend/src/chat/Chat.jsx`:
```jsx
import { useState } from 'react';

function formatTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString();
}

export default function Chat({ messages, onSend, error }) {
  const [draft, setDraft] = useState('');

  function submit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    onSend(text);
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)', minHeight: 0 }}>
      <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }}>
        {messages.map((message, index) => (
          <div key={index}>
            <div className="label">{message.role === 'user' ? 'vos' : 'mikha'}</div>
            <div style={{ whiteSpace: 'pre-wrap' }}>{message.text}</div>
            {message.durationSeconds !== undefined && (
              <div className="label" style={{ marginTop: 4 }}>
                {formatTime(message.queriedAt)} · {message.durationSeconds.toFixed(1)}s
              </div>
            )}
            {message.incomplete && <div className="label live">respuesta incompleta</div>}
          </div>
        ))}
      </div>

      {error && <div className="label live">{error}</div>}

      <form onSubmit={submit}>
        <input
          className="panel"
          style={{ width: '100%', color: 'var(--text)', fontFamily: 'var(--font-body)' }}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="escribí algo…"
          aria-label="mensaje"
        />
      </form>
    </section>
  );
}
```

- [ ] **Step 4: Verificar**

Run: `cd frontend && npx vitest run src/chat/useChatStream.test.js`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/chat frontend/src/api.js
git commit -m "feat: chat con streaming SSE y nivel para el orbe"
```

---

## Task 7: Los cuatro paneles

**Files:**
- Create: `frontend/src/panels/SystemPanel.jsx`, `TasksPanel.jsx`, `NotesPanel.jsx`, `PendingActionsPanel.jsx`, `frontend/src/panels/usePanelData.js`
- Test: `frontend/src/panels/panels.test.jsx`

**Interfaces:**
- Consumes: `GET /system`, `GET /tasks`, `GET /notes/recent`, `GET /actions/pending`, `POST /confirm/{id}` (Task 2 y lo ya existente).
- Produces: los cuatro componentes de panel y el hook `usePanelData(url, { intervalMs })`.

- [ ] **Step 1: Escribir los tests (fallan primero)**

`frontend/src/panels/panels.test.jsx`:
```jsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SystemPanel from './SystemPanel.jsx';
import TasksPanel from './TasksPanel.jsx';
import PendingActionsPanel from './PendingActionsPanel.jsx';

function mockFetchOnce(payload) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => payload })));
}

describe('SystemPanel', () => {
  it('muestra las lecturas cuando el backend responde', async () => {
    mockFetchOnce({
      ram: { total_gb: 31.2, used_gb: 17.4, available_gb: 13.8, percent_used: 55.7 },
      disk: { path: '/', total_gb: 882, used_gb: 431, free_gb: 451, percent_used: 48.9 },
      gpu: { available: true, vram_total_bytes: 8573157376, vram_used_bytes: 1748852736, vram_used_percent: 20.4 },
    });

    render(<SystemPanel />);

    await waitFor(() => expect(screen.getByText(/31.2/)).toBeInTheDocument());
  });

  it('muestra desconectado, no ceros, si el backend falla', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('caido'); }));

    render(<SystemPanel />);

    await waitFor(() => expect(screen.getByText(/sin conexión/i)).toBeInTheDocument());
    expect(screen.queryByText(/0 GB/)).not.toBeInTheDocument();
  });

  it('informa cuando la GPU no esta disponible', async () => {
    mockFetchOnce({
      ram: { total_gb: 31.2, used_gb: 1, available_gb: 30, percent_used: 3 },
      disk: { path: '/', total_gb: 882, used_gb: 1, free_gb: 881, percent_used: 1 },
      gpu: { available: false, reason: 'rocm-smi no está instalado o no está en PATH' },
    });

    render(<SystemPanel />);

    await waitFor(() => expect(screen.getByText(/rocm-smi/)).toBeInTheDocument());
  });
});

describe('TasksPanel', () => {
  it('lista las tareas por lista', async () => {
    mockFetchOnce({ lists: [{ name: 'Casa', tasks: [{ text: 'lavar los platos', done: false }] }] });

    render(<TasksPanel refreshKey={0} />);

    await waitFor(() => expect(screen.getByText('lavar los platos')).toBeInTheDocument());
    expect(screen.getByText('Casa')).toBeInTheDocument();
  });
});

describe('PendingActionsPanel', () => {
  it('no renderiza nada cuando no hay acciones pendientes', async () => {
    mockFetchOnce({ actions: [] });

    const { container } = render(<PendingActionsPanel refreshKey={0} />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('muestra la accion pendiente con sus botones', async () => {
    mockFetchOnce({ actions: [{ action_id: 'abc123', tool_name: 'restart_service', kwargs: { service_name: 'wireplumber' } }] });

    render(<PendingActionsPanel refreshKey={0} />);

    await waitFor(() => expect(screen.getByText(/restart_service/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /aprobar/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /rechazar/i })).toBeInTheDocument();
  });
});
```

Run: `cd frontend && npx vitest run src/panels/panels.test.jsx`
Expected: FAIL — los módulos no existen.

- [ ] **Step 2: El hook compartido**

`frontend/src/panels/usePanelData.js`:
```javascript
import { useEffect, useState } from 'react';

export function usePanelData(url, { intervalMs = 0, refreshKey = 0 } = {}) {
  const [data, setData] = useState(null);
  const [disconnected, setDisconnected] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(String(response.status));
        const payload = await response.json();
        if (!cancelled) {
          setData(payload);
          setDisconnected(false);
        }
      } catch {
        // Se marca desconectado y se conserva el ultimo dato bueno:
        // mostrar ceros mentiria sobre el estado real de la maquina.
        if (!cancelled) setDisconnected(true);
      }
    }

    load();
    if (!intervalMs) return () => { cancelled = true; };

    const id = setInterval(load, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [url, intervalMs, refreshKey]);

  return { data, disconnected };
}
```

- [ ] **Step 3: Los cuatro paneles**

`frontend/src/panels/SystemPanel.jsx`:
```jsx
import { usePanelData } from './usePanelData.js';

const LOAD_THRESHOLD = 80;

function Metric({ label, value, percent }) {
  const underLoad = typeof percent === 'number' && percent >= LOAD_THRESHOLD;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <span className="label">{label}</span>
      <span className={underLoad ? 'live' : undefined} style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        {value}
      </span>
    </div>
  );
}

export default function SystemPanel() {
  const { data, disconnected } = usePanelData('/system', { intervalMs: 5000 });

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>sistema</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <Metric label="ram" value={`${data.ram.available_gb} / ${data.ram.total_gb} GB`} percent={data.ram.percent_used} />
          <Metric label="disco" value={`${data.disk.free_gb} GB libres`} percent={data.disk.percent_used} />
          {data.gpu.available ? (
            <Metric label="gpu" value={`${data.gpu.vram_used_percent}% vram`} percent={data.gpu.vram_used_percent} />
          ) : (
            <Metric label="gpu" value={data.gpu.reason} />
          )}
        </div>
      )}
    </div>
  );
}
```

`frontend/src/panels/TasksPanel.jsx`:
```jsx
import { usePanelData } from './usePanelData.js';

export default function TasksPanel({ refreshKey }) {
  const { data, disconnected } = usePanelData('/tasks', { refreshKey });

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>tareas</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data?.lists.map((list) => (
        <div key={list.name} style={{ marginBottom: 10 }}>
          <div className="label">{list.name}</div>
          {list.tasks.map((task) => (
            <div key={task.text} style={{ fontSize: 13, opacity: task.done ? 0.45 : 1 }}>
              {task.done ? '☑' : '☐'} {task.text}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
```

`frontend/src/panels/NotesPanel.jsx`:
```jsx
import { usePanelData } from './usePanelData.js';

export default function NotesPanel({ refreshKey }) {
  const { data, disconnected } = usePanelData('/notes/recent', { refreshKey });

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>notas recientes</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data?.notes.map((note) => (
        <div key={note.title + note.created} style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13 }}>{note.title}</div>
          <div className="label" style={{ textTransform: 'none' }}>{note.excerpt}</div>
        </div>
      ))}
    </div>
  );
}
```

`frontend/src/panels/PendingActionsPanel.jsx`:
```jsx
import { usePanelData } from './usePanelData.js';

export default function PendingActionsPanel({ refreshKey, onResolved }) {
  const { data } = usePanelData('/actions/pending', { refreshKey });

  async function resolve(actionId, approve) {
    await fetch(`/confirm/${actionId}?approve=${approve}`, { method: 'POST' });
    onResolved?.();
  }

  // Este panel solo existe cuando te necesita.
  if (!data || data.actions.length === 0) return null;

  return (
    <div className="panel" style={{ borderColor: 'var(--amber)' }}>
      <div className="label live" style={{ marginBottom: 10 }}>por confirmar</div>
      {data.actions.map((action) => (
        <div key={action.action_id} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 13 }}>
            {action.tool_name} {Object.values(action.kwargs).join(' ')}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
            <button type="button" onClick={() => resolve(action.action_id, true)}>aprobar</button>
            <button type="button" onClick={() => resolve(action.action_id, false)}>rechazar</button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Verificar**

Run: `cd frontend && npx vitest run src/panels/panels.test.jsx`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/panels
git commit -m "feat: paneles de sistema, tareas, notas y confirmaciones"
```

---

## Task 8: Layout final, verificación en Docker y README

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `README.md`
- Test: verificación manual end-to-end

**Interfaces:**
- Consumes: todo lo construido en las Tasks 1-7.

- [ ] **Step 1: El layout**

`frontend/src/App.jsx`:
```jsx
import { useEffect, useState } from 'react';
import Orb from './orb/Orb.jsx';
import Chat from './chat/Chat.jsx';
import { useChatStream } from './chat/useChatStream.js';
import SystemPanel from './panels/SystemPanel.jsx';
import TasksPanel from './panels/TasksPanel.jsx';
import NotesPanel from './panels/NotesPanel.jsx';
import PendingActionsPanel from './panels/PendingActionsPanel.jsx';

export default function App() {
  const { messages, send, state, level, error } = useChatStream();
  const [refreshKey, setRefreshKey] = useState(0);
  const [clock, setClock] = useState('');

  // Los paneles se recargan cuando termina un turno, que es cuando pueden
  // haber cambiado; no hace falta polling para eso.
  useEffect(() => {
    if (state === 'idle' || state === 'awaiting') setRefreshKey((key) => key + 1);
  }, [state]);

  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ height: '100dvh', display: 'flex', flexDirection: 'column' }}>
      <header
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '12px 20px', borderBottom: '1px solid var(--hairline)',
        }}
      >
        <span className="display" style={{ fontSize: 15 }}>Mikha</span>
        <span className="label">{clock}</span>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 'var(--gap)', padding: 'var(--gap)', flex: 1, minHeight: 0 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)', minHeight: 0 }}>
          <div style={{ height: 260, flexShrink: 0 }}>
            <Orb state={state} level={level} />
          </div>
          <Chat messages={messages} onSend={send} error={error} />
        </div>

        <aside style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)', overflowY: 'auto' }}>
          <SystemPanel />
          <PendingActionsPanel refreshKey={refreshKey} onResolved={() => setRefreshKey((key) => key + 1)} />
          <TasksPanel refreshKey={refreshKey} />
          <NotesPanel refreshKey={refreshKey} />
        </aside>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Correr toda la suite del frontend**

Run: `cd frontend && npx vitest run`
Expected: todos los tests pasan (orbe + chat + paneles).

- [ ] **Step 3: Correr toda la suite del backend**

Run: `source .venv/bin/activate && pytest -q`
Expected: todo pasa (los tests marcados `xfail` siguen como xfail, no como fallos).

- [ ] **Step 4: Verificación manual end-to-end en desarrollo**

```bash
source .venv/bin/activate && uvicorn asistente_mikha.main:app &
cd frontend && npm run dev
```
Abrir la URL que imprime Vite y confirmar, uno por uno:
1. El orbe se ve y respira en `idle`.
2. Al mandar un mensaje, el orbe pasa a `thinking` y después vibra con los tokens mientras el texto aparece escribiéndose.
3. Debajo de la respuesta aparece la línea de hora y duración.
4. El panel de sistema muestra números reales y se refresca solo.
5. Pedir "reiniciá wireplumber" hace aparecer el panel de confirmación en ámbar, con sus botones; rechazar lo hace desaparecer.
6. Guardar una nota o agregar una tarea se refleja en su panel al terminar el turno.

Anotar cualquier punto que falle; no darlos por buenos sin mirarlos.

- [ ] **Step 5: Verificación en Docker**

```bash
cd /home/mikhail/Proyectos/Asistente_Mikha
docker compose up --build -d
sleep 10
curl -s http://localhost:8000/health
```
Abrir `http://localhost:8000` en el navegador y repetir los puntos 1 a 3 del Step 4 sobre el build de producción. Después `docker compose down`.

- [ ] **Step 6: Actualizar el README**

Agregar una sección `## Interfaz web` después de la de Tareas, explicando: que el dashboard se sirve en `http://localhost:8000` (el mismo backend), que en desarrollo se usa `npm run dev` dentro de `frontend/` con el backend corriendo aparte, y que el build de producción lo hace el Dockerfile solo. Agregar `Node 22+` a los requisitos (solo para desarrollo del frontend). Quitar "interfaz web" de la lista de próximas fases.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.jsx README.md
git commit -m "feat: layout del dashboard y documentacion de la interfaz web"
```

---

## Self-Review (completado durante la escritura de este plan)

- **Cobertura del spec:** streaming en el agente (Task 1), endpoints de lectura (Task 2), SSE (Task 3), scaffold + servido + Docker (Task 4), orbe con sus 4 estados y el `level` (Task 5), chat con el seguidor de envolvente (Task 6), los 4 paneles (Task 7), layout y verificación (Task 8). Los tokens de diseño, la regla del ámbar, `prefers-reduced-motion`, la pausa por visibilidad, y "desconectado en vez de ceros" están todos en Global Constraints y con tests o pasos de verificación.
- **Placeholders:** ninguno — todo el código es completo y ejecutable. La API de streaming de PydanticAI se verificó en vivo antes de escribir el plan (`run_stream` → `stream_text(delta=True)` → `all_messages()`), no se asumió.
- **Consistencia de tipos:** el evento `done` del SSE lleva las mismas claves que produce Task 3 y consume Task 6 (`reply`, `pending_action_ids`, `duration_seconds`, `queried_at`); las respuestas de los endpoints de Task 2 tienen las mismas formas que consumen los paneles de Task 7 (`ram/disk/gpu`, `lists[].name/tasks[]`, `notes[].title/created/excerpt`, `actions[].action_id/tool_name/kwargs`).
- **Desviación del spec registrada:** `fetch` + `ReadableStream` en vez de `EventSource`, porque `EventSource` no puede hacer POST. Está anotada en Global Constraints.
- **Riesgo marcado:** el path de `FRONTEND_DIST` dentro de la imagen Docker (Task 4 Step 8) se razonó pero debe verificarse en vivo en el Step 9 antes de continuar, no asumirse.
