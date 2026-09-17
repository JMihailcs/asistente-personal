from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from asistente_mikha.evals.runner import DIMENSIONES


def cargar_filas(salida: Path) -> list[dict]:
    return [
        json.loads(linea)
        for linea in salida.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]


def agregar(filas: list[dict], por: str) -> dict[str, dict]:
    agrupadas: dict[str, list[dict]] = defaultdict(list)
    for fila in filas:
        agrupadas[fila[por]].append(fila)

    agregado: dict[str, dict] = {}
    for clave, grupo in agrupadas.items():
        resumen: dict[str, float] = {"corridas": len(grupo)}
        for dimension in DIMENSIONES:
            aciertos = sum(1 for f in grupo if f["veredictos"][dimension]["ok"])
            resumen[dimension] = round(aciertos / len(grupo), 3)
        resumen["latencia_mediana"] = round(
            statistics.median(f["latencia_s"] for f in grupo), 2
        )
        agregado[clave] = resumen
    return agregado


def tabla_markdown(agregado: dict[str, dict], por: str) -> str:
    encabezado = f"| {por} | corridas | " + " | ".join(DIMENSIONES) + " | latencia mediana |"
    separador = "|" + "---|" * (len(DIMENSIONES) + 3)
    filas = [encabezado, separador]
    for clave in sorted(agregado):
        resumen = agregado[clave]
        celdas = " | ".join(f"{resumen[d]:.0%}" for d in DIMENSIONES)
        filas.append(
            f"| {clave} | {resumen['corridas']} | {celdas} | {resumen['latencia_mediana']}s |"
        )
    return "\n".join(filas)


def fallos(filas: list[dict], limite: int = 30) -> list[str]:
    encontrados: list[str] = []
    for fila in filas:
        origen = f"{fila['modelo']} / {fila['variante']} / {fila['caso']} #{fila['repeticion']}"
        if fila.get("error"):
            encontrados.append(f"{origen}: ERROR {fila['error'].splitlines()[-1]}")
            continue
        for dimension in DIMENSIONES:
            veredicto = fila["veredictos"][dimension]
            if not veredicto["ok"]:
                encontrados.append(f"{origen}: {dimension} — {veredicto['motivo']}")
    return encontrados[:limite]


def reporte_completo(filas: list[dict], por: str) -> str:
    partes = [
        f"# Reporte de evals (por {por})",
        "",
        tabla_markdown(agregar(filas, por), por),
        "",
        "## Fallos concretos",
        "",
    ]
    lista = fallos(filas)
    if lista:
        partes.extend(f"- {f}" for f in lista)
    else:
        partes.append("Ninguno.")
    return "\n".join(partes)
