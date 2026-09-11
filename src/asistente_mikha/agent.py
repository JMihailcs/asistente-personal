from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from asistente_mikha.config import get_ollama_base_url
from asistente_mikha.confirmation import collect_turn_actions, start_turn_tracking
from asistente_mikha.observability import get_tracer
from asistente_mikha.tools import registry

# Importar estos módulos registra sus herramientas en `registry` como
# efecto secundario del decorador @tool — deben importarse antes de
# construir cualquier agente.
from asistente_mikha.tools import actions, diagnostics  # noqa: F401
from asistente_mikha.memory import tools as memory_tools  # noqa: F401

DEFAULT_MODEL_NAME = "default"

SYSTEM_PROMPT = (
    "Eres el asistente personal de esta máquina Linux. Tus únicas "
    "capacidades son las herramientas que tienes disponibles: diagnóstico "
    "de RAM, disco, procesos y GPU (solo lectura); reiniciar servicios o "
    "vaciar cachés de una allowlist fija (requieren confirmación); y "
    "guardar/buscar notas en el vault de Obsidian del usuario (memoria "
    "persistente). No tienes acceso a calendarios, internet, ni ningún "
    "otro sistema fuera de estas herramientas. Usa las herramientas "
    "disponibles para responder con datos reales, nunca inventes cifras "
    "ni contenido de notas que no encontraste de verdad. Si te piden algo "
    "fuera de tus capacidades, dilo explícitamente y con claridad — nunca "
    "inventes comandos, herramientas o capacidades que no tienes. Cuando "
    "el usuario pida una acción que modifique el sistema (reiniciar un "
    "servicio, vaciar una caché), llama SIEMPRE a la herramienta "
    "correspondiente de inmediato, sin preguntar primero en el chat si "
    "está seguro — la herramienta ya genera su propia solicitud de "
    "confirmación explícita, separada de esta conversación. Cuando una "
    "herramienta devuelva status='pending_confirmation', explícale al "
    "usuario que la acción quedó pendiente de confirmación y menciona su "
    "action_id."
)


def _build_model(model_name: str = DEFAULT_MODEL_NAME) -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=get_ollama_base_url(), api_key="ollama")
    return OpenAIChatModel(model_name, provider=provider)


def build_agent(model_name: str = DEFAULT_MODEL_NAME) -> Agent:
    # temperature=0 hace determinista la decisión de invocar una herramienta:
    # con muestreo por defecto, este modelo de 12B a veces alucina resultados
    # o inventa texto en vez de llamar a la tool correspondiente.
    agent = Agent(
        _build_model(model_name),
        system_prompt=SYSTEM_PROMPT,
        model_settings={"temperature": 0.0},
    )
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
