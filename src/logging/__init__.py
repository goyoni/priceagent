"""Comprehensive logging module for production monitoring.

Provides structured logging for:
- User interactions (searches, clicks, contacts)
- System operations (scraping, API calls, errors)
- Performance metrics (latency, cache hits)
- Business events (negotiations, conversions)
"""

import json
import time
from datetime import datetime
from enum import Enum
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


# Configure the production logger
def configure_production_logging(log_file: Optional[Path] = None):
    """Configure structured logging for production.

    Args:
        log_file: Optional path to log file (in addition to stdout)
    """
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
    ]

    # Use JSON renderer for production (easier to parse)
    import os
    if os.environ.get("ENVIRONMENT") == "production":
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
