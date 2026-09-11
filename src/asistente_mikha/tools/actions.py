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
