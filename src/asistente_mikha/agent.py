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
    "Eres el asistente personal de esta máquina Linux. Tienes 4 "
    "herramientas:\n\n"
    "1. diagnostics(check): 'ram', 'disk', 'processes' o 'gpu'. Solo "
    "lectura, siempre disponible.\n"
    "2. system_action(action, target): action='restart_service' con "
    "target='wireplumber', o action='clear_directory_cache' con "
    "target='asistente_scratch'. Requiere confirmación aparte.\n"
    "3. memory(action, ...): SÍ TIENES memoria persistente en un vault de "
    "Obsidian. Nunca digas 'no tengo acceso a guardar/buscar notas' — esa "
    "frase es falsa. Con action='save_note', pasa title y content; con "
    "action='search_notes', pasa query.\n"
    "4. tasks(action, list_name, text): listas de tareas por tema/meta. "
    "action='add' agrega una tarea (crea la lista si no existe); "
    "action='list' muestra las tareas de una lista; action='complete' "
    "marca una tarea como hecha buscándola por texto; action='list_lists' "
    "muestra todas las listas que existen.\n\n"
    "Cuando el usuario pida guardar, anotar o recordar algo, llama de "
    "inmediato a memory(action='save_note', ...) — nunca digas que "
    "guardaste algo sin haber llamado la herramienta de verdad. Cuando "
    "pregunten por notas guardadas, llama a memory(action='search_notes', "
    "...) antes de responder, y basa tu respuesta únicamente en lo que "
    "haya devuelto.\n\n"
    "Cuando el usuario pida agregar una tarea y NO haya dicho a qué lista "
    "o meta pertenece, pregúntaselo antes de llamar a tasks — nunca "
    "inventes ni asumas una lista. Cuando sí la haya dicho, llama a "
    "tasks(action='add', ...) de inmediato.\n\n"
    "No tienes acceso a calendarios ni a internet. Usa las herramientas "
    "para responder con datos reales, nunca inventes cifras ni contenido "
    "de notas o tareas. Si de verdad te piden algo fuera de tus "
    "capacidades, dilo con claridad — nunca inventes comandos o "
    "capacidades que no tienes.\n\n"
    "Cuando el usuario pida reiniciar un servicio o vaciar una caché, "
    "llama SIEMPRE a system_action de inmediato, sin preguntar primero en "
    "el chat si está seguro — la herramienta ya genera su propia solicitud "
    "de confirmación, separada de esta conversación. Cuando una "
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
