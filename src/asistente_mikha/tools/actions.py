from __future__ import annotations

from pathlib import Path
from typing import Literal

from jeepney import DBusAddress, MessageType, new_method_call
from jeepney.io.blocking import open_dbus_connection

from asistente_mikha.confirmation import get_default_store, register_implementation
from asistente_mikha.tools.registry import ToolRisk, tool

ALLOWED_SERVICES: tuple[str, ...] = ("wireplumber",)

# Se habla D-Bus directo (via jeepney) en vez de invocar el binario
# `systemctl`: dentro de un contenedor Docker, systemctl --user usa un
# socket privado de alto rendimiento que solo es compatible entre
# versiones identicas de systemd, y falla si el systemd del contenedor
# no coincide exactamente con el del host. El D-Bus estandar de sesion
# si es compatible entre versiones, tanto nativo como en Docker.
_SYSTEMD_MANAGER = DBusAddress(
    "/org/freedesktop/systemd1",
    bus_name="org.freedesktop.systemd1",
    interface="org.freedesktop.systemd1.Manager",
)


def _restart_service_impl(service_name: str) -> dict:
    if service_name not in ALLOWED_SERVICES:
        raise ValueError(f"Servicio '{service_name}' no está en la allowlist {ALLOWED_SERVICES}")
    unit_name = f"{service_name}.service"
    with open_dbus_connection(bus="SESSION") as connection:
        msg = new_method_call(_SYSTEMD_MANAGER, "RestartUnit", "ss", (unit_name, "replace"))
        reply = connection.send_and_get_reply(msg)
    if reply.header.message_type == MessageType.error:
        error_text = str(reply.body[0]) if reply.body else "error desconocido"
        return {"service_name": service_name, "returncode": 1, "stderr": error_text}
    return {"service_name": service_name, "returncode": 0, "stderr": ""}


register_implementation("restart_service", _restart_service_impl)


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


def clear_directory_cache(target: Literal["asistente_scratch"]) -> dict:
    """Propone vaciar un directorio de caché de la app. No se ejecuta hasta confirmarse."""
    action = get_default_store().create("clear_directory_cache", {"target": target})
    return {"status": "pending_confirmation", "action_id": action.action_id}


@tool(
    risk=ToolRisk.CONFIRM,
    description=(
        "Ejecuta una acción controlada del sistema: reiniciar un servicio "
        "('wireplumber') o vaciar una caché ('asistente_scratch'). Requiere "
        "confirmación."
    ),
)
def system_action(
    action: Literal["restart_service", "clear_directory_cache"], target: str
) -> dict:
    """Propone una acción de sistema. No se ejecuta hasta confirmarse."""
    # Las allowlists se leen aca y no al importar: son el estado actual del
    # modulo, que los tests sustituyen.
    allowed_by_action: dict[str, list[str]] = {
        "restart_service": list(ALLOWED_SERVICES),
        "clear_directory_cache": list(CACHE_TARGETS),
    }
    allowed = allowed_by_action.get(action)
    if allowed is None:
        return {
            "status": "invalid_action",
            "action": action,
            "allowed": list(allowed_by_action),
        }
    # Se valida al proponer, no al ejecutar: pedirle confirmacion al usuario
    # para algo que ya sabemos que va a fallar no le sirve a nadie.
    if target not in allowed:
        return {
            "status": "invalid_target",
            "action": action,
            "target": target,
            "allowed": allowed,
        }
    if action == "restart_service":
        return restart_service(service_name=target)
    return clear_directory_cache(target=target)
