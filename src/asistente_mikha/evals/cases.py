from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SIN_HERRAMIENTA = "ninguna"
# El caso no exige ni prohibe llamar herramientas: solo mide el efecto.
CUALQUIER_HERRAMIENTA = "cualquiera"

_CLAVES_CASO = {"id", "mensaje", "prepara", "espera"}
_CLAVES_ESPERA = {
    "herramienta",
    "argumentos",
    "archivos",
    "sin_archivos",
    "respuesta_contiene",
    "respuesta_pregunta",
    "fundamentada",
}
_CLAVES_ARCHIVO = {"patron", "contiene"}


class CaseError(ValueError):
    """Un caso mal escrito. El mensaje siempre nombra el archivo y el campo."""


@dataclass(frozen=True)
class ExpectedFile:
    patron: str
    contiene: str


@dataclass(frozen=True)
class Expectation:
    herramienta: str
    argumentos: dict[str, Any] = field(default_factory=dict)
    archivos: list[ExpectedFile] = field(default_factory=list)
    sin_archivos: list[str] = field(default_factory=list)
    respuesta_contiene: list[str] = field(default_factory=list)
    respuesta_pregunta: bool = False
    fundamentada: bool = False


@dataclass(frozen=True)
class EvalCase:
    id: str
    mensaje: str
    espera: Expectation
    prepara: dict[str, Any] = field(default_factory=dict)


def _exigir(data: dict, clave: str, origen: str) -> Any:
    if clave not in data or data[clave] in (None, ""):
        raise CaseError(f"{origen}: falta el campo obligatorio '{clave}'")
    return data[clave]


def _rechazar_desconocidas(data: dict, permitidas: set[str], origen: str, donde: str) -> None:
    # Un typo silencioso apagaria un chequeo sin que nadie se entere.
    sobrantes = sorted(set(data) - permitidas)
    if sobrantes:
        raise CaseError(f"{origen}: claves desconocidas en {donde}: {', '.join(sobrantes)}")


def load_case(data: dict, origen: str) -> EvalCase:
    if not isinstance(data, dict):
        raise CaseError(f"{origen}: el caso tiene que ser un mapeo, no {type(data).__name__}")
    _rechazar_desconocidas(data, _CLAVES_CASO, origen, "el caso")

    identificador = _exigir(data, "id", origen)
    mensaje = _exigir(data, "mensaje", origen)
    espera_raw = _exigir(data, "espera", origen)
    if not isinstance(espera_raw, dict):
        raise CaseError(f"{origen}: 'espera' tiene que ser un mapeo")
    _rechazar_desconocidas(espera_raw, _CLAVES_ESPERA, origen, "'espera'")

    herramienta = _exigir(espera_raw, "herramienta", origen)

    argumentos_raw = espera_raw.get("argumentos")
    if argumentos_raw is not None:
        if not isinstance(argumentos_raw, dict):
            raise CaseError(f"{origen}: 'argumentos' tiene que ser un mapeo")
        argumentos = dict(argumentos_raw)
    else:
        argumentos = {}

    archivos_raw = espera_raw.get("archivos")
    archivos = []
    if archivos_raw is not None:
        if not isinstance(archivos_raw, list):
            raise CaseError(f"{origen}: 'archivos' tiene que ser una lista")
        for entrada in archivos_raw:
            if not isinstance(entrada, dict):
                raise CaseError(f"{origen}: cada entrada de 'archivos' tiene que ser un mapeo")
            _rechazar_desconocidas(entrada, _CLAVES_ARCHIVO, origen, "'archivos'")
            archivos.append(
                ExpectedFile(
                    patron=_exigir(entrada, "patron", origen),
                    contiene=_exigir(entrada, "contiene", origen),
                )
            )

    sin_archivos_raw = espera_raw.get("sin_archivos")
    if sin_archivos_raw is not None:
        if not isinstance(sin_archivos_raw, list):
            raise CaseError(f"{origen}: 'sin_archivos' tiene que ser una lista")
        sin_archivos = list(sin_archivos_raw)
    else:
        sin_archivos = []

    respuesta_contiene_raw = espera_raw.get("respuesta_contiene")
    if respuesta_contiene_raw is not None:
        if not isinstance(respuesta_contiene_raw, list):
            raise CaseError(f"{origen}: 'respuesta_contiene' tiene que ser una lista")
        respuesta_contiene = list(respuesta_contiene_raw)
    else:
        respuesta_contiene = []

    espera = Expectation(
        herramienta=herramienta,
        argumentos=argumentos,
        archivos=archivos,
        sin_archivos=sin_archivos,
        respuesta_contiene=respuesta_contiene,
        respuesta_pregunta=bool(espera_raw.get("respuesta_pregunta", False)),
        fundamentada=bool(espera_raw.get("fundamentada", False)),
    )

    prepara_raw = data.get("prepara")
    if prepara_raw is not None:
        if not isinstance(prepara_raw, dict):
            raise CaseError(f"{origen}: 'prepara' tiene que ser un mapeo")
        prepara = dict(prepara_raw)
    else:
        prepara = {}

    return EvalCase(
        id=identificador,
        mensaje=mensaje,
        espera=espera,
        prepara=prepara,
    )


def load_cases(directorio: Path) -> list[EvalCase]:
    casos: list[EvalCase] = []
    vistos: dict[str, str] = {}
    for archivo in sorted(directorio.glob("*.yaml")):
        data = yaml.safe_load(archivo.read_text(encoding="utf-8"))
        caso = load_case(data, origen=archivo.name)
        if caso.id in vistos:
            raise CaseError(
                f"{archivo.name}: el id '{caso.id}' ya lo usa {vistos[caso.id]}"
            )
        vistos[caso.id] = archivo.name
        casos.append(caso)
    casos.sort(key=lambda c: c.id)
    return casos
