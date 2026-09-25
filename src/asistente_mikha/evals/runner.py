from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import httpx

from asistente_mikha.config import get_ollama_base_url
from asistente_mikha.evals.cases import EvalCase
from asistente_mikha.evals.checks import (
    Verdict,
    argumentos_correctos,
    efecto_correcto,
    sin_efecto,
    eligio_herramienta,
    fundamentada,
    respuesta_ok,
)
from asistente_mikha.evals.variants import TurnOutcome, ejecutar_turno
from asistente_mikha.memory import tools as memory_tools
from asistente_mikha.memory.tasks import add_task

# Un turno normal tarda 14-20s; el doble de eso da margen a two_step sin
# dejar que una corrida colgada frene un barrido de horas.
TIMEOUT_SEGUNDOS = 90.0

DIMENSIONES = ("herramienta", "argumentos", "efecto", "respuesta", "fundamentada")


def preparar_vault(vault: Path, prepara: dict[str, Any]) -> None:
    for nombre, tareas in (prepara.get("tareas") or {}).items():
        for texto in tareas:
            add_task(vault, nombre, texto)


def _efecto(vault: Path, espera) -> Verdict:
    encontrado = efecto_correcto(vault, espera.archivos)
    if not encontrado.ok:
        return encontrado
    return sin_efecto(vault, espera.sin_archivos)


def veredictos_de(caso: EvalCase, resultado: TurnOutcome, vault: Path) -> dict[str, dict]:
    espera = caso.espera
    crudos = {
        "herramienta": eligio_herramienta(resultado.llamadas, espera.herramienta),
        "argumentos": argumentos_correctos(
            resultado.llamadas, espera.herramienta, espera.argumentos
        ),
        "efecto": _efecto(vault, espera),
        "respuesta": respuesta_ok(
            resultado.respuesta, espera.respuesta_contiene, espera.respuesta_pregunta
        ),
        # Una dimension que el caso no pidio no puede hacerlo fallar.
        "fundamentada": (
            fundamentada(resultado.respuesta, resultado.llamadas)
            if espera.fundamentada
            else Verdict(True)
        ),
    }
    return {nombre: {"ok": v.ok, "motivo": v.motivo} for nombre, v in crudos.items()}


def _fila_de_error(caso: EvalCase, modelo: str, variante: str, repeticion: int, error: str) -> dict:
    return {
        "modelo": modelo,
        "variante": variante,
        "caso": caso.id,
        "repeticion": repeticion,
        "veredictos": {d: {"ok": False, "motivo": "la corrida no termino"} for d in DIMENSIONES},
        "latencia_s": 0.0,
        "llamadas": [],
        "respuesta": "",
        "error": error,
    }


async def ejecutar_corrida(
    caso: EvalCase, modelo: str, variante: str, repeticion: int, raiz: Path
) -> dict:
    vault = Path(tempfile.mkdtemp(dir=raiz, prefix=f"{caso.id}-"))
    os.environ["MIKHA_VAULT_PATH"] = str(vault)
    # El indexador es un global cacheado: sin esto la corrida siguiente
    # seguiria escribiendo en el vault de la anterior.
    memory_tools.reset_indexer_for_tests()
    preparar_vault(vault, caso.prepara)

    empezo = time.perf_counter()
    try:
        resultado = await asyncio.wait_for(
            ejecutar_turno(modelo, variante, caso.mensaje), timeout=TIMEOUT_SEGUNDOS
        )
    except asyncio.TimeoutError:
        return _fila_de_error(caso, modelo, variante, repeticion, f"timeout tras {TIMEOUT_SEGUNDOS}s")
    except Exception:
        return _fila_de_error(caso, modelo, variante, repeticion, traceback.format_exc(limit=3))

    return {
        "modelo": modelo,
        "variante": variante,
        "caso": caso.id,
        "repeticion": repeticion,
        "veredictos": veredictos_de(caso, resultado, vault),
        "latencia_s": round(time.perf_counter() - empezo, 2),
        "llamadas": [{"name": ll.name, "args": ll.args} for ll in resultado.llamadas],
        "respuesta": resultado.respuesta,
        "error": None,
    }


def clave_de(fila: dict) -> tuple[str, str, str, int]:
    return (fila["modelo"], fila["variante"], fila["caso"], fila["repeticion"])


def claves_hechas(salida: Path) -> set[tuple[str, str, str, int]]:
    if not salida.exists():
        return set()
    hechas = set()
    for linea in salida.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            hechas.add(clave_de(json.loads(linea)))
    return hechas


def modelos_faltantes(modelos: list[str]) -> list[str]:
    """Los que Ollama no tiene descargados. Se chequea ANTES del barrido.

    Fallar a las dos horas porque falta un modelo es inaceptable.
    """
    base = get_ollama_base_url()
    raiz = base[: -len("/v1")] if base.endswith("/v1") else base
    try:
        respuesta = httpx.get(f"{raiz}/api/tags", timeout=5.0)
        respuesta.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError(f"no se pudo consultar Ollama en {raiz}: {error}") from error
    disponibles = {m["name"] for m in respuesta.json().get("models", [])}
    disponibles |= {n.split(":")[0] for n in disponibles}
    return [m for m in modelos if m not in disponibles]


async def barrer(
    casos: list[EvalCase],
    modelos: list[str],
    variantes: list[str],
    repeticiones: int,
    salida: Path,
) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    hechas = claves_hechas(salida)
    vault_original = os.environ.get("MIKHA_VAULT_PATH")

    with tempfile.TemporaryDirectory(prefix="mikha-eval-") as raiz_tmp:
        raiz = Path(raiz_tmp)
        try:
            for modelo in modelos:
                for variante in variantes:
                    for caso in casos:
                        for repeticion in range(repeticiones):
                            if (modelo, variante, caso.id, repeticion) in hechas:
                                continue
                            fila = await ejecutar_corrida(caso, modelo, variante, repeticion, raiz)
                            # Se escribe apenas termina: una interrupcion no
                            # cuesta el barrido entero.
                            with salida.open("a", encoding="utf-8") as f:
                                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                            estado = "ERROR" if fila["error"] else (
                                "ok" if all(v["ok"] for v in fila["veredictos"].values()) else "falla"
                            )
                            print(
                                f"{modelo} {variante} {caso.id} #{repeticion} "
                                f"{estado} {fila['latencia_s']}s",
                                flush=True,
                            )
        finally:
            if vault_original is None:
                os.environ.pop("MIKHA_VAULT_PATH", None)
            else:
                os.environ["MIKHA_VAULT_PATH"] = vault_original
            memory_tools.reset_indexer_for_tests()
