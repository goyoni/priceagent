"""Comprehensive logging module for production monitoring.

Provides structured logging for:
- User interactions (searches, clicks, contacts)
- System operations (scraping, API calls, errors)
- Performance metrics (latency, cache hits)
- Business events (negotiations, conversions)

Supports:
- Console logging (development)
- File logging (development and production)
- External log aggregation (production - Grafana Loki compatible)
"""

import json
import logging
import os
import sys
import time
import threading
from datetime import datetime
from enum import Enum
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Optional
from contextvars import ContextVar

import structlog
from pydantic import BaseModel

# Request context for correlating logs
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
_session_id: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


class EventCategory(str, Enum):
    """Categories of logged events."""
    USER_ACTION = "user_action"
    SEARCH = "search"
    SCRAPING = "scraping"
    CONTACT = "contact"
    NEGOTIATION = "negotiation"
    SYSTEM = "system"
    ERROR = "error"
    PERFORMANCE = "performance"


class UserAction(str, Enum):
    """Types of user actions."""
    PAGE_VIEW = "page_view"
    SEARCH_SUBMIT = "search_submit"
    RESULT_CLICK = "result_click"
    SELLER_CONTACT = "seller_contact"
    DRAFT_GENERATE = "draft_generate"
    DRAFT_COPY = "draft_copy"
    WHATSAPP_CLICK = "whatsapp_click"
    FILTER_CHANGE = "filter_change"
    SORT_CHANGE = "sort_change"


class LogEvent(BaseModel):
    """Structured log event."""
    timestamp: datetime
    category: EventCategory
    action: str
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    data: dict = {}
    duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None


class LogConfig:
    """Logging configuration from environment variables."""

    # Environment: development, staging, production
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Log level: DEBUG, INFO, WARNING, ERROR
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Log format: json or text
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json" if ENVIRONMENT == "production" else "text")

    # File logging
    LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    LOG_DIR: Path = Path(os.getenv("LOG_DIR", "logs"))
    LOG_FILE_MAX_BYTES: int = int(os.getenv("LOG_FILE_MAX_BYTES", 10 * 1024 * 1024))  # 10MB
    LOG_FILE_BACKUP_COUNT: int = int(os.getenv("LOG_FILE_BACKUP_COUNT", 5))

    # External logging (Grafana Loki / Grafana Cloud compatible)
    LOG_EXTERNAL_ENABLED: bool = os.getenv("LOG_EXTERNAL_ENABLED", "false").lower() == "true"
    LOG_EXTERNAL_ENDPOINT: str = os.getenv("LOG_EXTERNAL_ENDPOINT", "")  # e.g., https://logs-prod-xxx.grafana.net/loki/api/v1/push
    LOG_EXTERNAL_LABELS: str = os.getenv("LOG_EXTERNAL_LABELS", '{"app":"priceagent"}')

    # Grafana Cloud authentication (optional - for cloud hosted Loki)
    LOG_EXTERNAL_USER: str = os.getenv("LOG_EXTERNAL_USER", "")  # Grafana Cloud user ID
    LOG_EXTERNAL_API_KEY: str = os.getenv("LOG_EXTERNAL_API_KEY", "")  # Grafana Cloud API key

    @classmethod
    def get_labels(cls) -> dict:
        """Parse external log labels from JSON string."""
        try:
            return json.loads(cls.LOG_EXTERNAL_LABELS)
        except json.JSONDecodeError:
            return {"app": "priceagent"}

    @classmethod
    def get_auth(cls) -> tuple[str, str] | None:
        """Get authentication credentials if configured."""
        if cls.LOG_EXTERNAL_USER and cls.LOG_EXTERNAL_API_KEY:
            return (cls.LOG_EXTERNAL_USER, cls.LOG_EXTERNAL_API_KEY)
        return None


