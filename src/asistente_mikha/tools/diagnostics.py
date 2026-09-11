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
