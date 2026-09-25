from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic_ai import Agent

from asistente_mikha.agent import SYSTEM_PROMPT, _build_model, instrucciones_de_fecha
from asistente_mikha.evals.checks import ToolCall, extraer_llamadas
from asistente_mikha.memory.turn_context import reset_user_message, set_user_message
from asistente_mikha.tools import registry

VARIANTES = ("baseline", "cot_prompt", "cot_arg", "two_step", "no_think")

INSTRUCCION_COT = (
    "\n\nAntes de actuar, pensá paso a paso qué te están pidiendo y qué "
    "herramienta lo resuelve. Después actuá."
)

INSTRUCCION_MOTIVO = (
    "\n\nCada herramienta lleva un argumento 'motivo': escribí ahí, en una "
    "frase, por qué elegís esa acción y esos argumentos, antes de completar "
    "el resto."
)

PROMPT_PLANIFICADOR = (
    "Sos el planificador de un asistente de una máquina Linux. NO ejecutás "
    "nada. Tenés estas herramientas disponibles para quien ejecute: "
    "diagnostics(check), system_action(action, target), memory(action, ...), "
    "tasks(action, list_name, text). Decí en dos líneas qué herramienta hay "
    "que usar y con qué argumentos exactos. Si no hace falta ninguna, decilo."
)


@dataclass
class TurnOutcome:
    respuesta: str
    llamadas: list[ToolCall] = field(default_factory=list)


def con_motivo(func: Callable[..., Any]) -> Callable[..., Any]:
    """Envuelve una herramienta agregandole un 'motivo' obligatorio adelante.

    pydantic-ai arma el esquema desde typing.get_type_hints(), no desde
    __signature__, asi que hay que asignar los dos: con uno solo falla con
    KeyError: 'motivo'. Verificado contra pydantic-ai 2.42.0.
    """

    @functools.wraps(func)
    def wrapper(*, motivo: str, **kwargs: Any) -> Any:
        # El motivo no se usa para nada: existe para que el modelo razone
        # dentro de la llamada, y queda grabado en la traza de Phoenix.
        return func(**kwargs)

    original = inspect.signature(func)
    parametros = [inspect.Parameter("motivo", inspect.Parameter.KEYWORD_ONLY, annotation=str)]
    parametros += [
        p.replace(kind=inspect.Parameter.KEYWORD_ONLY) for p in original.parameters.values()
    ]
    wrapper.__signature__ = original.replace(parameters=parametros)
    wrapper.__annotations__ = {"motivo": str, **func.__annotations__}
    wrapper.__doc__ = (func.__doc__ or "") + "\n\nmotivo: por que elegis esta accion."
    return wrapper


def construir_agente(modelo: str, variante: str) -> Agent:
    if variante not in VARIANTES:
        raise ValueError(f"variante desconocida: '{variante}'. Conocidas: {', '.join(VARIANTES)}")

    prompt = SYSTEM_PROMPT
    if variante == "cot_prompt":
        prompt += INSTRUCCION_COT
    elif variante == "cot_arg":
        prompt += INSTRUCCION_MOTIVO

    ajustes: dict[str, Any] = {"temperature": 0.0}
    if variante == "no_think":
        # Apaga el razonamiento entrenado de los modelos thinking (qwen3). Por el
        # endpoint /v1 de Ollama 0.34 solo funciona reasoning_effort="none":
        # 'think: false' y '/no_think' en el mensaje se ignoran. Verificado en
        # vivo: 796 tokens y 29.6s pasan a 4 tokens y 0.3s, misma respuesta.
        ajustes["openai_reasoning_effort"] = "none"

    agente = Agent(
        _build_model(modelo),
        system_prompt=prompt,
        instructions=lambda: instrucciones_de_fecha(),
        model_settings=ajustes,
    )
    for registrada in registry.all_tools().values():
        funcion = con_motivo(registrada.func) if variante == "cot_arg" else registrada.func
        agente.tool_plain(funcion)
    return agente


def _construir_planificador(modelo: str) -> Agent:
    # Sin herramientas a proposito: si las tiene, 'two_step' degenera en el
    # baseline con un paso de mas.
    return Agent(
        _build_model(modelo),
        system_prompt=PROMPT_PLANIFICADOR,
        model_settings={"temperature": 0.0},
    )


async def ejecutar_turno(modelo: str, variante: str, mensaje: str) -> TurnOutcome:
    entrada = mensaje
    if variante == "two_step":
        plan = await _construir_planificador(modelo).run(mensaje)
        entrada = f"Plan: {plan.output}\n\nPedido del usuario: {mensaje}"

    token = set_user_message(mensaje)
    try:
        resultado = await construir_agente(modelo, variante).run(entrada)
    finally:
        reset_user_message(token)
    return TurnOutcome(
        respuesta=resultado.output,
        llamadas=extraer_llamadas(resultado.all_messages()),
    )
