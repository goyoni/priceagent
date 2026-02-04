"""Trace store with SQLite persistence and WebSocket pub/sub."""

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import WebSocket
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.db.base import get_async_session_factory
from src.db.models import SpanModel, TraceModel

from .models import OperationalSummary, Span, SpanStatus, Trace, TraceEvent


def _trace_to_model(trace: Trace) -> TraceModel:
    """Convert Pydantic Trace to SQLAlchemy TraceModel."""
    return TraceModel(
        id=trace.id,
        session_id=trace.session_id,
        parent_trace_id=trace.parent_trace_id,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        status=trace.status.value if isinstance(trace.status, SpanStatus) else trace.status,
        input_prompt=trace.input_prompt,
        final_output=trace.final_output,
        total_tokens=trace.total_tokens,
        total_input_tokens=trace.total_input_tokens,
        total_output_tokens=trace.total_output_tokens,
        total_duration_ms=trace.total_duration_ms,
        operational_summary_json=trace.operational_summary.model_dump_json() if trace.operational_summary else None,
        error=trace.error,
    )


def _model_to_trace(model: TraceModel, include_spans: bool = False) -> Trace:
    """Convert SQLAlchemy TraceModel to Pydantic Trace."""
    operational_summary = OperationalSummary()
    if model.operational_summary_json:
        try:
            operational_summary = OperationalSummary.model_validate_json(model.operational_summary_json)
        except Exception:
            pass

    trace = Trace(
        id=model.id,
        session_id=model.session_id,
        parent_trace_id=model.parent_trace_id,
        started_at=model.started_at,
        ended_at=model.ended_at,
        status=SpanStatus(model.status) if model.status else SpanStatus.RUNNING,
        input_prompt=model.input_prompt,
        final_output=model.final_output,
        total_tokens=model.total_tokens or 0,
        total_input_tokens=model.total_input_tokens or 0,
        total_output_tokens=model.total_output_tokens or 0,
        total_duration_ms=model.total_duration_ms,
        operational_summary=operational_summary,
        error=model.error,
        spans=[],
    )

    if include_spans and model.spans:
        trace.spans = [_model_to_span(s) for s in model.spans]

    return trace


def _span_to_model(span: Span) -> SpanModel:
    """Convert Pydantic Span to SQLAlchemy SpanModel."""
    return SpanModel(
        id=span.id,
        trace_id=span.trace_id,
        parent_span_id=span.parent_span_id,
        span_type=span.span_type.value if hasattr(span.span_type, 'value') else span.span_type,
        name=span.name,
        started_at=span.started_at,
        ended_at=span.ended_at,
        duration_ms=span.duration_ms,
        status=span.status.value if isinstance(span.status, SpanStatus) else span.status,
        system_prompt=span.system_prompt,
        input_messages_json=json.dumps(span.input_messages) if span.input_messages else None,
        output_content=span.output_content,
        input_tokens=span.input_tokens,
        output_tokens=span.output_tokens,
        model=span.model,
        tool_name=span.tool_name,
        tool_input_json=json.dumps(span.tool_input) if span.tool_input else None,
        tool_output_json=json.dumps(span.tool_output, default=str) if span.tool_output else None,
        cached=span.cached,
        from_agent=span.from_agent,
        to_agent=span.to_agent,
        error=span.error,
    )


def _model_to_span(model: SpanModel) -> Span:
    """Convert SQLAlchemy SpanModel to Pydantic Span."""
    from .models import SpanType

    input_messages = None
    if model.input_messages_json:
        try:
            input_messages = json.loads(model.input_messages_json)
        except Exception:
            pass

    tool_input = None
    if model.tool_input_json:
        try:
            tool_input = json.loads(model.tool_input_json)
        except Exception:
            pass

    tool_output = None
    if model.tool_output_json:
        try:
            tool_output = json.loads(model.tool_output_json)
        except Exception:
            pass

    return Span(
        id=model.id,
        trace_id=model.trace_id,
        parent_span_id=model.parent_span_id,
        span_type=SpanType(model.span_type) if model.span_type else SpanType.TOOL_CALL,
        name=model.name,
        started_at=model.started_at,
        ended_at=model.ended_at,
        duration_ms=model.duration_ms,
        status=SpanStatus(model.status) if model.status else SpanStatus.RUNNING,
        system_prompt=model.system_prompt,
        input_messages=input_messages,
        output_content=model.output_content,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        model=model.model,
        tool_name=model.tool_name,
        tool_input=tool_input,
        tool_output=tool_output,
        cached=model.cached,
        from_agent=model.from_agent,
        to_agent=model.to_agent,
        error=model.error,
    )


