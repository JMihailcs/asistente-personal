from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from asistente_mikha import observability
from asistente_mikha.observability import get_tracer


def test_get_tracer_creates_span_with_attributes():
    # No usamos trace.set_tracer_provider(): OpenTelemetry solo permite fijar
    # el proveedor global una vez por proceso, y otro test de la suite (que
    # levanta la app FastAPI) puede haberlo hecho ya. En su lugar,
    # interceptamos get_tracer_provider() para aislar este test del orden
    # de ejecución del resto de la suite.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
        tracer = get_tracer()
        with tracer.start_as_current_span("test.span") as span:
            span.set_attribute("gen_ai.tool.name", "get_ram_usage")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.span"
    assert spans[0].attributes["gen_ai.tool.name"] == "get_ram_usage"


def test_configure_tracing_uses_phoenix_endpoint_from_config(monkeypatch):
    monkeypatch.setenv("PHOENIX_ENDPOINT", "http://phoenix:6006/v1/traces")
    observability._tracing_configured = False
    captured = {}

    def fake_register(**kwargs):
        captured.update(kwargs)

    with patch("phoenix.otel.register", side_effect=fake_register):
        observability.configure_tracing()

    assert captured["endpoint"] == "http://phoenix:6006/v1/traces"
    observability._tracing_configured = False
