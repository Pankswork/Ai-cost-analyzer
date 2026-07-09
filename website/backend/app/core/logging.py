import structlog
from opentelemetry import trace


def add_otel_trace_context(logger, method_name, event_dict):
    span = trace.get_current_span()
    span_context = span.get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = hex(span_context.trace_id)
        event_dict["span_id"] = hex(span_context.span_id)
    return event_dict


structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_otel_trace_context,
        structlog.dev.ConsoleRenderer() if __import__("sys").stdout.isatty()
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