class LokiHandler(logging.Handler):
    """Custom handler for sending logs to Grafana Loki.

    Loki expects logs in this format:
    {
        "streams": [
            {
                "stream": {"app": "priceagent", "level": "info"},
                "values": [
                    ["<unix_nanoseconds>", "<log_line>"]
                ]
            }
        ]
    }

    Supports both local Loki and Grafana Cloud with basic auth.

    Resilience: After MAX_CONSECUTIVE_FAILURES, the handler disables itself
    to avoid spamming logs or impacting performance.
    """

    MAX_CONSECUTIVE_FAILURES = 3  # Disable after this many consecutive failures

    def __init__(
        self,
        endpoint: str,
        labels: dict,
        auth: tuple[str, str] | None = None,
        batch_size: int = 100,
        flush_interval: float = 30.0  # Flush every 30 seconds (not 5)
    ):
        super().__init__()
        self.endpoint = endpoint
        self.base_labels = labels
        self.auth = auth  # (user_id, api_key) for Grafana Cloud
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer: list[tuple[str, str, dict]] = []  # (timestamp_ns, message, labels)
        self._last_flush = time.time()
        self._consecutive_failures = 0
        self._disabled = False
        self._first_error_logged = False
        self._lock = threading.Lock()
        self._flush_in_progress = False

    def emit(self, record: logging.LogRecord):
        """Emit a log record."""
        # Skip if handler has been disabled due to repeated failures
        if self._disabled:
            return

        try:
            # Format the message
            msg = self.format(record)

            # Get timestamp in nanoseconds
            timestamp_ns = str(int(record.created * 1e9))

            # Add level to labels
            labels = {**self.base_labels, "level": record.levelname.lower()}

            with self._lock:
                self._buffer.append((timestamp_ns, msg, labels))
                should_flush = (
                    len(self._buffer) >= self.batch_size or
                    (time.time() - self._last_flush) >= self.flush_interval
                )

            # Flush in background thread if needed
            if should_flush and not self._flush_in_progress:
                self._flush_async()

        except Exception:
            self.handleError(record)

    def _flush_async(self):
        """Flush in a background thread to avoid blocking."""
        self._flush_in_progress = True
        thread = threading.Thread(target=self._do_flush, daemon=True)
        thread.start()

    def _do_flush(self):
        """Actual flush operation (runs in background thread)."""
        try:
            self.flush()
        finally:
            self._flush_in_progress = False

    def flush(self):
        """Flush buffered logs to Loki."""
        if self._disabled:
            return

        # Grab buffer under lock
        with self._lock:
            if not self._buffer:
                return
            buffer_copy = self._buffer[:]
            self._buffer = []
            self._last_flush = time.time()

        try:
            import httpx

            # Group by labels
            streams: dict[str, list[tuple[str, str]]] = {}
            for timestamp_ns, msg, labels in buffer_copy:
                key = json.dumps(labels, sort_keys=True)
                if key not in streams:
                    streams[key] = []
                streams[key].append((timestamp_ns, msg))

            # Build Loki payload
            payload = {
                "streams": [
                    {
                        "stream": json.loads(label_key),
                        "values": [[ts, msg] for ts, msg in values]
                    }
                    for label_key, values in streams.items()
                ]
            }

            # Send to Loki
            with httpx.Client(timeout=10.0, auth=self.auth) as client:
                response = client.post(
                    self.endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()

            # Success - reset failure counter
            self._consecutive_failures = 0

        except Exception as e:
            self._consecutive_failures += 1

            # Only log the first error to avoid spamming stderr
            if not self._first_error_logged:
                print(f"[LokiHandler] Failed to send logs to Loki: {e}", file=sys.stderr)
                self._first_error_logged = True

            # Disable handler after repeated failures
            if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                self._disabled = True
                print(
                    f"[LokiHandler] Disabled after {self._consecutive_failures} consecutive failures. "
                    "Logs will continue to file/console.",
                    file=sys.stderr
                )

        finally:
            self._buffer = []
            self._last_flush = time.time()

    def close(self):
        """Close the handler and flush remaining logs."""
        self.flush()
        super().close()


def setup_file_logging() -> Optional[logging.Handler]:
    """Set up file-based logging with rotation."""
    if not LogConfig.LOG_TO_FILE:
        return None

    # Create log directory
    LogConfig.LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Main log file with rotation
    log_file = LogConfig.LOG_DIR / "app.log"
    handler = RotatingFileHandler(
        log_file,
        maxBytes=LogConfig.LOG_FILE_MAX_BYTES,
        backupCount=LogConfig.LOG_FILE_BACKUP_COUNT,
    )

    # Use JSON format for file logs (easier to parse)
    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.setLevel(getattr(logging, LogConfig.LOG_LEVEL))

    return handler


def setup_error_file_logging() -> Optional[logging.Handler]:
    """Set up separate error log file."""
    if not LogConfig.LOG_TO_FILE:
        return None

    LogConfig.LOG_DIR.mkdir(parents=True, exist_ok=True)

    error_log_file = LogConfig.LOG_DIR / "error.log"
    handler = RotatingFileHandler(
        error_log_file,
        maxBytes=LogConfig.LOG_FILE_MAX_BYTES,
        backupCount=LogConfig.LOG_FILE_BACKUP_COUNT,
    )

    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.setLevel(logging.ERROR)

    return handler


def setup_external_logging() -> Optional[logging.Handler]:
    """Set up external log aggregation (Loki / Grafana Cloud)."""
    if not LogConfig.LOG_EXTERNAL_ENABLED or not LogConfig.LOG_EXTERNAL_ENDPOINT:
        return None

    handler = LokiHandler(
        endpoint=LogConfig.LOG_EXTERNAL_ENDPOINT,
        labels=LogConfig.get_labels(),
        auth=LogConfig.get_auth(),  # None for local Loki, (user, key) for Grafana Cloud
    )
    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.setLevel(getattr(logging, LogConfig.LOG_LEVEL))

    return handler


def configure_production_logging(log_file: Optional[Path] = None):
    """Configure structured logging for all environments.

    Args:
        log_file: Optional path to log file (deprecated, use LOG_DIR env var)
    """
    # Set up standard library logging handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LogConfig.LOG_LEVEL))

    # Clear existing handlers
    root_logger.handlers = []

    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LogConfig.LOG_LEVEL))
    root_logger.addHandler(console_handler)

    # File handler (if enabled)
    file_handler = setup_file_logging()
    if file_handler:
        root_logger.addHandler(file_handler)

    # Error file handler
    error_handler = setup_error_file_logging()
    if error_handler:
        root_logger.addHandler(error_handler)

    # External handler (Loki)
    external_handler = setup_external_logging()
    if external_handler:
        root_logger.addHandler(external_handler)

    # Configure structlog processors
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Add request context
        add_request_context,
        # Add environment info
        add_environment_context,
    ]

    # Use JSON renderer for production, colored console for dev
    if LogConfig.LOG_FORMAT == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Log startup info
    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        environment=LogConfig.ENVIRONMENT,
        log_level=LogConfig.LOG_LEVEL,
        log_format=LogConfig.LOG_FORMAT,
        file_logging=LogConfig.LOG_TO_FILE,
        log_dir=str(LogConfig.LOG_DIR) if LogConfig.LOG_TO_FILE else None,
        external_logging=LogConfig.LOG_EXTERNAL_ENABLED,
    )


