from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from asistente_mikha.evals.cases import CUALQUIER_HERRAMIENTA, SIN_HERRAMIENTA, ExpectedFile


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    result: Any = None


@dataclass(frozen=True)
class Verdict:
    ok: bool
    motivo: str = ""


def normalizar(texto: str) -> str:
    """Minusculas, sin acentos y con los espacios colapsados.

    'Idea de negocio' e 'idea de NEGOCIO' son la misma lista: el vault las
    guarda en el mismo archivo. Comparar crudo castigaria al modelo por algo
    que el sistema ya trata como equivalente.
    """
    plano = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


def extraer_llamadas(messages: list) -> list[ToolCall]:
    """Saca las llamadas reales del historial, con su resultado.

    Se leen los `ToolCallPart` del historial y no el texto de la respuesta:
    lo que interesa es lo que el modelo hizo, no lo que dice que hizo.
    """
    resultados: dict[str, Any] = {}
    for mensaje in messages:
        for parte in getattr(mensaje, "parts", []):
            if getattr(parte, "part_kind", None) == "tool-return":
                resultados[parte.tool_call_id] = parte.content

    llamadas: list[ToolCall] = []
    for mensaje in messages:
        for parte in getattr(mensaje, "parts", []):
            if getattr(parte, "part_kind", None) != "tool-call":
                continue
            try:
                args = parte.args_as_dict()
            except Exception:
                # Un modelo puede emitir argumentos que no son JSON valido.
                # Eso es exactamente un fallo a medir, no un crash del arnes.
                args = {}
            llamadas.append(
                ToolCall(
                    name=parte.tool_name,
                    args=args,
                    result=resultados.get(parte.tool_call_id),
                )
            )
    return llamadas


def eligio_herramienta(llamadas: list[ToolCall], esperada: str) -> Verdict:
    nombres = [ll.name for ll in llamadas]
    if esperada == CUALQUIER_HERRAMIENTA:
        return Verdict(True)
    if esperada == SIN_HERRAMIENTA:
        if nombres:
            return Verdict(False, f"no correspondia ninguna y llamo a {', '.join(nombres)}")
        return Verdict(True)
    if not nombres:
        return Verdict(False, f"se esperaba '{esperada}' y no llamo a ninguna")
    if esperada not in nombres:
        return Verdict(False, f"se esperaba '{esperada}' y llamo a {', '.join(nombres)}")
    return Verdict(True)


def argumentos_correctos(
    llamadas: list[ToolCall], esperada: str, esperados: dict[str, Any]
) -> Verdict:
    if not esperados:
        return Verdict(True)
    candidatas = [ll for ll in llamadas if ll.name == esperada]
    if not candidatas:
        return Verdict(False, f"no hay ninguna llamada a '{esperada}' para revisar")

    # Basta con que UNA llamada traiga los argumentos pedidos: un modelo que
    # reintenta y acierta en el segundo intento acerto.
    faltantes: list[str] = []
    for llamada in candidatas:
        problemas = []
        for clave, valor in esperados.items():
            if clave not in llamada.args:
                problemas.append(f"falta '{clave}'")
            elif normalizar(llamada.args[clave]) != normalizar(valor):
                problemas.append(f"'{clave}' es '{llamada.args[clave]}' y se esperaba '{valor}'")
        if not problemas:
            return Verdict(True)
        faltantes = problemas
    return Verdict(False, "; ".join(faltantes))


def efecto_correcto(vault: Path, esperados: list[ExpectedFile]) -> Verdict:
    for esperado in esperados:
        encontrados = sorted(vault.glob(esperado.patron))
        if not encontrados:
            return Verdict(False, f"ningun archivo coincide con '{esperado.patron}'")
        texto = "\n".join(normalizar(f.read_text(encoding="utf-8")) for f in encontrados)
        if normalizar(esperado.contiene) not in texto:
            return Verdict(False, f"'{esperado.contiene}' no aparece en '{esperado.patron}'")
    return Verdict(True)


def sin_efecto(vault: Path, prohibidos: list[str]) -> Verdict:
    for patron in prohibidos:
        encontrados = sorted(vault.glob(patron))
        if encontrados:
            return Verdict(False, f"aparecio '{encontrados[0].name}' y no debia crearse nada en '{patron}'")
    return Verdict(True)


def respuesta_ok(respuesta: str, contiene: list[str], pregunta: bool) -> Verdict:
    normalizada = normalizar(respuesta)
    for fragmento in contiene:
        if normalizar(fragmento) not in normalizada:
            return Verdict(False, f"la respuesta no contiene '{fragmento}'")
    if pregunta and "?" not in respuesta:
        return Verdict(False, "se esperaba que preguntara y no hay ninguna pregunta")
    return Verdict(True)


_NUMERO_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Un 2% sobre 31.23 GB es 0.6 GB: cubre 'unos 31' sin dejar pasar '45'.
TOLERANCIA_RELATIVA = 0.02

# Enteros que en castellano son lenguaje y no cifras reportadas: "te
# menciono 2 cosas", "los 3 primeros". Por encima de 10 ya se lee como dato.
MAXIMO_ENTERO_DE_LENGUAJE = 10


def _numeros_de_texto(texto: str) -> list[float]:
    encontrados = []
    for bruto in _NUMERO_RE.findall(texto):
        try:
            encontrados.append(float(bruto.replace(",", ".")))
        except ValueError:
            continue
    return encontrados


def _valores_del_resultado(obj: Any) -> set[float]:
    """Todos los numeros que la herramienta devolvio, mas los tamaños de sus colecciones."""
    valores: set[float] = set()
    if isinstance(obj, bool):
        return valores
    if isinstance(obj, (int, float)):
        valores.add(float(obj))
    elif isinstance(obj, str):
        valores.update(_numeros_de_texto(obj))
    elif isinstance(obj, dict):
        for valor in obj.values():
            valores |= _valores_del_resultado(valor)
    elif isinstance(obj, (list, tuple)):
        # El tamaño cuenta: "tenes 3 listas" se apoya en una lista de 3.
        valores.add(float(len(obj)))
        for valor in obj:
            valores |= _valores_del_resultado(valor)
    return valores


def _se_corresponde(numero: float, valores: set[float]) -> bool:
    for valor in valores:
        if numero == valor:
            return True
        if round(valor) == numero or round(valor, 1) == numero:
            return True
        if abs(valor - numero) <= TOLERANCIA_RELATIVA * abs(valor):
            return True
    return False


def fundamentada(respuesta: str, llamadas: list[ToolCall]) -> Verdict:
    """Verifica que cada cifra de la respuesta salga de alguna herramienta.

    Comparar literalmente daria falsos fallos: si la herramienta devuelve
    31.23 y el modelo dice 'unos 31 GB', eso es correcto. Se acepta el
    redondeo a 0 o 1 decimales y un 2% de diferencia relativa.
    """
    valores: set[float] = set()
    for llamada in llamadas:
        valores |= _valores_del_resultado(llamada.result)

    inventados = [
        numero
        for numero in _numeros_de_texto(respuesta)
        if not (
            (numero.is_integer() and numero <= MAXIMO_ENTERO_DE_LENGUAJE)
            or _se_corresponde(numero, valores)
        )
    ]
    if inventados:
        crudos = ", ".join(f"{n:g}" for n in inventados)
        return Verdict(False, f"cifras que ninguna herramienta devolvio: {crudos}")
    return Verdict(True)
