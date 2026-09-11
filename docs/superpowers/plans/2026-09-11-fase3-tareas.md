# Fase 3 — Gestión de Tareas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a Mikha listas de tareas por tema/meta, guardadas como checkboxes de Markdown en el vault de Obsidian, gestionadas por una única herramienta router (`tasks`) que mantiene al agente en 4 herramientas totales.

**Architecture:** Nuevo módulo `memory/tasks.py` con funciones puras (sin `@tool`) sobre archivos `.md` en `<vault>/Tareas/`, expuestas al agente mediante una única herramienta router `tasks(action, ...)` agregada a `memory/tools.py` — mismo patrón que `diagnostics`, `system_action` y `memory` de fases anteriores.

**Tech Stack:** Solo librería estándar (sin dependencias nuevas); reutiliza `slugify()` de `memory/vault.py`.

**Spec:** `docs/superpowers/specs/2026-09-11-fase3-tareas-design.md`

## Global Constraints

- Las listas viven en `<vault>/Tareas/<slug-de-la-lista>.md`, sin frontmatter, con checkboxes nativos de Obsidian (`- [ ] texto`, `- [x] texto`).
- Todas las acciones de `tasks` son de riesgo `read` (ejecución inmediata, sin confirmación).
- `complete_task` nunca marca una tarea al azar: cero o más de una coincidencia se reportan explícitamente, nunca se adivina.
- Solo `action='add'` crea una lista nueva si no existe; `list`/`complete` sobre una lista inexistente devuelven un estado de error claro.
- El agente debe seguir teniendo exactamente 4 herramientas de nivel superior después de esta fase (`diagnostics`, `system_action`, `memory`, `tasks`).

---

## Task 1: Funciones puras de listas de tareas

**Files:**
- Create: `src/asistente_mikha/memory/tasks.py`
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `slugify` de `asistente_mikha.memory.vault`.
- Produces: `TaskItem` (dataclass: `text: str`, `done: bool`), `TaskList` (dataclass: `name: str`, `path: Path`, `items: list[TaskItem]`), `add_task(vault_path: Path, list_name: str, text: str) -> Path`, `list_tasks(vault_path: Path, list_name: str) -> TaskList | None`, `complete_task(vault_path: Path, list_name: str, text: str) -> dict`, `list_task_lists(vault_path: Path) -> list[str]`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_tasks.py`:
```python
from asistente_mikha.memory.tasks import (
    add_task,
    list_tasks,
    complete_task,
    list_task_lists,
)


def test_add_task_creates_list_file_with_title(tmp_path):
    path = add_task(tmp_path, "Idea de negocio", "comprar granos de cafe")
    assert path.exists()
    text = path.read_text()
    assert text.startswith("# Idea de negocio")
    assert "- [ ] comprar granos de cafe" in text


def test_add_task_appends_to_existing_list(tmp_path):
    add_task(tmp_path, "Casa", "lavar los platos")
    add_task(tmp_path, "Casa", "sacar la basura")

    result = list_tasks(tmp_path, "Casa")

    assert [t.text for t in result.items] == ["lavar los platos", "sacar la basura"]
    assert all(not t.done for t in result.items)


def test_list_tasks_returns_none_for_missing_list(tmp_path):
    assert list_tasks(tmp_path, "No existe") is None


