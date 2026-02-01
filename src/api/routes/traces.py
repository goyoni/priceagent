"""FastAPI routes for trace data."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from typing import List

from src.observability import get_trace_store

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("/")
async def list_traces(limit: int = 50):
    """List recent traces with summary stats."""
    store = get_trace_store()
    traces = store.get_traces(limit=limit)
    return {
        "traces": [
            {
                "id": t.id,
                "session_id": t.session_id,
                "parent_trace_id": t.parent_trace_id,
                "input_prompt": t.input_prompt[:100] + "..." if len(t.input_prompt) > 100 else t.input_prompt,
                "status": t.status.value,
                "started_at": t.started_at.isoformat(),
                "ended_at": t.ended_at.isoformat() if t.ended_at else None,
                "total_duration_ms": t.total_duration_ms,
                "total_tokens": t.total_tokens,
                "total_input_tokens": t.total_input_tokens,
                "total_output_tokens": t.total_output_tokens,
                "error": t.error,
            }
            for t in traces
        ]
    }


@router.get("/running")
async def list_running_traces():
    """Get currently running traces."""
    store = get_trace_store()
    traces = store.get_running_traces()
    return {
        "traces": [
            {
                "id": t.id,
                "input_prompt": t.input_prompt[:100] + "..." if len(t.input_prompt) > 100 else t.input_prompt,
                "started_at": t.started_at.isoformat(),
                "total_tokens": t.total_tokens,
            }
            for t in traces
        ]
    }


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    """Get a trace with all its spans."""
    store = get_trace_store()
    trace = store.get_trace(trace_id, include_spans=True)

    if not trace:
        return JSONResponse(status_code=404, content={"error": "Trace not found"})

    return {
        "id": trace.id,
        "session_id": trace.session_id,
        "parent_trace_id": trace.parent_trace_id,
        "input_prompt": trace.input_prompt,
        "final_output": trace.final_output,
        "status": trace.status.value,
        "started_at": trace.started_at.isoformat(),
        "ended_at": trace.ended_at.isoformat() if trace.ended_at else None,
        "total_duration_ms": trace.total_duration_ms,
        "total_tokens": trace.total_tokens,
        "total_input_tokens": trace.total_input_tokens,
        "total_output_tokens": trace.total_output_tokens,
        "error": trace.error,
        "operational_summary": (
            trace.operational_summary.model_dump()
            if trace.operational_summary
            else {
                "google_searches": 0,
                "google_searches_cached": 0,
                "zap_searches": 0,
                "zap_searches_cached": 0,
                "page_scrapes": 0,
                "page_scrapes_cached": 0,
                "errors": [],
                "warnings": [],
                "prices_extracted": 0,
                "prices_failed": 0,
                "contacts_extracted": 0,
                "contacts_failed": 0,
            }
        ),
        "spans": [
            {
                "id": s.id,
                "parent_span_id": s.parent_span_id,
                "span_type": s.span_type.value,
                "name": s.name,
                "status": s.status.value,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "duration_ms": s.duration_ms,
                "system_prompt": s.system_prompt,
                "input_messages": s.input_messages,
                "output_content": s.output_content,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "model": s.model,
                "tool_name": s.tool_name,
                "tool_input": s.tool_input,
                "tool_output": s.tool_output,
                "cached": s.cached,  # Add cached field
                "from_agent": s.from_agent,
                "to_agent": s.to_agent,
                "error": s.error,
            }
            for s in trace.spans
        ]
    }


@router.delete("/{trace_id}")
async def delete_trace(trace_id: str):
    """Delete a trace by ID."""
    store = get_trace_store()
    success = store.delete_trace(trace_id)

    if not success:
        return JSONResponse(status_code=404, content={"error": "Trace not found"})

    return {"status": "deleted", "trace_id": trace_id}


@router.websocket("/ws")
async def trace_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time trace updates."""
    await websocket.accept()
    store = get_trace_store()
    await store.register_websocket(websocket)

    try:
        # Keep connection alive
        while True:
            # Wait for any message (ping/pong or close)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await store.unregister_websocket(websocket)
