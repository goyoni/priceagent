# Backend Python OTEL Instrumentation Template

Reference patterns for instrumenting Python backends with OpenTelemetry.

---

## Dependencies

Add to `requirements.txt` or `pyproject.toml`:

```
# OpenTelemetry Core
opentelemetry-api>=1.27.0
opentelemetry-sdk>=1.27.0
opentelemetry-exporter-otlp-proto-grpc>=1.27.0

# Auto-instrumentation (add based on detected stack)
opentelemetry-instrumentation-fastapi>=0.48b0    # FastAPI
opentelemetry-instrumentation-flask>=0.48b0      # Flask
opentelemetry-instrumentation-django>=0.48b0     # Django
opentelemetry-instrumentation-httpx>=0.48b0      # httpx
opentelemetry-instrumentation-requests>=0.48b0   # requests
opentelemetry-instrumentation-sqlalchemy>=0.48b0 # SQLAlchemy
opentelemetry-instrumentation-redis>=0.48b0      # Redis
opentelemetry-instrumentation-celery>=0.48b0     # Celery
opentelemetry-instrumentation-aiohttp-client>=0.48b0  # aiohttp
opentelemetry-instrumentation-grpc>=0.48b0       # gRPC
```

---

## Telemetry Initialization Module

Create `src/telemetry.py` (adjust path to match project structure):

```python
"""
OpenTelemetry initialization and utilities.

Import and call `init_telemetry()` at application startup,
BEFORE importing modules that need instrumentation.
"""

import os
import logging
from functools import wraps
from typing import Optional, Callable, Any

from opentelemetry import trace, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.trace import StatusCode, Status

logger = logging.getLogger(__name__)

# Global state
_initialized = False


def init_telemetry(
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
) -> None:
    """
    Initialize OpenTelemetry tracing.

    Call this once at application startup, before any other imports
    that need instrumentation.

    Configuration via environment variables:
    - OTEL_ENABLED: Set to "false" to disable (default: "true")
    - OTEL_SERVICE_NAME: Service name (default: "unknown-service")
    - OTEL_EXPORTER_OTLP_ENDPOINT: Collector endpoint (default: "http://localhost:4317")
    - DEPLOYMENT_ENVIRONMENT: Environment name (default: "development")
    """
    global _initialized
    if _initialized:
        return

    enabled = os.getenv("OTEL_ENABLED", "true").lower() == "true"
    if not enabled:
        logger.info("OpenTelemetry disabled via OTEL_ENABLED=false")
        _initialized = True
        return

    _service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "unknown-service")
    _service_version = service_version or os.getenv("OTEL_SERVICE_VERSION", "0.1.0")
    _environment = os.getenv("DEPLOYMENT_ENVIRONMENT", "development")
    _endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Create resource with service metadata
    resource = Resource.create(
        {
            "service.name": _service_name,
            "service.version": _service_version,
            "deployment.environment": _environment,
        }
    )

    # Configure trace provider
    provider = TracerProvider(resource=resource)

    # Add OTLP exporter with batch processor
    otlp_exporter = OTLPSpanExporter(endpoint=_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global provider
    trace.set_tracer_provider(provider)

    # Configure W3C TraceContext + Baggage propagation
    set_global_textmap(
        CompositePropagator(
            [TraceContextTextMapPropagator(), W3CBaggagePropagator()]
        )
    )

    _initialized = True
    logger.info(
        "OpenTelemetry initialized",
        extra={
            "service_name": _service_name,
            "endpoint": _endpoint,
            "environment": _environment,
        },
    )


def get_tracer(name: str) -> trace.Tracer:
    """Get a named tracer instance."""
    return trace.get_tracer(name)


def traced(
    span_name: Optional[str] = None,
    attributes: Optional[dict] = None,
):
    """
    Decorator to wrap a function in an OTEL span.

    Usage:
        @traced("my_operation")
        def do_something():
            ...

        @traced(attributes={"operation.type": "search"})
        async def search(query: str):
            ...
    """

    def decorator(func: Callable) -> Callable:
        _name = span_name or f"{func.__module__}.{func.__qualname__}"
        tracer = get_tracer(func.__module__)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def record_exception(span: trace.Span, exception: Exception) -> None:
    """Record an exception on a span and set error status."""
    span.record_exception(exception)
    span.set_status(Status(StatusCode.ERROR, str(exception)))
```

