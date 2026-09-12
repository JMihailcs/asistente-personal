from __future__ import annotations

from pathlib import Path
from typing import Literal

import psutil

from asistente_mikha.tools.registry import ToolRisk, tool

# Se lee sysfs en vez de invocar `rocm-smi`: sysfs esta disponible tal cual
# dentro de un contenedor (sin montar ROCm ni pasar dispositivos), mientras
# que rocm-smi vive en /opt/rocm del host y no existe en la imagen. Ademas
# evita un subproceso por consulta.
DRM_DEVICES_GLOB = "/sys/class/drm/card*/device"


def get_ram_usage() -> dict:
    """Devuelve el uso de RAM del sistema en GB y porcentaje."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 2),
        "used_gb": round(mem.used / (1024**3), 2),
        "available_gb": round(mem.available / (1024**3), 2),
        "percent_used": mem.percent,
    }


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


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def get_gpu_status() -> dict:
    """Devuelve el uso de VRAM leido de sysfs, o indica que no esta disponible."""
    for device in sorted(Path("/").glob(DRM_DEVICES_GLOB.lstrip("/"))):
        total_bytes = _read_int(device / "mem_info_vram_total")
        if not total_bytes:
            continue
        used_bytes = _read_int(device / "mem_info_vram_used")
        return {
            "available": True,
            "vram_total_bytes": total_bytes,
            "vram_used_bytes": used_bytes,
            "vram_used_percent": (
                round(used_bytes / total_bytes * 100, 1) if used_bytes else None
            ),
        }
    return {
        "available": False,
        "reason": "no se encontro una GPU con informacion de VRAM en sysfs",
    }


@tool(
    risk=ToolRisk.READ,
    description="Diagnostico del sistema: RAM, disco, procesos o GPU.",
)
def diagnostics(
    check: Literal["ram", "disk", "processes", "gpu"],
    path: str = "/",
    limit: int = 10,
) -> dict:
    """Devuelve el diagnostico solicitado: 'ram', 'disk', 'processes' o 'gpu'."""
    if check == "ram":
        return {"status": "ok", "check": "ram", **get_ram_usage()}
    if check == "disk":
        return {"status": "ok", "check": "disk", **get_disk_usage(path)}
    if check == "processes":
        return {"status": "ok", "check": "processes", "processes": list_processes(limit)}
    if check == "gpu":
        gpu = get_gpu_status()
        if not gpu.pop("available"):
            return {"status": "unavailable", "check": "gpu", **gpu}
        return {"status": "ok", "check": "gpu", **gpu}
    return {
        "status": "invalid_action",
        "check": check,
        "allowed": ["ram", "disk", "processes", "gpu"],
    }
