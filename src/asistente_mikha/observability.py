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
    from phoenix.otel import register

    register(
        project_name=project_name,
        endpoint=endpoint or get_phoenix_endpoint(),
        auto_instrument=False,
    )
    _tracing_configured = True


def get_tracer() -> Tracer:
    return trace.get_tracer(TRACER_NAME)