---

## FastAPI Integration

### Auto-instrumentation setup

Add to your telemetry init or a separate `src/telemetry_fastapi.py`:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


def instrument_fastapi(app):
    """Add OTEL auto-instrumentation to a FastAPI app."""
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,healthz,ready,readyz",  # Skip health checks
    )
```

### Application startup integration

In your `main.py` or wherever the FastAPI app is created:

```python
# IMPORTANT: Import and init telemetry BEFORE creating the app
from src.telemetry import init_telemetry
init_telemetry(service_name="my-api")

from fastapi import FastAPI
from src.telemetry_fastapi import instrument_fastapi

app = FastAPI()
instrument_fastapi(app)
```

### Session ID middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace


class SessionTraceMiddleware(BaseHTTPMiddleware):
    """Extract session ID from request headers and attach to current span."""

    async def dispatch(self, request, call_next):
        span = trace.get_current_span()
        session_id = request.headers.get("x-session-id")
        if session_id:
            span.set_attribute("session.id", session_id)
        return await call_next(request)


# Add to app:
# app.add_middleware(SessionTraceMiddleware)
```

---

## Flask Integration

```python
from opentelemetry.instrumentation.flask import FlaskInstrumentor


def instrument_flask(app):
    FlaskInstrumentor().instrument_app(app)
```

---

## Django Integration

```python
# In settings.py, add to INSTALLED_APPS or MIDDLEWARE:
# Or use the programmatic approach:

from opentelemetry.instrumentation.django import DjangoInstrumentor

DjangoInstrumentor().instrument()
```

---

## HTTP Client Instrumentation

### httpx

```python
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

HTTPXClientInstrumentor().instrument()
```

### requests

```python
from opentelemetry.instrumentation.requests import RequestsInstrumentor

RequestsInstrumentor().instrument()
```

---

## SQLAlchemy Instrumentation

```python
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Instrument all engines automatically
SQLAlchemyInstrumentor().instrument()

# Or instrument a specific engine
# SQLAlchemyInstrumentor().instrument(engine=engine)
```

---

## Custom Span Examples

### Search operation

```python
from src.telemetry import get_tracer, traced

tracer = get_tracer(__name__)


@traced("product.search")
async def search_products(query: str, filters: dict):
    span = trace.get_current_span()
    span.set_attribute("search.query", query)
    span.set_attribute("search.filters", str(filters))

    results = await do_search(query, filters)

    span.set_attribute("search.result_count", len(results))
    return results
```

### External API call

```python
async def call_external_api(url: str, payload: dict):
    with tracer.start_as_current_span("external_api.call") as span:
        span.set_attribute("http.url", url)
        span.set_attribute("http.method", "POST")

        try:
            response = await client.post(url, json=payload)
            span.set_attribute("http.status_code", response.status_code)

            if response.status_code >= 400:
                span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))

            return response
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
```

### Database operation with context

```python
async def get_user_by_id(user_id: int):
    with tracer.start_as_current_span("db.get_user") as span:
        span.set_attribute("db.system", "sqlite")
        span.set_attribute("db.operation", "SELECT")
        span.set_attribute("user.id", user_id)

        user = await db.query(User).filter_by(id=user_id).first()

        if user:
            span.set_attribute("db.result", "found")
        else:
            span.set_attribute("db.result", "not_found")

        return user
```

---

## Error Handling Pattern

```python
from opentelemetry.trace import StatusCode


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    span = trace.get_current_span()
    if span.is_recording():
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
        span.set_attribute("error.type", type(exc).__name__)
    raise exc
```

---

## Shutdown

Ensure spans are flushed on shutdown:

```python
import atexit
from opentelemetry import trace


def shutdown_telemetry():
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()


atexit.register(shutdown_telemetry)

# Or for FastAPI:
@app.on_event("shutdown")
async def shutdown():
    shutdown_telemetry()
```