class TraceStore:
    """Storage for traces with WebSocket notifications and SQLite persistence."""

    def __init__(self, max_traces: int = 100, storage_path: Optional[Path] = None):
        self.max_traces = max_traces
        # storage_path kept for backwards compatibility but not used
        self._websockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        # In-memory cache for active traces (running traces)
        self._active_traces: dict[str, Trace] = {}
        self._active_spans: dict[str, list[Span]] = defaultdict(list)

    async def create_trace(self, input_prompt: str, session_id: Optional[str] = None, parent_trace_id: Optional[str] = None) -> Optional[Trace]:
        """Create and store a new trace. Returns None if tracing is disabled."""
        # Check if tracing is enabled (import here to avoid circular imports)
        from src.config.settings import settings
        if not settings.trace_enabled:
            return None

        trace = Trace(input_prompt=input_prompt, session_id=session_id, parent_trace_id=parent_trace_id)

        async with self._lock:
            # Store in memory for fast access
            self._active_traces[trace.id] = trace

            # Persist to database
            await self._save_trace_to_db(trace)

            # Evict old traces if limit reached
            await self._evict_old_traces()

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
            trace = self._active_traces.get(trace_id)
            if not trace:
                # Try loading from database
                trace = await self._load_trace_from_db(trace_id)
                if not trace:
                    return

            trace.complete(final_output=final_output, error=error)

            # Update in database
            await self._update_trace_in_db(trace)

            # Move spans to database and clear from memory
            if trace_id in self._active_spans:
                await self._save_spans_to_db(trace_id, self._active_spans[trace_id])
                del self._active_spans[trace_id]

            # Remove from active traces
            self._active_traces.pop(trace_id, None)

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
            self._active_spans[trace_id].append(span)

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
            spans = self._active_spans.get(trace_id, [])
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
                trace = self._active_traces.get(trace_id)
                if trace:
                    trace.add_tokens(
                        input_tokens=span.input_tokens or 0,
                        output_tokens=span.output_tokens or 0
                    )

        await self._broadcast(TraceEvent(
            event_type="span_ended",
            trace_id=trace_id,
            span_id=span_id,
            data=span.model_dump()
        ))

    def get_trace(self, trace_id: str, include_spans: bool = True) -> Optional[Trace]:
        """Get a trace by ID (sync version for backwards compatibility)."""
        # Check in-memory cache first
        trace = self._active_traces.get(trace_id)
        if trace:
            trace = trace.model_copy()
            if include_spans:
                trace.spans = self._active_spans.get(trace_id, [])
            return trace

        # Need to load from database - run in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._load_trace_from_db(trace_id, include_spans))
                    return future.result(timeout=5)
            else:
                return loop.run_until_complete(self._load_trace_from_db(trace_id, include_spans))
        except Exception:
            return None

    async def get_trace_async(self, trace_id: str, include_spans: bool = True) -> Optional[Trace]:
        """Get a trace by ID (async version)."""
        # Check in-memory cache first
        trace = self._active_traces.get(trace_id)
        if trace:
            trace = trace.model_copy()
            if include_spans:
                trace.spans = self._active_spans.get(trace_id, [])
            return trace

        # Load from database
        return await self._load_trace_from_db(trace_id, include_spans)

    async def update_trace(self, trace_id: str, trace: Trace) -> None:
        """Update a trace in the store."""
        async with self._lock:
            if trace_id in self._active_traces:
                self._active_traces[trace_id] = trace
            await self._update_trace_in_db(trace)

    def get_traces(
        self,
        limit: int = 50,
        include_running: bool = True
    ) -> list[Trace]:
        """Get recent traces (sync version for backwards compatibility)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.get_traces_async(limit, include_running))
                    return future.result(timeout=10)
            else:
                return loop.run_until_complete(self.get_traces_async(limit, include_running))
        except Exception:
            return []

    async def get_traces_async(
        self,
        limit: int = 50,
        include_running: bool = True
    ) -> list[Trace]:
        """Get recent traces (async version)."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            query = select(TraceModel).order_by(TraceModel.started_at.desc()).limit(limit)

            if not include_running:
                query = query.where(TraceModel.status != SpanStatus.RUNNING.value)

            result = await session.execute(query)
            models = result.scalars().all()

            return [_model_to_trace(m, include_spans=False) for m in models]

    def get_running_traces(self) -> list[Trace]:
        """Get currently running traces."""
        return list(self._active_traces.values())

    def get_span(self, trace_id: str, span_id: str) -> Optional[Span]:
        """Get a specific span."""
        spans = self._active_spans.get(trace_id, [])
        return next((s for s in spans if s.id == span_id), None)

    def get_spans(self, trace_id: str) -> list[Span]:
        """Get all spans for a trace."""
        return self._active_spans.get(trace_id, [])

    async def delete_trace(self, trace_id: str) -> bool:
        """Delete a trace by ID. Returns True if deleted, False if not found."""
        async with self._lock:
            # Remove from memory
            self._active_traces.pop(trace_id, None)
            self._active_spans.pop(trace_id, None)

            # Remove from database
            session_factory = get_async_session_factory()
            async with session_factory() as session:
                result = await session.execute(
                    delete(TraceModel).where(TraceModel.id == trace_id)
                )
                await session.commit()
                return result.rowcount > 0

    async def clear_stale_traces(self, stuck_timeout_minutes: int = 60) -> dict:
        """Clear stale traces (stuck in RUNNING state for too long)."""
        now = datetime.utcnow()
        stuck_threshold = now - timedelta(minutes=stuck_timeout_minutes)

        deleted_stuck = 0

        # Clear from memory
        trace_ids_to_delete = []
        for trace_id, trace in list(self._active_traces.items()):
            if trace.status == SpanStatus.RUNNING:
                if trace.started_at < stuck_threshold:
                    trace_ids_to_delete.append(trace_id)
                    deleted_stuck += 1

        for trace_id in trace_ids_to_delete:
            self._active_traces.pop(trace_id, None)
            self._active_spans.pop(trace_id, None)

        # Clear from database
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                delete(TraceModel).where(
                    TraceModel.status == SpanStatus.RUNNING.value,
                    TraceModel.started_at < stuck_threshold
                )
            )
            await session.commit()
            deleted_stuck += result.rowcount

        return {
            "deleted_stuck": deleted_stuck,
            "total_deleted": deleted_stuck,
        }

    async def clear_all_traces(self) -> int:
        """Clear all traces from the store."""
        # Clear memory
        count = len(self._active_traces)
        self._active_traces.clear()
        self._active_spans.clear()

        # Clear database
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(delete(TraceModel))
            await session.commit()
            count += result.rowcount

        return count

    # Database operations

    async def _save_trace_to_db(self, trace: Trace) -> None:
        """Save a trace to the database."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            model = _trace_to_model(trace)
            session.add(model)
            await session.commit()

    async def _update_trace_in_db(self, trace: Trace) -> None:
        """Update a trace in the database."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(TraceModel).where(TraceModel.id == trace.id)
            )
            model = result.scalar_one_or_none()

            if model:
                model.session_id = trace.session_id
                model.parent_trace_id = trace.parent_trace_id
                model.ended_at = trace.ended_at
                model.status = trace.status.value if isinstance(trace.status, SpanStatus) else trace.status
                model.final_output = trace.final_output
                model.total_tokens = trace.total_tokens
                model.total_input_tokens = trace.total_input_tokens
                model.total_output_tokens = trace.total_output_tokens
                model.total_duration_ms = trace.total_duration_ms
                model.operational_summary_json = trace.operational_summary.model_dump_json() if trace.operational_summary else None
                model.error = trace.error
                await session.commit()

    async def _save_spans_to_db(self, trace_id: str, spans: list[Span]) -> None:
        """Save spans to the database."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            for span in spans:
                model = _span_to_model(span)
                session.add(model)
            await session.commit()

    async def _load_trace_from_db(self, trace_id: str, include_spans: bool = True) -> Optional[Trace]:
        """Load a trace from the database."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            query = select(TraceModel).where(TraceModel.id == trace_id)
            if include_spans:
                query = query.options(selectinload(TraceModel.spans))

            result = await session.execute(query)
            model = result.scalar_one_or_none()

            if model:
                return _model_to_trace(model, include_spans=include_spans)
            return None

    async def _evict_old_traces(self) -> None:
        """Evict old traces if limit reached."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            # Count traces
            count_result = await session.execute(
                select(TraceModel.id).order_by(TraceModel.started_at.desc())
            )
            all_ids = [row[0] for row in count_result.fetchall()]

            if len(all_ids) > self.max_traces:
                # Get IDs to delete
                ids_to_delete = all_ids[self.max_traces:]
                await session.execute(
                    delete(TraceModel).where(TraceModel.id.in_(ids_to_delete))
                )
                await session.commit()

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
