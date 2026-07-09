import os
import sentry_sdk
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

_tracer: trace.Tracer | None = None
_meter: metrics.Meter | None = None
_initialized = False


def init_telemetry(service_name: str = "backend") -> None:
    global _tracer, _meter, _initialized

    if _initialized:
        return

    sentry_dsn = os.getenv("SENTRY_DSN", "")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=os.getenv("APP_ENVIRONMENT", "development"),
        )

    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://localhost:4317",
    )

    tracer_provider = TracerProvider()
    span_processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=endpoint),
    )
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)
    _tracer = tracer_provider.get_tracer(service_name)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint),
        export_interval_millis=30_000,
    )
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    _meter = meter_provider.get_meter(service_name)

    LoggingInstrumentor().instrument(set_logging_format=False)

    _initialized = True


def instrument_fastapi(app) -> None:
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine)


def instrument_httpx() -> None:
    HTTPXClientInstrumentor().instrument()


def get_tracer() -> trace.Tracer:
    if _tracer is None:
        return trace.get_tracer("backend")
    return _tracer


def get_meter() -> metrics.Meter:
    if _meter is None:
        return metrics.get_meter("backend")
    return _meter