def add_request_context(logger, method_name, event_dict):
    """Add request context to log events."""
    request_id = _request_id.get()
    user_id = _user_id.get()
    session_id = _session_id.get()

    if request_id:
        event_dict["request_id"] = request_id
    if user_id:
        event_dict["user_id"] = user_id
    if session_id:
        event_dict["session_id"] = session_id

    return event_dict


def add_environment_context(logger, method_name, event_dict):
    """Add environment info to log events."""
    event_dict["env"] = LogConfig.ENVIRONMENT
    return event_dict


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """Set request context for correlation."""
    if request_id:
        _request_id.set(request_id)
    if user_id:
        _user_id.set(user_id)
    if session_id:
        _session_id.set(session_id)


def clear_request_context():
    """Clear request context."""
    _request_id.set(None)
    _user_id.set(None)
    _session_id.set(None)


# Get module logger
logger = structlog.get_logger(__name__)


# High-level logging functions

def log_user_action(
    action: UserAction,
    data: Optional[dict] = None,
    duration_ms: Optional[float] = None,
):
    """Log a user action for engagement tracking.

    Args:
        action: Type of user action
        data: Additional context data
        duration_ms: Duration of the action in milliseconds
    """
    logger.info(
        "user_action",
        category=EventCategory.USER_ACTION.value,
        action=action.value,
        data=data or {},
        duration_ms=duration_ms,
    )


def log_search(
    query: str,
    results_count: int,
    sources: list[str],
    duration_ms: float,
    cached: bool = False,
    error: Optional[str] = None,
):
    """Log a search operation.

    Args:
        query: Search query
        results_count: Number of results returned
        sources: List of sources searched
        duration_ms: Search duration in milliseconds
        cached: Whether results were from cache
        error: Error message if search failed
    """
    logger.info(
        "search",
        category=EventCategory.SEARCH.value,
        query=query,
        results_count=results_count,
        sources=sources,
        duration_ms=duration_ms,
        cached=cached,
        success=error is None,
        error=error,
    )


