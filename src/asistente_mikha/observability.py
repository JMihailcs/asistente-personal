from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Tracer

TRACER_NAME = "asistente_mikha"
DEFAULT_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"

_tracing_configured = False


def configure_tracing(
    project_name: str = "asistente-mikha", endpoint: str = DEFAULT_PHOENIX_ENDPOINT
) -> None:
    """Registra el TracerProvider global apuntando a un Phoenix local. Idempotente."""
    global _tracing_configured
    if _tracing_configured:
        return
    from phoenix.otel import register

    register(project_name=project_name, endpoint=endpoint, auto_instrument=False)
    _tracing_configured = True


def get_tracer() -> Tracer:
    return trace.get_tracer(TRACER_NAME)
