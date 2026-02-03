"""In-memory trace store with WebSocket pub/sub and disk persistence."""

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import WebSocket

from .models import Span, SpanStatus, Trace, TraceEvent


class TraceStore:
    """Storage for traces with WebSocket notifications and disk persistence."""

    def __init__(self, max_traces: int = 100, storage_path: Optional[Path] = None):
        self.max_traces = max_traces
        self.storage_path = storage_path or Path("data/traces.json")
        self._traces: dict[str, Trace] = {}
        self._spans: dict[str, list[Span]] = defaultdict(list)
        self._trace_order: list[str] = []  # For maintaining order
        self._websockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()

        # Load existing traces from disk
        self._load_from_disk()

    async def create_trace(self, input_prompt: str, session_id: Optional[str] = None, parent_trace_id: Optional[str] = None) -> Optional[Trace]:
        """Create and store a new trace. Returns None if tracing is disabled."""
        # Check if tracing is enabled (import here to avoid circular imports)
        from src.config.settings import settings
        if not settings.trace_enabled:
            return None

        trace = Trace(input_prompt=input_prompt, session_id=session_id, parent_trace_id=parent_trace_id)

        async with self._lock:
            self._traces[trace.id] = trace
            self._trace_order.append(trace.id)

            # Evict old traces if limit reached
            while len(self._trace_order) > self.max_traces:
                old_id = self._trace_order.pop(0)
                self._traces.pop(old_id, None)
                self._spans.pop(old_id, None)

            self._save_to_disk()

        await self._broadcast(TraceEvent(
            event_type="trace_started",
            trace_id=trace.id,
            data=trace.model_dump(exclude={"spans"})
        ))

        return trace

    async def complete_trace(
        self,
        trace_id: str,
        final_output: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Mark a trace as complete."""
        async with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                return

            trace.complete(final_output=final_output, error=error)
            self._save_to_disk()

        await self._broadcast(TraceEvent(
            event_type="trace_ended",
            trace_id=trace_id,
            data=trace.model_dump(exclude={"spans"})
        ))

    async def create_span(
        self,
        trace_id: str,
        span: Span
    ) -> Span:
        """Add a span to a trace."""
        span.trace_id = trace_id

        async with self._lock:
            self._spans[trace_id].append(span)

        await self._broadcast(TraceEvent(
            event_type="span_started",
            trace_id=trace_id,
            span_id=span.id,
            data=span.model_dump()
        ))

        return span

    async def complete_span(
        self,
        trace_id: str,
        span_id: str,
        status: SpanStatus = SpanStatus.COMPLETED,
        error: Optional[str] = None,
        **updates
    ):
        """Mark a span as complete and update its fields."""
        async with self._lock:
            spans = self._spans.get(trace_id, [])
            span = next((s for s in spans if s.id == span_id), None)
            if not span:
                return

            # Update any additional fields
            for key, value in updates.items():
                if hasattr(span, key):
                    setattr(span, key, value)

            span.complete(status=status, error=error)

            # Update trace token counts if this is an LLM span
            if span.input_tokens or span.output_tokens:
                trace = self._traces.get(trace_id)
                if trace:
                    trace.add_tokens(
                        input_tokens=span.input_tokens or 0,
                        output_tokens=span.output_tokens or 0
                    )

            self._save_to_disk()

        await self._broadcast(TraceEvent(
            event_type="span_ended",
            trace_id=trace_id,
            span_id=span_id,
            data=span.model_dump()
        ))

    def get_trace(self, trace_id: str, include_spans: bool = True) -> Optional[Trace]:
        """Get a trace by ID."""
        trace = self._traces.get(trace_id)
        if trace and include_spans:
            trace = trace.model_copy()
            trace.spans = self._spans.get(trace_id, [])
        return trace

    async def update_trace(self, trace_id: str, trace: Trace) -> None:
        """Update a trace in the store.

        Args:
            trace_id: ID of the trace to update
            trace: Updated trace object
        """
        async with self._lock:
            if trace_id in self._traces:
                self._traces[trace_id] = trace
                self._save_to_disk()

    def get_traces(
        self,
        limit: int = 50,
        include_running: bool = True
    ) -> list[Trace]:
        """Get recent traces."""
        traces = []
        for trace_id in reversed(self._trace_order[-limit:]):
            trace = self._traces.get(trace_id)
            if trace:
                if include_running or trace.status != SpanStatus.RUNNING:
                    traces.append(trace)
        return traces

    def get_running_traces(self) -> list[Trace]:
        """Get currently running traces."""
        return [
            t for t in self._traces.values()
            if t.status == SpanStatus.RUNNING
        ]

    def get_span(self, trace_id: str, span_id: str) -> Optional[Span]:
        """Get a specific span."""
        spans = self._spans.get(trace_id, [])
        return next((s for s in spans if s.id == span_id), None)

    def get_spans(self, trace_id: str) -> list[Span]:
        """Get all spans for a trace."""
        return self._spans.get(trace_id, [])

    def delete_trace(self, trace_id: str) -> bool:
        """Delete a trace by ID. Returns True if deleted, False if not found."""
        if trace_id not in self._traces:
            return False

        # Remove from all data structures
        del self._traces[trace_id]
        self._spans.pop(trace_id, None)
        if trace_id in self._trace_order:
            self._trace_order.remove(trace_id)

        self._save_to_disk()
        return True

    def clear_stale_traces(self, stuck_timeout_minutes: int = 60) -> dict:
        """Clear stale traces (stuck in RUNNING state for too long).

        Args:
            stuck_timeout_minutes: Consider traces stuck if running longer than this

        Returns:
            Dict with counts of deleted traces by reason
        """
        now = datetime.now(timezone.utc)
        stuck_threshold = now - timedelta(minutes=stuck_timeout_minutes)

        deleted_stuck = 0
        trace_ids_to_delete = []

        for trace_id, trace in self._traces.items():
            # Delete traces stuck in RUNNING state
            if trace.status == SpanStatus.RUNNING:
                if trace.started_at < stuck_threshold:
                    trace_ids_to_delete.append(trace_id)
                    deleted_stuck += 1

        # Delete collected traces
        for trace_id in trace_ids_to_delete:
            del self._traces[trace_id]
            self._spans.pop(trace_id, None)
            if trace_id in self._trace_order:
                self._trace_order.remove(trace_id)

        if trace_ids_to_delete:
            self._save_to_disk()

        return {
            "deleted_stuck": deleted_stuck,
            "total_deleted": len(trace_ids_to_delete),
        }

    def clear_all_traces(self) -> int:
        """Clear all traces from the store.

        Returns:
            Number of traces deleted
        """
        count = len(self._traces)
        self._traces.clear()
        self._spans.clear()
        self._trace_order.clear()
        self._save_to_disk()
        return count

    # Disk persistence

    def _load_from_disk(self):
        """Load traces from disk on startup."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            for trace_data in data.get("traces", []):
                trace = Trace.model_validate(trace_data["trace"])
                self._traces[trace.id] = trace
                self._trace_order.append(trace.id)

                for span_data in trace_data.get("spans", []):
                    span = Span.model_validate(span_data)
                    self._spans[trace.id].append(span)

            # Trim to max_traces
            while len(self._trace_order) > self.max_traces:
                old_id = self._trace_order.pop(0)
                self._traces.pop(old_id, None)
                self._spans.pop(old_id, None)

        except Exception as e:
            # Don't crash on corrupt data, just start fresh
            print(f"Warning: Could not load traces from disk: {e}")

    def _save_to_disk(self):
        """Save traces to disk."""
        try:
            # Ensure directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "traces": [
                    {
                        "trace": self._traces[trace_id].model_dump(mode="json"),
                        "spans": [s.model_dump(mode="json") for s in self._spans.get(trace_id, [])]
                    }
                    for trace_id in self._trace_order
                    if trace_id in self._traces
                ]
            }

            with open(self.storage_path, "w") as f:
                json.dump(data, f, default=str)

        except Exception as e:
            print(f"Warning: Could not save traces to disk: {e}")

    # WebSocket management

    async def register_websocket(self, ws: WebSocket):
        """Register a WebSocket for updates."""
        self._websockets.add(ws)

    async def unregister_websocket(self, ws: WebSocket):
        """Unregister a WebSocket."""
        self._websockets.discard(ws)

    async def _broadcast(self, event: TraceEvent):
        """Broadcast an event to all connected WebSockets."""
        if not self._websockets:
            return

        message = event.model_dump_json()
        disconnected = set()

        # Iterate over a copy to avoid "Set changed size during iteration"
        for ws in list(self._websockets):
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)

        # Clean up disconnected clients
        self._websockets -= disconnected


# Global store instance
_store: Optional[TraceStore] = None


def get_trace_store() -> TraceStore:
    """Get the global trace store instance."""
    global _store
    if _store is None:
        _store = TraceStore()
    return _store


def set_trace_store(store: TraceStore):
    """Set the global trace store instance."""
    global _store
    _store = store