def log_scrape(
    source: str,
    url: str,
    success: bool,
    duration_ms: float,
    items_found: int = 0,
    error: Optional[str] = None,
):
    """Log a scraping operation.

    Args:
        source: Scraper name (zap, google, etc.)
        url: URL scraped
        success: Whether scrape succeeded
        duration_ms: Scrape duration in milliseconds
        items_found: Number of items found
        error: Error message if failed
    """
    level = "info" if success else "warning"
    getattr(logger, level)(
        "scrape",
        category=EventCategory.SCRAPING.value,
        source=source,
        url=url[:100],  # Truncate long URLs
        success=success,
        duration_ms=duration_ms,
        items_found=items_found,
        error=error,
    )


def log_contact_extraction(
    seller: str,
    url: str,
    phone_found: bool,
    duration_ms: float,
    phone: Optional[str] = None,
):
    """Log contact extraction attempt.

    Args:
        seller: Seller name
        url: Seller URL
        phone_found: Whether phone was found
        duration_ms: Extraction duration
        phone: Phone number if found (masked for privacy)
    """
    # Mask phone number for privacy in logs
    masked_phone = None
    if phone:
        masked_phone = phone[:4] + "****" + phone[-2:] if len(phone) > 6 else "***"

    logger.info(
        "contact_extraction",
        category=EventCategory.CONTACT.value,
        seller=seller,
        url=url[:100],
        phone_found=phone_found,
        phone_masked=masked_phone,
        duration_ms=duration_ms,
    )


def log_seller_contact(
    seller: str,
    phone: str,
    product: str,
    method: str = "whatsapp",
):
    """Log when user contacts a seller.

    Args:
        seller: Seller name
        phone: Phone number (will be masked)
        product: Product being inquired about
        method: Contact method (whatsapp, phone, email)
    """
    masked_phone = phone[:4] + "****" + phone[-2:] if len(phone) > 6 else "***"

    logger.info(
        "seller_contact",
        category=EventCategory.CONTACT.value,
        action="contact_initiated",
        seller=seller,
        phone_masked=masked_phone,
        product=product,
        method=method,
    )


def log_api_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    user_agent: Optional[str] = None,
    error: Optional[str] = None,
):
    """Log API request.

    Args:
        method: HTTP method
        path: Request path
        status_code: Response status code
        duration_ms: Request duration
        user_agent: Client user agent
        error: Error message if failed
    """
    level = "info" if status_code < 400 else "warning" if status_code < 500 else "error"
    getattr(logger, level)(
        "api_request",
        category=EventCategory.SYSTEM.value,
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        user_agent=user_agent[:100] if user_agent else None,
        error=error,
    )


def log_cache_operation(
    operation: str,  # "hit", "miss", "set", "clear"
    key_prefix: str,
    duration_ms: float,
    hit_rate: Optional[float] = None,
):
    """Log cache operation.

    Args:
        operation: Type of cache operation
        key_prefix: Cache key prefix
        duration_ms: Operation duration
        hit_rate: Current cache hit rate
    """
    logger.debug(
        "cache_operation",
        category=EventCategory.PERFORMANCE.value,
        operation=operation,
        key_prefix=key_prefix,
        duration_ms=duration_ms,
        hit_rate=hit_rate,
    )


def log_error(
    error_type: str,
    message: str,
    stack_trace: Optional[str] = None,
    context: Optional[dict] = None,
):
    """Log an error.

    Args:
        error_type: Type/class of error
        message: Error message
        stack_trace: Full stack trace
        context: Additional context
    """
    logger.error(
        "error",
        category=EventCategory.ERROR.value,
        error_type=error_type,
        message=message,
        stack_trace=stack_trace,
        context=context or {},
    )


def log_business_event(
    event: str,
    data: dict,
):
    """Log a business/conversion event.

    Args:
        event: Event name (e.g., "draft_sent", "negotiation_started")
        data: Event data
    """
    logger.info(
        "business_event",
        category=EventCategory.NEGOTIATION.value,
        event=event,
        data=data,
    )


# Context manager for timing operations
class LogTimer:
    """Context manager for timing and logging operations."""

    def __init__(
        self,
        operation: str,
        category: EventCategory = EventCategory.PERFORMANCE,
        **extra_fields,
    ):
        self.operation = operation
        self.category = category
        self.extra_fields = extra_fields
        self.start_time: float = 0
        self.duration_ms: float = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000

        if exc_type is not None:
            logger.error(
                self.operation,
                category=self.category.value,
                duration_ms=self.duration_ms,
                success=False,
                error=str(exc_val),
                **self.extra_fields,
            )
        else:
            logger.info(
                self.operation,
                category=self.category.value,
                duration_ms=self.duration_ms,
                success=True,
                **self.extra_fields,
            )

        return False  # Don't suppress exceptions
