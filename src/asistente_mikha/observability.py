from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Tracer

from asistente_mikha.config import get_phoenix_endpoint

TRACER_NAME = "asistente_mikha"

_tracing_configured = False


def configure_tracing(project_name: str = "asistente-mikha", endpoint: str | None = None) -> None:
    """Registra el TracerProvider global apuntando a un Phoenix local. Idempotente."""
    global _tracing_configured
    if _tracing_configured:
        return
    from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
    from phoenix.otel import register
    from pydantic_ai import Agent
    from pydantic_ai.models.instrumented import InstrumentationSettings

    tracer_provider = register(
        project_name=project_name,
        endpoint=endpoint or get_phoenix_endpoint(),
        auto_instrument=False,
    )
    # OpenInferenceSpanProcessor traduce los spans de PydanticAI al esquema
    # de atributos que la UI de Phoenix sabe leer para las columnas
    # input/output/cost (Phoenix documenta version=2 para esta combinación
    # — versiones más nuevas del esquema GenAI de OTel usan otros nombres
    # de atributo que la UI de Phoenix todavía no muestra en esas columnas).
    tracer_provider.add_span_processor(OpenInferenceSpanProcessor())
    Agent.instrument_all(InstrumentationSettings(version=2))
    _tracing_configured = True


def get_tracer() -> Tracer:
    return trace.get_tracer(TRACER_NAME)
