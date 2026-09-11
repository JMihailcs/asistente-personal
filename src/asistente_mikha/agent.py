from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from asistente_mikha.confirmation import collect_turn_actions, start_turn_tracking
from asistente_mikha.observability import get_tracer
from asistente_mikha.tools import registry

# Importar estos módulos registra sus herramientas en `registry` como
# efecto secundario del decorador @tool — deben importarse antes de
# construir cualquier agente.
from asistente_mikha.tools import actions, diagnostics  # noqa: F401

OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL_NAME = "default"

SYSTEM_PROMPT = (
    "Eres un asistente de diagnóstico para esta máquina Linux. Usa las "
    "herramientas disponibles para responder con datos reales, nunca "
    "inventes cifras. Cuando una herramienta devuelva "
    "status='pending_confirmation', explícale al usuario que la acción "
    "quedó pendiente de confirmación explícita y menciona su action_id."
)


def _build_model(model_name: str = DEFAULT_MODEL_NAME) -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=OLLAMA_BASE_URL, api_key="ollama")
    return OpenAIChatModel(model_name, provider=provider)


def build_agent(model_name: str = DEFAULT_MODEL_NAME) -> Agent:
    agent = Agent(_build_model(model_name), system_prompt=SYSTEM_PROMPT)
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
