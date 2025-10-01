from typing import Optional

from starlette_exporter import PrometheusMiddleware, handle_metrics

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    _HAS_OTEL = True
except Exception:  # pragma: no cover
    _HAS_OTEL = False


def add_prometheus(app, app_name: str = "gateway") -> None:
    app.add_middleware(
        PrometheusMiddleware,
        app_name=app_name,
        prefix=app_name,
        group_paths=True,
    )
    app.add_route("/metrics", handle_metrics)


def add_tracing(app, app_name: str, endpoint: Optional[str]) -> None:
    if not _HAS_OTEL:
        return
    resource = Resource.create({"service.name": app_name})
    provider = TracerProvider(resource=resource)
    if endpoint:
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        provider.add_span_processor(processor)
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
