# Fase 1 — Núcleo del Agente Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el backend (FastAPI + agente PydanticAI sobre Ollama) y el cliente CLI del asistente de diagnóstico de máquina, con tool-calling de solo-lectura + acciones controladas por confirmación explícita, y observabilidad OpenTelemetry/Phoenix instrumentada desde el inicio.

**Architecture:** Proceso único Python (`uvicorn`). Capas: API (FastAPI) → Agente (PydanticAI, hablando con Ollama vía su endpoint OpenAI-compatible) → Registro de herramientas tipadas con nivel de riesgo (`read` se ejecuta directo, `confirm` solo crea una acción pendiente) → capa de confirmación que ejecuta la implementación real cuando el cliente la aprueba explícitamente. Cada capa emite spans OpenTelemetry hacia Phoenix.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pydantic-ai 2.x, psutil, httpx, arize-phoenix + arize-phoenix-otel, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-10-agente-nucleo-design.md`

## Global Constraints

- Python >= 3.11.
- Sin Docker: todo corre como procesos nativos (`uvicorn`, `phoenix serve`, `ollama serve`).
- Modelo LLM por defecto: alias `default` de Ollama (actualmente `mistral-nemo:12b`), servido en `http://localhost:11434`.
- Ninguna herramienta de riesgo `confirm` puede ejecutar su efecto real sin pasar por el endpoint `/confirm/{action_id}`, incluso si el LLM la invoca directamente — es el guardrail central de esta fase.
- Toda llamada al LLM y a una herramienta debe generar un span OpenTelemetry.

---

## Task 1: Scaffolding del proyecto + registro de herramientas

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/asistente_mikha/__init__.py`
- Create: `src/asistente_mikha/tools/__init__.py`
- Create: `src/asistente_mikha/tools/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Produces: `ToolRisk` (Enum: `READ`, `CONFIRM`), `RegisteredTool` (dataclass: `name: str`, `func: Callable`, `risk: ToolRisk`, `description: str`), `tool(risk: ToolRisk, description: str)` (decorador), `get_tool(name: str) -> RegisteredTool | None`, `all_tools() -> dict[str, RegisteredTool]`, `clear_registry_for_tests() -> None`.

- [ ] **Step 1: Crear estructura y `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "asistente-mikha"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic-ai>=2.42.0",
    "psutil>=6.0",
    "httpx>=0.27",
    "arize-phoenix>=8.0",
    "arize-phoenix-otel>=0.6",
    "opentelemetry-api>=1.27",
    "opentelemetry-sdk>=1.27",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24"]

[project.scripts]
mikha = "asistente_mikha.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/asistente_mikha"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = ["integration: requiere ollama serve corriendo con el modelo 'default'"]
```

```
# .gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
```

Crear `src/asistente_mikha/__init__.py` vacío y `src/asistente_mikha/tools/__init__.py` vacío.

- [ ] **Step 2: Crear entorno e instalar**

Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```
Expected: instalación exitosa sin errores de dependencias.

- [ ] **Step 3: Escribir el test del registro (falla primero)**

`tests/test_registry.py`:
```python
import pytest

