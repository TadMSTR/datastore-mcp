"""datastore-mcp — Multi-backend database MCP server."""
from __future__ import annotations

import os

import structlog
from fastmcp import FastMCP

from datastore_mcp.config import load_config
from datastore_mcp.registry import ConnectionRegistry
from datastore_mcp.tools.core import register_core_tools
from datastore_mcp.tools.extras import register_extra_tools

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger()


def _setup_telemetry() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        log.info("OTLP tracing enabled", endpoint=endpoint)
    except ImportError:
        log.warning(
            "opentelemetry packages not installed — tracing disabled. "
            "Install datastore-mcp[telemetry] to enable."
        )


config = load_config()
registry = ConnectionRegistry(config)

mcp = FastMCP("datastore-mcp")
register_core_tools(mcp, registry)
register_extra_tools(mcp, registry)


def main() -> None:
    _setup_telemetry()
    log.info(
        "datastore-mcp starting",
        port=8501,
        instances=registry.list_instances(),
    )
    mcp.run()


if __name__ == "__main__":
    main()
