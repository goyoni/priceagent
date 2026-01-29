"""Data models for observability traces and spans."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SpanType(str, Enum):
    """Type of span in a trace."""
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    AGENT_RUN = "agent_run"
    HANDOFF = "handoff"


class SpanStatus(str, Enum):
    """Status of a span or trace."""
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class OperationalSummary(BaseModel):
    """Operational statistics for a trace."""

    # Search stats
    google_searches: int = 0
    google_searches_cached: int = 0
    zap_searches: int = 0
    zap_searches_cached: int = 0

    # Scrape stats
    page_scrapes: int = 0
    page_scrapes_cached: int = 0

    # Error/warning tracking
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Price extraction stats
    prices_extracted: int = 0
    prices_failed: int = 0

    # Contact extraction stats
    contacts_extracted: int = 0
    contacts_failed: int = 0

    @property
    def total_searches(self) -> int:
        return self.google_searches + self.zap_searches

    @property
    def total_cached(self) -> int:
        return self.google_searches_cached + self.zap_searches_cached + self.page_scrapes_cached

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


class Span(BaseModel):
    """A single operation within a trace."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str
    parent_span_id: Optional[str] = None
    span_type: SpanType
    name: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: SpanStatus = SpanStatus.RUNNING

    # LLM-specific fields
    system_prompt: Optional[str] = None
    input_messages: Optional[list[dict[str, Any]]] = None
    output_content: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model: Optional[str] = None

    # Tool-specific fields
    tool_name: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    tool_output: Optional[Any] = None
    cached: Optional[bool] = None  # True if result came from cache, False if fresh

    # Handoff-specific fields
    from_agent: Optional[str] = None
    to_agent: Optional[str] = None

    # Error info
    error: Optional[str] = None

    def complete(self, status: SpanStatus = SpanStatus.COMPLETED, error: Optional[str] = None):
        """Mark the span as complete."""
        self.ended_at = datetime.utcnow()
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        self.status = status
        if error:
            self.error = error
            self.status = SpanStatus.ERROR


class Trace(BaseModel):
    """A complete trace of an agent run."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    status: SpanStatus = SpanStatus.RUNNING

    # Input/output
    input_prompt: str
    final_output: Optional[str] = None

    # Aggregated stats
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_ms: Optional[float] = None

    # Operational summary (searches, scrapes, errors, etc.)
    operational_summary: OperationalSummary = Field(default_factory=OperationalSummary)

    # Error info
    error: Optional[str] = None

    # Spans are stored separately in TraceStore but can be attached for API responses
    spans: list[Span] = Field(default_factory=list)

    def complete(self, final_output: Optional[str] = None, error: Optional[str] = None):
        """Mark the trace as complete."""
        self.ended_at = datetime.utcnow()
        self.total_duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        if final_output:
            self.final_output = final_output
        if error:
            self.error = error
            self.status = SpanStatus.ERROR
        else:
            self.status = SpanStatus.COMPLETED

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0):
        """Add token counts to the trace totals."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_tokens = self.total_input_tokens + self.total_output_tokens


class TraceEvent(BaseModel):
    """Event sent via WebSocket for real-time updates."""

    event_type: str  # trace_started, trace_ended, span_started, span_ended
    trace_id: str
    span_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
