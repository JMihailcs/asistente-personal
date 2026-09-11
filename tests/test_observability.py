from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from asistente_mikha.observability import get_tracer


def test_get_tracer_creates_span_with_attributes():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = get_tracer()
    with tracer.start_as_current_span("test.span") as span:
        span.set_attribute("gen_ai.tool.name", "get_ram_usage")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.span"
    assert spans[0].attributes["gen_ai.tool.name"] == "get_ram_usage"
