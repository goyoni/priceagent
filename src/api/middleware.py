"""FastAPI middleware for request logging and analytics."""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.logging import (
    log_api_request,
    set_request_context,
    clear_request_context,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests with timing and context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]

        # Extract session/user from headers or cookies
        session_id = request.cookies.get("session_id") or request.headers.get("X-Session-ID")
        user_id = request.headers.get("X-User-ID")

        # Set request context for all logs in this request
        set_request_context(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
        )

        # Add request ID to response headers
        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log the request
            log_api_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_agent=request.headers.get("User-Agent"),
            )

            # Add request ID to response
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            log_api_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
                user_agent=request.headers.get("User-Agent"),
                error=str(e),
            )
            raise

        finally:
            clear_request_context()