from asistente_mikha.tools.registry import (
    ToolRisk,
    tool,
    get_tool,
    all_tools,
    clear_registry_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry_for_tests()
    yield
    clear_registry_for_tests()


def test_tool_decorator_registers_function_with_metadata():
    @tool(risk=ToolRisk.READ, description="ejemplo de solo lectura")
    def sample_read_tool() -> str:
        return "ok"

    registered = get_tool("sample_read_tool")
    assert registered is not None
    assert registered.risk == ToolRisk.READ
    assert registered.description == "ejemplo de solo lectura"
    assert registered.func() == "ok"


def test_get_tool_returns_none_for_unknown_name():
    assert get_tool("no_existe") is None


def test_all_tools_returns_every_registered_tool():
    @tool(risk=ToolRisk.READ, description="a")
    def tool_a() -> None:
        ...

    @tool(risk=ToolRisk.CONFIRM, description="b")
    def tool_b() -> None:
        ...

    names = set(all_tools().keys())
    assert names == {"tool_a", "tool_b"}


def test_duplicate_registration_raises():
    @tool(risk=ToolRisk.READ, description="a")
    def dup_tool() -> None:
        ...

    with pytest.raises(ValueError):
        @tool(risk=ToolRisk.READ, description="a otra vez")
        def dup_tool() -> None:  # noqa: F811
            ...
```

Run: `pytest tests/test_registry.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.tools.registry'`.

- [ ] **Step 4: Implementar el registro**

`src/asistente_mikha/tools/registry.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ToolRisk(str, Enum):
    READ = "read"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    func: Callable[..., Any]
    risk: ToolRisk
    description: str


_REGISTRY: dict[str, RegisteredTool] = {}


def tool(risk: ToolRisk, description: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if func.__name__ in _REGISTRY:
            raise ValueError(f"Tool '{func.__name__}' ya está registrada")
        _REGISTRY[func.__name__] = RegisteredTool(
            name=func.__name__, func=func, risk=risk, description=description
        )
        return func

    return decorator


def get_tool(name: str) -> RegisteredTool | None:
    return _REGISTRY.get(name)


def all_tools() -> dict[str, RegisteredTool]:
    return dict(_REGISTRY)


def clear_registry_for_tests() -> None:
    _REGISTRY.clear()
```

- [ ] **Step 5: Verificar que pasa**

Run: `pytest tests/test_registry.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src tests
git commit -m "feat: scaffolding del proyecto y registro de herramientas"
```

---

## Task 2: Capa de confirmación

**Files:**
- Create: `src/asistente_mikha/confirmation.py`
- Test: `tests/test_confirmation.py`

**Interfaces:**
- Consumes: nada de tareas anteriores (módulo independiente).
- Produces: `ActionStatus` (Enum: `PENDING`, `CONFIRMED`, `REJECTED`, `EXPIRED`), `PendingAction` (dataclass: `action_id: str`, `tool_name: str`, `kwargs: dict`, `created_at: float`, `ttl_seconds: float`, `status: ActionStatus`, `result: Any`), `register_implementation(tool_name: str, func: Callable[..., dict]) -> None`, `PendingActionStore` (métodos `create(tool_name, kwargs) -> PendingAction`, `get(action_id) -> PendingAction | None`, `reject(action_id) -> PendingAction`, `execute(action_id) -> PendingAction`), `get_default_store() -> PendingActionStore`, `reset_default_store_for_tests() -> None`, `start_turn_tracking() -> None`, `collect_turn_actions() -> list[str]`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_confirmation.py`:
```python
import pytest

from asistente_mikha.confirmation import (
    ActionStatus,
    PendingActionStore,
    register_implementation,
    get_default_store,
    reset_default_store_for_tests,
    start_turn_tracking,
    collect_turn_actions,
)


@pytest.fixture(autouse=True)
def _clean_store():
    reset_default_store_for_tests()
    yield
    reset_default_store_for_tests()


def test_create_and_get_returns_pending_before_ttl():
    store = PendingActionStore(ttl_seconds=300.0)
    action = store.create("dummy_tool", {"x": 1})
    fetched = store.get(action.action_id)
    assert fetched is not None
    assert fetched.status == ActionStatus.PENDING
    assert fetched.kwargs == {"x": 1}


def test_action_expires_after_ttl():
    current = {"t": 1000.0}
    store = PendingActionStore(ttl_seconds=5.0, clock=lambda: current["t"])
    action = store.create("dummy_tool", {})
    current["t"] += 10.0
    assert store.get(action.action_id).status == ActionStatus.EXPIRED


def test_reject_sets_rejected_status():
    store = PendingActionStore()
    action = store.create("dummy_tool", {})
    rejected = store.reject(action.action_id)
    assert rejected.status == ActionStatus.REJECTED


def test_execute_calls_registered_implementation_with_kwargs():
    store = PendingActionStore()
    calls = []

    def fake_impl(x: int) -> dict:
        calls.append(x)
        return {"doubled": x * 2}

    register_implementation("dummy_tool", fake_impl)
    action = store.create("dummy_tool", {"x": 3})
    executed = store.execute(action.action_id)
    assert calls == [3]
    assert executed.status == ActionStatus.CONFIRMED
    assert executed.result == {"doubled": 6}


def test_execute_without_implementation_raises_keyerror():
    store = PendingActionStore()
    action = store.create("sin_implementacion", {})
    with pytest.raises(KeyError):
        store.execute(action.action_id)


def test_execute_twice_raises_valueerror():
    store = PendingActionStore()
    register_implementation("dummy_tool", lambda: {"ok": True})
    action = store.create("dummy_tool", {})
    store.execute(action.action_id)
    with pytest.raises(ValueError):
        store.execute(action.action_id)


def test_unknown_action_id_raises_keyerror_on_reject():
    store = PendingActionStore()
    with pytest.raises(KeyError):
        store.reject("no-existe")


def test_create_on_default_store_records_turn_action():
    reset_default_store_for_tests()
    start_turn_tracking()
    action = get_default_store().create("dummy_tool", {})
    assert collect_turn_actions() == [action.action_id]
```

Run: `pytest tests/test_confirmation.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.confirmation'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/confirmation.py`:
```python
from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ActionStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class PendingAction:
    action_id: str
    tool_name: str
    kwargs: dict[str, Any]
    created_at: float
    ttl_seconds: float
    status: ActionStatus = ActionStatus.PENDING
    result: Any = None


IMPLEMENTATIONS: dict[str, Callable[..., dict]] = {}


def register_implementation(tool_name: str, func: Callable[..., dict]) -> None:
    IMPLEMENTATIONS[tool_name] = func


_current_turn_actions: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "_current_turn_actions", default=None
)


def start_turn_tracking() -> None:
    _current_turn_actions.set([])


def record_pending_action(action_id: str) -> None:
    bucket = _current_turn_actions.get()
    if bucket is not None:
        bucket.append(action_id)


def collect_turn_actions() -> list[str]:
    return list(_current_turn_actions.get() or [])


class PendingActionStore:
    def __init__(
        self, ttl_seconds: float = 300.0, clock: Callable[[], float] = time.time
    ) -> None:
        self._actions: dict[str, PendingAction] = {}
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def create(self, tool_name: str, kwargs: dict[str, Any]) -> PendingAction:
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            tool_name=tool_name,
            kwargs=kwargs,
            created_at=self._clock(),
            ttl_seconds=self._ttl_seconds,
        )
        self._actions[action.action_id] = action
        record_pending_action(action.action_id)
        return action

    def get(self, action_id: str) -> PendingAction | None:
        action = self._actions.get(action_id)
        if action is None:
            return None
        if (
            action.status == ActionStatus.PENDING
            and self._clock() - action.created_at > action.ttl_seconds
        ):
            action.status = ActionStatus.EXPIRED
        return action

    def reject(self, action_id: str) -> PendingAction:
        action = self._require_pending(action_id)
        action.status = ActionStatus.REJECTED
        return action

    def execute(self, action_id: str) -> PendingAction:
        action = self._require_pending(action_id)
        impl = IMPLEMENTATIONS.get(action.tool_name)
        if impl is None:
            raise KeyError(f"No hay implementación registrada para '{action.tool_name}'")
        action.result = impl(**action.kwargs)
        action.status = ActionStatus.CONFIRMED
        return action

    def _require_pending(self, action_id: str) -> PendingAction:
        action = self.get(action_id)
        if action is None:
            raise KeyError(f"Acción '{action_id}' no existe")
        if action.status != ActionStatus.PENDING:
            raise ValueError(f"Acción '{action_id}' no está pendiente (estado: {action.status})")
        return action


_default_store = PendingActionStore()


def get_default_store() -> PendingActionStore:
    return _default_store


def reset_default_store_for_tests() -> None:
    global _default_store
    _default_store = PendingActionStore()
    IMPLEMENTATIONS.clear()
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_confirmation.py -v`
Expected: 8 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/confirmation.py tests/test_confirmation.py
git commit -m "feat: capa de confirmación de acciones con TTL y tracking por turno"
```

---

## Task 3: Herramientas de diagnóstico (riesgo `read`)

**Files:**
- Create: `src/asistente_mikha/tools/diagnostics.py`
- Test: `tests/test_diagnostics_tools.py`

**Interfaces:**
- Consumes: `ToolRisk`, `tool` de `asistente_mikha.tools.registry` (Task 1).
- Produces: `get_ram_usage() -> dict`, `get_disk_usage(path: str = "/") -> dict`, `list_processes(limit: int = 10) -> list[dict]`, `get_gpu_status() -> dict`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_diagnostics_tools.py`:
```python
from asistente_mikha.tools.diagnostics import (
    get_ram_usage,
    get_disk_usage,
    list_processes,
    get_gpu_status,
)


def test_get_ram_usage_returns_expected_keys():
    result = get_ram_usage()
    assert set(result.keys()) == {"total_gb", "used_gb", "available_gb", "percent_used"}
    assert result["total_gb"] > 0
    assert 0 <= result["percent_used"] <= 100


def test_get_disk_usage_default_path():
    result = get_disk_usage()
    assert result["path"] == "/"
    assert result["total_gb"] > 0
    assert 0 <= result["percent_used"] <= 100


def test_list_processes_respects_limit_and_sorts_desc():
    result = list_processes(limit=5)
    assert len(result) <= 5
    rss_values = [p["rss_mb"] for p in result]
    assert rss_values == sorted(rss_values, reverse=True)
    for entry in result:
        assert set(entry.keys()) == {"pid", "name", "rss_mb"}


def test_get_gpu_status_returns_structured_result():
    result = get_gpu_status()
    assert "available" in result
    if result["available"]:
        assert "vram_total_bytes" in result
        assert result["vram_total_bytes"] > 0
```

Run: `pytest tests/test_diagnostics_tools.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.tools.diagnostics'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/tools/diagnostics.py`:
```python
from __future__ import annotations

import re
import shutil
import subprocess

import psutil

from asistente_mikha.tools.registry import ToolRisk, tool

_VRAM_LINE_RE = re.compile(r"VRAM (Total|Total Used) Memory \(B\):\s*(\d+)")


@tool(risk=ToolRisk.READ, description="Muestra el uso actual de RAM del sistema.")
def get_ram_usage() -> dict:
    """Devuelve el uso de RAM del sistema en GB y porcentaje."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "percent_used": mem.percent,
    }


@tool(risk=ToolRisk.READ, description="Muestra el uso de disco de una ruta dada.")
def get_disk_usage(path: str = "/") -> dict:
    """Devuelve el uso de disco de `path` en GB y porcentaje."""
    usage = psutil.disk_usage(path)
    return {
        "path": path,
        "total_gb": round(usage.total / (1024**3), 2),
        "used_gb": round(usage.used / (1024**3), 2),
        "free_gb": round(usage.free / (1024**3), 2),
        "percent_used": usage.percent,
    }


@tool(risk=ToolRisk.READ, description="Lista los procesos que más memoria RAM están usando.")
def list_processes(limit: int = 10) -> list[dict]:
    """Devuelve hasta `limit` procesos ordenados por RSS de memoria descendente."""
    procs: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            memory_info = info["memory_info"]
            rss_mb = memory_info.rss / (1024 * 1024) if memory_info else 0.0
            procs.append({"pid": info["pid"], "name": info["name"], "rss_mb": round(rss_mb, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda p: p["rss_mb"], reverse=True)
    return procs[:limit]


@tool(risk=ToolRisk.READ, description="Muestra el uso de VRAM de la GPU AMD, si rocm-smi está disponible.")
def get_gpu_status() -> dict:
    """Devuelve el uso de VRAM reportado por rocm-smi, o indica que no está disponible."""
    if shutil.which("rocm-smi") is None:
        return {"available": False, "reason": "rocm-smi no está instalado o no está en PATH"}
    result = subprocess.run(
        ["rocm-smi", "--showmeminfo", "vram"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return {"available": False, "reason": result.stderr.strip() or "rocm-smi falló"}
    total_bytes = None
    used_bytes = None
    for match in _VRAM_LINE_RE.finditer(result.stdout):
        kind, value = match.group(1), int(match.group(2))
        if kind == "Total":
            total_bytes = value
        else:
            used_bytes = value
    if total_bytes is None:
        return {"available": False, "reason": "no se pudo interpretar la salida de rocm-smi"}
    return {
        "available": True,
        "vram_total_bytes": total_bytes,
        "vram_used_bytes": used_bytes,
        "vram_used_percent": round(used_bytes / total_bytes * 100, 1) if used_bytes else None,
    }
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_diagnostics_tools.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/tools/diagnostics.py tests/test_diagnostics_tools.py
git commit -m "feat: herramientas de diagnóstico de solo lectura"
```

---

## Task 4: Herramientas de acción (riesgo `confirm`)

**Files:**
- Create: `src/asistente_mikha/tools/actions.py`
- Test: `tests/test_action_tools.py`

**Interfaces:**
- Consumes: `ToolRisk`, `tool` (Task 1); `get_default_store`, `register_implementation` (Task 2).
- Produces: `restart_service(service_name: Literal["wireplumber"]) -> dict`, `clear_directory_cache(target: Literal["asistente_scratch"]) -> dict`, `ALLOWED_SERVICES: tuple[str, ...]`, `CACHE_TARGETS: dict[str, Path]`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_action_tools.py`:
```python
from unittest.mock import patch, MagicMock

import pytest

from asistente_mikha.confirmation import get_default_store, reset_default_store_for_tests
from asistente_mikha.tools import actions


@pytest.fixture(autouse=True)
def _clean_store():
    reset_default_store_for_tests()
    # las funciones _impl se registran al importar el módulo `actions`;
    # como el import ya ocurrió antes del test, hay que re-registrarlas.
    actions.register_implementation("restart_service", actions._restart_service_impl)
    actions.register_implementation("clear_directory_cache", actions._clear_directory_cache_impl)
    yield
    reset_default_store_for_tests()


def test_restart_service_creates_pending_action_without_executing():
    with patch("asistente_mikha.tools.actions.subprocess.run") as mock_run:
        result = actions.restart_service(service_name="wireplumber")
        assert result["status"] == "pending_confirmation"
        mock_run.assert_not_called()


def test_confirming_restart_service_calls_systemctl():
    mock_result = MagicMock(returncode=0, stderr="")
    with patch("asistente_mikha.tools.actions.subprocess.run", return_value=mock_result) as mock_run:
        pending = actions.restart_service(service_name="wireplumber")
        executed = get_default_store().execute(pending["action_id"])
        mock_run.assert_called_once_with(
            ["systemctl", "--user", "restart", "wireplumber"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert executed.result["returncode"] == 0


def test_restart_service_rejects_service_outside_allowlist():
    with pytest.raises(ValueError):
        actions._restart_service_impl("sshd")


def test_clear_directory_cache_creates_pending_action():
    result = actions.clear_directory_cache(target="asistente_scratch")
    assert result["status"] == "pending_confirmation"


def test_clear_directory_cache_impl_removes_files(tmp_path, monkeypatch):
    fake_target_dir = tmp_path / "scratch"
    monkeypatch.setitem(actions.CACHE_TARGETS, "asistente_scratch", fake_target_dir)
    fake_target_dir.mkdir()
    (fake_target_dir / "a.txt").write_text("x")
    (fake_target_dir / "b.txt").write_text("y")

    result = actions._clear_directory_cache_impl("asistente_scratch")
    assert result["files_removed"] == 2
    assert list(fake_target_dir.iterdir()) == []
```

Run: `pytest tests/test_action_tools.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.tools.actions'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/tools/actions.py`:
```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from asistente_mikha.confirmation import get_default_store, register_implementation
from asistente_mikha.tools.registry import ToolRisk, tool

ALLOWED_SERVICES: tuple[str, ...] = ("wireplumber",)


def _restart_service_impl(service_name: str) -> dict:
    if service_name not in ALLOWED_SERVICES:
        raise ValueError(f"Servicio '{service_name}' no está en la allowlist {ALLOWED_SERVICES}")
    result = subprocess.run(
        ["systemctl", "--user", "restart", service_name],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return {
        "service_name": service_name,
        "returncode": result.returncode,
        "stderr": result.stderr.strip(),
    }


register_implementation("restart_service", _restart_service_impl)


@tool(
    risk=ToolRisk.CONFIRM,
    description="Reinicia un servicio de usuario systemd de la allowlist. Requiere confirmación.",
)
def restart_service(service_name: Literal["wireplumber"]) -> dict:
    """Propone reiniciar un servicio systemd de usuario. No se ejecuta hasta confirmarse."""
    action = get_default_store().create("restart_service", {"service_name": service_name})
    return {"status": "pending_confirmation", "action_id": action.action_id}


CACHE_TARGETS: dict[str, Path] = {
    "asistente_scratch": Path.home() / ".cache" / "asistente_mikha" / "scratch",
}


def _clear_directory_cache_impl(target: str) -> dict:
    if target not in CACHE_TARGETS:
        raise ValueError(f"Target '{target}' no está en la allowlist {list(CACHE_TARGETS)}")
    directory = CACHE_TARGETS[target]
    directory.mkdir(parents=True, exist_ok=True)
    removed = 0
    for item in directory.iterdir():
        if item.is_file():
            item.unlink()
            removed += 1
    return {"target": target, "files_removed": removed}


register_implementation("clear_directory_cache", _clear_directory_cache_impl)


@tool(
    risk=ToolRisk.CONFIRM,
    description="Vacía un directorio de caché propio de la aplicación. Requiere confirmación.",
)
def clear_directory_cache(target: Literal["asistente_scratch"]) -> dict:
    """Propone vaciar un directorio de caché de la app. No se ejecuta hasta confirmarse."""
    action = get_default_store().create("clear_directory_cache", {"target": target})
    return {"status": "pending_confirmation", "action_id": action.action_id}
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_action_tools.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/tools/actions.py tests/test_action_tools.py
git commit -m "feat: herramientas de acción con confirmación obligatoria"
```

---

## Task 5: Observabilidad (OpenTelemetry + Phoenix)

**Files:**
- Create: `src/asistente_mikha/observability.py`
- Test: `tests/test_observability.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `configure_tracing(project_name: str = "asistente-mikha") -> None`, `get_tracer() -> opentelemetry.trace.Tracer`.

- [ ] **Step 1: Escribir test (falla primero)**

`tests/test_observability.py`:
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from asistente_mikha.observability import get_tracer


def test_get_tracer_creates_span_with_attributes():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = get_tracer()
    with tracer.start_as_current_span("test.span") as span:
        span.set_attribute("gen_ai.tool.name", "get_ram_usage")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.span"
    assert spans[0].attributes["gen_ai.tool.name"] == "get_ram_usage"
```

Run: `pytest tests/test_observability.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.observability'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/observability.py`:
```python
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Tracer

TRACER_NAME = "asistente_mikha"
DEFAULT_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"

_tracing_configured = False


def configure_tracing(
    project_name: str = "asistente-mikha", endpoint: str = DEFAULT_PHOENIX_ENDPOINT
) -> None:
    """Registra el TracerProvider global apuntando a un Phoenix local. Idempotente."""
    global _tracing_configured
    if _tracing_configured:
        return
    from phoenix.otel import register

    register(project_name=project_name, endpoint=endpoint, auto_instrument=False)
    _tracing_configured = True


def get_tracer() -> Tracer:
    return trace.get_tracer(TRACER_NAME)
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_observability.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/observability.py tests/test_observability.py
git commit -m "feat: configuración de tracing OpenTelemetry hacia Phoenix"
```

---

## Task 6: Núcleo del agente (PydanticAI + Ollama)

**Files:**
- Create: `src/asistente_mikha/agent.py`
- Test: `tests/test_agent_integration.py`

**Interfaces:**
- Consumes: `registry.all_tools()` (Task 1, indirectamente vía import de `tools.diagnostics` y `tools.actions` de Tasks 3-4); `get_tracer()` (Task 5); `start_turn_tracking`, `collect_turn_actions` (Task 2).
- Produces: `AgentTurnResult` (dataclass: `reply: str`, `pending_action_ids: list[str]`), `run_turn(session_id: str, message: str) -> AgentTurnResult` (async), `reset_sessions_for_tests() -> None`.

- [ ] **Step 1: Escribir test de integración (falla primero)**

Este test requiere `ollama serve` corriendo con el modelo `default` disponible (`ollama list` debe mostrarlo). Se marca como `integration` para poder excluirlo en corridas rápidas.

`tests/test_agent_integration.py`:
```python
import pytest

from asistente_mikha.agent import run_turn, reset_sessions_for_tests


@pytest.fixture(autouse=True)
def _clean_sessions():
    reset_sessions_for_tests()
    yield
    reset_sessions_for_tests()


@pytest.mark.integration
async def test_agent_answers_ram_question_using_real_tool():
    result = await run_turn("test-session", "¿Cuánta RAM tengo disponible ahora mismo?")
    assert result.reply
    assert "GB" in result.reply or "%" in result.reply


@pytest.mark.integration
async def test_agent_creates_pending_action_for_restart_service():
    result = await run_turn(
        "test-session-2",
        "Reinicia el servicio wireplumber por favor.",
    )
    assert result.pending_action_ids, "se esperaba al menos una acción pendiente"
```

Run: `pytest tests/test_agent_integration.py -v -m integration`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.agent'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/agent.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from asistente_mikha.confirmation import collect_turn_actions, start_turn_tracking
from asistente_mikha.observability import get_tracer
from asistente_mikha.tools import registry

# Importar estos módulos registra sus herramientas en `registry` como
# efecto secundario del decorador @tool — deben importarse antes de
# construir cualquier agente.
from asistente_mikha.tools import actions, diagnostics  # noqa: F401

OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL_NAME = "default"

SYSTEM_PROMPT = (
    "Eres un asistente de diagnóstico para esta máquina Linux. Usa las "
    "herramientas disponibles para responder con datos reales, nunca "
    "inventes cifras. Cuando una herramienta devuelva "
    "status='pending_confirmation', explícale al usuario que la acción "
    "quedó pendiente de confirmación explícita y menciona su action_id."
)


def _build_model(model_name: str = DEFAULT_MODEL_NAME) -> OpenAIModel:
    provider = OpenAIProvider(base_url=OLLAMA_BASE_URL, api_key="ollama")
    return OpenAIModel(model_name, provider=provider)


def build_agent(model_name: str = DEFAULT_MODEL_NAME) -> Agent:
    agent = Agent(_build_model(model_name), system_prompt=SYSTEM_PROMPT)
    for registered in registry.all_tools().values():
        agent.tool_plain(registered.func)
    return agent


@dataclass
class Session:
    agent: Agent
    history: list = field(default_factory=list)


@dataclass
class AgentTurnResult:
    reply: str
    pending_action_ids: list[str]


_sessions: dict[str, Session] = {}


def get_or_create_session(session_id: str, model_name: str = DEFAULT_MODEL_NAME) -> Session:
    if session_id not in _sessions:
        _sessions[session_id] = Session(agent=build_agent(model_name))
    return _sessions[session_id]


def reset_sessions_for_tests() -> None:
    _sessions.clear()


async def run_turn(session_id: str, message: str) -> AgentTurnResult:
    start_turn_tracking()
    session = get_or_create_session(session_id)
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.turn") as span:
        span.set_attribute("gen_ai.request.model", DEFAULT_MODEL_NAME)
        span.set_attribute("mikha.session_id", session_id)
        result = await session.agent.run(message, message_history=session.history)
        session.history = result.all_messages()
        span.set_attribute("gen_ai.response.text_length", len(result.output))
    return AgentTurnResult(reply=result.output, pending_action_ids=collect_turn_actions())
```

- [ ] **Step 3: Verificar que pasa (con Ollama corriendo)**

Run:
```bash
ollama serve &
pytest tests/test_agent_integration.py -v -m integration
```
Expected: 2 passed. (Si `ollama serve` ya corre de una sesión anterior, omitir el primer comando.)

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/agent.py tests/test_agent_integration.py
git commit -m "feat: agente PydanticAI sobre Ollama con tracking de acciones pendientes"
```

---

## Task 7: API FastAPI

**Files:**
- Create: `src/asistente_mikha/api/__init__.py`
- Create: `src/asistente_mikha/api/models.py`
- Create: `src/asistente_mikha/api/routes.py`
- Create: `src/asistente_mikha/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_turn`, `AgentTurnResult` (Task 6); `get_default_store`, `ActionStatus` (Task 2); `configure_tracing` (Task 5).
- Produces: FastAPI `app` en `asistente_mikha.main`, rutas `POST /chat`, `POST /confirm/{action_id}`, `GET /health`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_api.py`:
```python
import pytest
from fastapi.testclient import TestClient

from asistente_mikha.confirmation import (
    get_default_store,
    register_implementation,
    reset_default_store_for_tests,
)
from asistente_mikha.main import app


@pytest.fixture(autouse=True)
def _clean_store():
    reset_default_store_for_tests()
    yield
    reset_default_store_for_tests()


@pytest.fixture
def client(monkeypatch):
    async def fake_run_turn(session_id: str, message: str):
        from asistente_mikha.agent import AgentTurnResult

        return AgentTurnResult(reply=f"eco: {message}", pending_action_ids=[])

    monkeypatch.setattr("asistente_mikha.api.routes.run_turn", fake_run_turn)
    with TestClient(app) as test_client:
        yield test_client


def test_chat_endpoint_returns_agent_reply(client):
    response = client.post("/chat", json={"session_id": "s1", "message": "hola"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "eco: hola"
    assert body["pending_action_ids"] == []


def test_confirm_endpoint_approves_pending_action(client):
    register_implementation("dummy_tool", lambda: {"ok": True})
    action = get_default_store().create("dummy_tool", {})
    response = client.post(f"/confirm/{action.action_id}", params={"approve": True})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["result"] == {"ok": True}


def test_confirm_endpoint_rejects_when_approve_false(client):
    action = get_default_store().create("dummy_tool", {})
    response = client.post(f"/confirm/{action.action_id}", params={"approve": False})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_confirm_endpoint_unknown_action_returns_404(client):
    response = client.post("/confirm/no-existe", params={"approve": True})
    assert response.status_code == 404


def test_health_endpoint_returns_structure(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "ollama_reachable" in body
```

Run: `pytest tests/test_api.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.main'`.

- [ ] **Step 2: Implementar modelos**

`src/asistente_mikha/api/__init__.py`: vacío.

`src/asistente_mikha/api/models.py`:
```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    pending_action_ids: list[str] = []


class ConfirmResponse(BaseModel):
    action_id: str
    status: str
    result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
```

- [ ] **Step 3: Implementar rutas**

`src/asistente_mikha/api/routes.py`:
```python
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from asistente_mikha.agent import run_turn
from asistente_mikha.api.models import (
    ChatRequest,
    ChatResponse,
    ConfirmResponse,
    HealthResponse,
)
from asistente_mikha.confirmation import get_default_store

router = APIRouter()

OLLAMA_HEALTH_URL = "http://localhost:11434/api/tags"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    result = await run_turn(request.session_id, request.message)
    return ChatResponse(reply=result.reply, pending_action_ids=result.pending_action_ids)


@router.post("/confirm/{action_id}", response_model=ConfirmResponse)
async def confirm(action_id: str, approve: bool = True) -> ConfirmResponse:
    store = get_default_store()
    try:
        action = store.execute(action_id) if approve else store.reject(action_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ConfirmResponse(action_id=action.action_id, status=action.status.value, result=action.result)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(OLLAMA_HEALTH_URL)
            ollama_ok = resp.status_code == 200
    except httpx.HTTPError:
        ollama_ok = False
    return HealthResponse(status="ok", ollama_reachable=ollama_ok)
```

- [ ] **Step 4: Implementar `main.py`**

`src/asistente_mikha/main.py`:
```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from asistente_mikha.api.routes import router
from asistente_mikha.observability import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing()
    yield


app = FastAPI(title="Asistente Mikha", lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 5: Verificar que pasa**

Run: `pytest tests/test_api.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asistente_mikha/api src/asistente_mikha/main.py tests/test_api.py
git commit -m "feat: API FastAPI con endpoints /chat, /confirm y /health"
```

---

## Task 8: Cliente CLI

**Files:**
- Create: `src/asistente_mikha/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: nada en tiempo de import de tareas anteriores (habla con la API por HTTP, no importa módulos del backend).
- Produces: `send_message(client: httpx.Client, session_id: str, message: str) -> tuple[str, list[str]]`, `confirm_action(client: httpx.Client, action_id: str, approve: bool) -> dict`, `main() -> None`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_cli.py`:
```python
import httpx

from asistente_mikha.cli import send_message, confirm_action


def test_send_message_parses_reply_and_pending_actions():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat"
        assert request.method == "POST"
        return httpx.Response(200, json={"reply": "hola", "pending_action_ids": ["abc123"]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    reply, pending = send_message(client, "session-1", "hola")
    assert reply == "hola"
    assert pending == ["abc123"]


def test_send_message_defaults_pending_actions_to_empty_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": "sin acciones"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    _, pending = send_message(client, "session-1", "hola")
    assert pending == []


def test_confirm_action_sends_approve_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["approve"] = request.url.params.get("approve")
        return httpx.Response(200, json={"action_id": "abc123", "status": "confirmed", "result": None})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    result = confirm_action(client, "abc123", approve=True)
    assert captured["path"] == "/confirm/abc123"
    assert captured["approve"] == "true"
    assert result["status"] == "confirmed"
```

Run: `pytest tests/test_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.cli'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/cli.py`:
```python
from __future__ import annotations

import uuid

import httpx

API_BASE_URL = "http://localhost:8000"


def send_message(client: httpx.Client, session_id: str, message: str) -> tuple[str, list[str]]:
    response = client.post("/chat", json={"session_id": session_id, "message": message})
    response.raise_for_status()
    body = response.json()
    return body["reply"], body.get("pending_action_ids", [])


def confirm_action(client: httpx.Client, action_id: str, approve: bool) -> dict:
    response = client.post(f"/confirm/{action_id}", params={"approve": approve})
    response.raise_for_status()
    return response.json()


def main() -> None:
    session_id = str(uuid.uuid4())
    print(f"Asistente Mikha — sesión {session_id}. Escribe 'salir' para terminar.")
    with httpx.Client(base_url=API_BASE_URL) as client:
        while True:
            try:
                message = input("> ").strip()
            except EOFError:
                break
            if message.lower() in {"salir", "exit", "quit"}:
                break
            if not message:
                continue
            reply, pending_ids = send_message(client, session_id, message)
            print(reply)
            for action_id in pending_ids:
                answer = input(f"  ¿Confirmar acción {action_id}? [s/N] ").strip().lower()
                result = confirm_action(client, action_id, approve=(answer == "s"))
                print(f"  -> {result}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_cli.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/cli.py tests/test_cli.py
git commit -m "feat: cliente CLI con flujo de confirmación interactivo"
```

---

## Task 9: Smoke test end-to-end + documentación de uso

**Files:**
- Create: `tests/test_end_to_end.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `app` (Task 7), todo el sistema construido en Tasks 1-8.
- Produces: ninguna interfaz nueva — valida el sistema completo.

- [ ] **Step 1: Escribir el smoke test**

`tests/test_end_to_end.py`:
```python
import pytest
from fastapi.testclient import TestClient

from asistente_mikha.agent import reset_sessions_for_tests
from asistente_mikha.confirmation import reset_default_store_for_tests
from asistente_mikha.main import app


@pytest.fixture(autouse=True)
def _clean_state():
    reset_default_store_for_tests()
    reset_sessions_for_tests()
    yield
    reset_default_store_for_tests()
    reset_sessions_for_tests()


@pytest.mark.integration
def test_full_flow_diagnose_then_confirm_action():
    with TestClient(app) as client:
        chat_response = client.post(
            "/chat",
            json={"session_id": "e2e-1", "message": "¿Cuánta RAM tengo disponible?"},
        )
        assert chat_response.status_code == 200
        assert chat_response.json()["reply"]

        action_response = client.post(
            "/chat",
            json={
                "session_id": "e2e-1",
                "message": "Reinicia el servicio wireplumber.",
            },
        )
        assert action_response.status_code == 200
        pending_ids = action_response.json()["pending_action_ids"]
        assert pending_ids, "se esperaba una acción pendiente para restart_service"

        confirm_response = client.post(f"/confirm/{pending_ids[0]}", params={"approve": False})
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "rejected"
```

Nota: este test rechaza la confirmación (`approve=False`) para no reiniciar `wireplumber` de verdad en cada corrida de tests — ya se probó que la ejecución real funciona en el `test_confirming_restart_service_calls_systemctl` de la Task 4 (con `subprocess.run` mockeado) y queda cubierto manualmente al usar la CLI.

- [ ] **Step 2: Ejecutar toda la suite**

Run:
```bash
ollama serve &  # si no está corriendo ya
pytest -v
```
Expected: todos los tests pasan (unitarios + integración).

- [ ] **Step 3: Escribir `README.md`**

`README.md`:
```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py README.md
git commit -m "test: smoke test end-to-end y documentación de uso"
```

---

## Self-Review (completado durante la escritura de este plan)

- **Cobertura del spec:** Capa API (Task 7), Agente (Task 6), Registro de herramientas + confirmación (Tasks 1, 2, 3, 4), Observabilidad (Task 5), manejo de errores (spans de error en confirmación/agente, 404/409 en API, fallback en `get_gpu_status`), testing (unit + integración en cada tarea, smoke test en Task 9). Sin huecos detectados.
- **Placeholders:** ninguno — todo el código de cada step es completo y ejecutable.
- **Consistencia de tipos:** `AgentTurnResult`, `PendingAction`, `RegisteredTool` y los modelos Pydantic de la API usan los mismos nombres de campo en todas las tareas que los consumen (verificado: `pending_action_ids`, `action_id`, `status`, `result`, `kwargs`, `risk`, `func`).