def test_complete_task_marks_single_match(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche")
    add_task(tmp_path, "Compras", "comprar pan")

    result = complete_task(tmp_path, "Compras", "leche")

    assert result == {"status": "completed", "task": "comprar leche"}
    tasks_after = list_tasks(tmp_path, "Compras")
    done_map = {t.text: t.done for t in tasks_after.items}
    assert done_map["comprar leche"] is True
    assert done_map["comprar pan"] is False


def test_complete_task_returns_not_found(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche")

    result = complete_task(tmp_path, "Compras", "algo que no existe")

    assert result == {"status": "not_found"}


def test_complete_task_returns_ambiguous_for_multiple_matches(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche entera")
    add_task(tmp_path, "Compras", "comprar leche deslactosada")

    result = complete_task(tmp_path, "Compras", "leche")

    assert result["status"] == "ambiguous"
    assert set(result["matches"]) == {"comprar leche entera", "comprar leche deslactosada"}


def test_complete_task_returns_list_not_found(tmp_path):
    assert complete_task(tmp_path, "No existe", "algo") == {"status": "list_not_found"}


def test_list_task_lists_returns_pretty_names(tmp_path):
    add_task(tmp_path, "Idea de negocio", "tarea 1")
    add_task(tmp_path, "Casa", "tarea 2")

    assert set(list_task_lists(tmp_path)) == {"Idea de negocio", "Casa"}


def test_list_task_lists_returns_empty_when_no_tasks_dir(tmp_path):
    assert list_task_lists(tmp_path) == []
```

Run: `pytest tests/test_tasks.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.memory.tasks'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/memory/tasks.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from asistente_mikha.memory.vault import slugify

TASKS_DIRNAME = "Tareas"

_TASK_LINE_RE = re.compile(r"^- \[( |x|X)\] (.+)$")


@dataclass
class TaskItem:
    text: str
    done: bool


@dataclass
class TaskList:
    name: str
    path: Path
    items: list[TaskItem] = field(default_factory=list)


def _tasks_dir(vault_path: Path) -> Path:
    return vault_path / TASKS_DIRNAME


def _list_path(vault_path: Path, list_name: str) -> Path:
    return _tasks_dir(vault_path) / f"{slugify(list_name)}.md"


def add_task(vault_path: Path, list_name: str, text: str) -> Path:
    tasks_dir = _tasks_dir(vault_path)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        file_path.write_text(f"# {list_name}\n\n", encoding="utf-8")
    with file_path.open("a", encoding="utf-8") as f:
        f.write(f"- [ ] {text}\n")
    return file_path


def _parse_task_list(file_path: Path, name: str) -> TaskList:
    items: list[TaskItem] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        match = _TASK_LINE_RE.match(line.strip())
        if match:
            done = match.group(1).lower() == "x"
            items.append(TaskItem(text=match.group(2), done=done))
    return TaskList(name=name, path=file_path, items=items)


def list_tasks(vault_path: Path, list_name: str) -> TaskList | None:
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        return None
    return _parse_task_list(file_path, list_name)


def complete_task(vault_path: Path, list_name: str, text: str) -> dict:
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        return {"status": "list_not_found"}
    lines = file_path.read_text(encoding="utf-8").splitlines()
    matches: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        match = _TASK_LINE_RE.match(line.strip())
        if match and match.group(1) == " " and text.lower() in match.group(2).lower():
            matches.append((i, match.group(2)))
    if len(matches) == 0:
        return {"status": "not_found"}
    if len(matches) > 1:
        return {"status": "ambiguous", "matches": [m[1] for m in matches]}
    index, exact_text = matches[0]
    lines[index] = f"- [x] {exact_text}"
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "completed", "task": exact_text}


def list_task_lists(vault_path: Path) -> list[str]:
    tasks_dir = _tasks_dir(vault_path)
    if not tasks_dir.exists():
        return []
    names = []
    for file_path in sorted(tasks_dir.glob("*.md")):
        raw = file_path.read_text(encoding="utf-8")
        first_line = raw.splitlines()[0] if raw else ""
        if first_line.startswith("# "):
            names.append(first_line[2:].strip())
        else:
            names.append(file_path.stem)
    return names
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_tasks.py -v`
Expected: 9 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/memory/tasks.py tests/test_tasks.py
git commit -m "feat: funciones puras de listas de tareas en markdown"
```

---

## Task 2: Herramienta router `tasks`

**Files:**
- Modify: `src/asistente_mikha/memory/tools.py`
- Modify: `tests/test_memory_tools.py`

**Interfaces:**
- Consumes: `add_task`, `list_tasks`, `complete_task`, `list_task_lists` de `asistente_mikha.memory.tasks` (Task 1); `get_vault_path` de `asistente_mikha.config` (ya usado en el archivo).
- Produces: `tasks(action: Literal["add", "list", "complete", "list_lists"], list_name: str | None = None, text: str | None = None) -> dict`.

- [ ] **Step 1: Escribir tests (fallan primero)**

Agregar a `tests/test_memory_tools.py`:
```python
def test_tasks_router_add_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    added = memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")
    assert added["status"] == "added"

    listed = memory_tools.tasks(action="list", list_name="Casa")
    assert listed["tasks"] == [{"text": "lavar los platos", "done": False}]


def test_tasks_router_list_returns_list_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    result = memory_tools.tasks(action="list", list_name="No existe")

    assert result == {"status": "list_not_found"}


def test_tasks_router_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")

    result = memory_tools.tasks(action="complete", list_name="Casa", text="lavar")

    assert result["status"] == "completed"


def test_tasks_router_list_lists(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.tasks(action="add", list_name="Casa", text="algo")

    result = memory_tools.tasks(action="list_lists")

    assert result == {"lists": ["Casa"]}
```

Run: `pytest tests/test_memory_tools.py -v`
Expected: FAIL con `AttributeError: module 'asistente_mikha.memory.tools' has no attribute 'tasks'`.

- [ ] **Step 2: Implementar**

En `src/asistente_mikha/memory/tools.py`, agregar el import y la función al final del archivo:

```python
from asistente_mikha.memory.tasks import (
    add_task,
    complete_task,
    list_task_lists,
    list_tasks,
)
```

```python
@tool(
    risk=ToolRisk.READ,
    description="Gestiona listas de tareas por tema/meta en el vault de Obsidian del usuario.",
)
def tasks(
    action: Literal["add", "list", "complete", "list_lists"],
    list_name: str | None = None,
    text: str | None = None,
) -> dict:
    """Agrega, lista o completa tareas de una lista por tema, o lista todas las listas existentes."""
    vault_path = get_vault_path()
    if action == "add":
        path = add_task(vault_path, list_name or "", text or "")
        return {"status": "added", "path": str(path)}
    if action == "list":
        result = list_tasks(vault_path, list_name or "")
        if result is None:
            return {"status": "list_not_found"}
        return {
            "list": result.name,
            "tasks": [{"text": item.text, "done": item.done} for item in result.items],
        }
    if action == "complete":
        return complete_task(vault_path, list_name or "", text or "")
    return {"lists": list_task_lists(vault_path)}
```

(`Literal` ya está importado en el archivo desde la Fase 2.)

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_memory_tools.py -v`
Expected: todos pasan (los de save_note/search_notes/memory ya existentes + los 4 nuevos de tasks).

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/memory/tools.py tests/test_memory_tools.py
git commit -m "feat: herramienta router tasks para listas de tareas por tema"
```

---

## Task 3: Integrar `tasks` en el agente

**Files:**
- Modify: `src/asistente_mikha/agent.py`
- Test: `tests/test_tasks_integration.py`

**Interfaces:**
- Consumes: `tasks` (Task 2, ya registrada automáticamente en `registry` al decorarse con `@tool` — no requiere nuevo import en `agent.py`, `memory.tools` ya se importa desde la Fase 2).
- Produces: ninguna interfaz nueva — el agente ya construido ahora tiene una cuarta herramienta disponible.

- [ ] **Step 1: Escribir test de integración (falla primero)**

`tests/test_tasks_integration.py`:
```python
import pytest

from asistente_mikha.agent import run_turn, reset_sessions_for_tests


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    reset_sessions_for_tests()
    yield
    reset_sessions_for_tests()


@pytest.mark.integration
async def test_agent_adds_and_lists_task():
    add_result = await run_turn(
        "tasks-test",
        "Agrega la tarea 'comprar granos de cafe' a mi lista de Idea de negocio.",
    )
    assert add_result.reply

    list_result = await run_turn(
        "tasks-test",
        "Que tareas tengo en mi lista de Idea de negocio?",
    )
    assert "cafe" in list_result.reply.lower() or "café" in list_result.reply.lower()
```

Run: `pytest tests/test_tasks_integration.py -v -m integration`
Expected: FAIL — el agente todavía no sabe de la herramienta `tasks` en su prompt (puede no invocarla, o el test simplemente confirma el estado actual antes del cambio).

- [ ] **Step 2: Actualizar el `SYSTEM_PROMPT` en `agent.py`**

Reemplazar el bloque que enumera las herramientas:

```python
SYSTEM_PROMPT = (
    "Eres el asistente personal de esta máquina Linux. Tienes 4 "
    "herramientas:\n\n"
    "1. diagnostics(check): 'ram', 'disk', 'processes' o 'gpu'. Solo "
    "lectura, siempre disponible.\n"
    "2. system_action(action, target): action='restart_service' con "
    "target='wireplumber', o action='clear_directory_cache' con "
    "target='asistente_scratch'. Requiere confirmación aparte.\n"
    "3. memory(action, ...): SÍ TIENES memoria persistente en un vault de "
    "Obsidian. Nunca digas 'no tengo acceso a guardar/buscar notas' — esa "
    "frase es falsa. Con action='save_note', pasa title y content; con "
    "action='search_notes', pasa query.\n"
    "4. tasks(action, list_name, text): listas de tareas por tema/meta. "
    "action='add' agrega una tarea (crea la lista si no existe); "
    "action='list' muestra las tareas de una lista; action='complete' "
    "marca una tarea como hecha buscándola por texto; action='list_lists' "
    "muestra todas las listas que existen.\n\n"
    "Cuando el usuario pida guardar, anotar o recordar algo, llama de "
    "inmediato a memory(action='save_note', ...) — nunca digas que "
    "guardaste algo sin haber llamado la herramienta de verdad. Cuando "
    "pregunten por notas guardadas, llama a memory(action='search_notes', "
    "...) antes de responder, y basa tu respuesta únicamente en lo que "
    "haya devuelto.\n\n"
    "Cuando el usuario pida agregar una tarea y NO haya dicho a qué lista "
    "o meta pertenece, pregúntaselo antes de llamar a tasks — nunca "
    "inventes ni asumas una lista. Cuando sí la haya dicho, llama a "
    "tasks(action='add', ...) de inmediato.\n\n"
    "No tienes acceso a calendarios ni a internet. Usa las herramientas "
    "para responder con datos reales, nunca inventes cifras ni contenido "
    "de notas o tareas. Si de verdad te piden algo fuera de tus "
    "capacidades, dilo con claridad — nunca inventes comandos o "
    "capacidades que no tienes.\n\n"
    "Cuando el usuario pida reiniciar un servicio o vaciar una caché, "
    "llama SIEMPRE a system_action de inmediato, sin preguntar primero en "
    "el chat si está seguro — la herramienta ya genera su propia solicitud "
    "de confirmación, separada de esta conversación. Cuando una "
    "herramienta devuelva status='pending_confirmation', explícale al "
    "usuario que la acción quedó pendiente de confirmación y menciona su "
    "action_id."
)
```

- [ ] **Step 3: Verificar que pasa (con Ollama corriendo)**

Run: `pytest tests/test_tasks_integration.py -v -m integration`
Expected: 1 passed.

- [ ] **Step 4: Confirmar que el agente sigue teniendo exactamente 4 herramientas**

Run:
```bash
python3 -c "
from asistente_mikha import agent
from asistente_mikha.tools import registry
print(sorted(registry.all_tools().keys()))
"
```
Expected: `['diagnostics', 'memory', 'system_action', 'tasks']`.

- [ ] **Step 5: Correr toda la suite**

Run: `pytest -v`
Expected: todos los tests pasan (Fase 1 + Fase 2 + Fase 3).

- [ ] **Step 6: Commit**

```bash
git add src/asistente_mikha/agent.py tests/test_tasks_integration.py
git commit -m "feat: integrar tasks en el agente como cuarta herramienta"
```

---

## Self-Review (completado durante la escritura de este plan)

- **Cobertura del spec:** funciones puras (Task 1), router (Task 2), integración en el agente (Task 3). Manejo de errores (`list_not_found`, `not_found`, `ambiguous`) cubierto en los tests de Task 1 y Task 2. El comportamiento de "preguntar antes de asumir la lista" queda documentado en el prompt de Task 3, con la salvedad ya acordada de que es mejor esfuerzo, no garantizado.
- **Placeholders:** ninguno — todo el código de cada step es completo y ejecutable.
- **Consistencia de tipos:** `TaskItem`/`TaskList` y las claves de los diccionarios de retorno (`status`, `task`, `matches`, `list`, `tasks`, `lists`, `path`) se usan de forma idéntica en Task 1, Task 2 y sus tests.
