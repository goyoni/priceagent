"""FastAPI routes for trace data."""

import secrets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, Header
from fastapi.responses import JSONResponse
from typing import List, Optional

from src.observability import get_trace_store
from src.config.settings import settings

router = APIRouter(prefix="/traces", tags=["traces"])


def verify_dashboard_auth(
    auth_token: Optional[str] = Query(None, alias="auth"),
    x_dashboard_auth: Optional[str] = Header(None),
) -> bool:
    """Verify dashboard authentication.

    In development (no password set), always allows access.
    In production (password set), requires valid auth token.
    """
    # No password configured = development mode, allow all
    if not settings.dashboard_password:
        return True

    # Check query param or header
    token = auth_token or x_dashboard_auth
    if not token:
        raise HTTPException(status_code=401, detail="Dashboard authentication required")

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(token, settings.dashboard_password):
        raise HTTPException(status_code=401, detail="Invalid dashboard credentials")

    return True


def _trace_to_dict(t, truncate_prompt: bool = True) -> dict:
    """Convert a trace to a dictionary representation."""
    prompt = t.input_prompt
    if truncate_prompt and len(prompt) > 100:
        prompt = prompt[:100] + "..."

    return {
        "id": t.id,
        "session_id": t.session_id,
        "parent_trace_id": t.parent_trace_id,
        "input_prompt": prompt,
        "status": t.status.value,
        "started_at": t.started_at.isoformat(),
        "ended_at": t.ended_at.isoformat() if t.ended_at else None,
        "total_duration_ms": t.total_duration_ms,
        "total_tokens": t.total_tokens,
        "total_input_tokens": t.total_input_tokens,
        "total_output_tokens": t.total_output_tokens,
        "error": t.error,
    }


@router.get("/")
async def list_traces(
    limit: int = 50,
    include_children: bool = True,
    _auth: bool = Depends(verify_dashboard_auth),
):
    """List recent traces with summary stats.

    By default, child traces are nested under their parent traces.
    Only root traces (without parent_trace_id) appear at the top level.

    Requires dashboard authentication.
    """
    store = get_trace_store()
    traces = await store.get_traces_async(limit=limit * 2)  # Get more to account for children

    # Separate parent and child traces
    parent_traces = []
    children_by_parent: dict[str, list] = {}

    for t in traces:
        if t.parent_trace_id:
            # This is a child trace
            if t.parent_trace_id not in children_by_parent:
                children_by_parent[t.parent_trace_id] = []
            children_by_parent[t.parent_trace_id].append(t)
        else:
            # This is a parent/root trace
            parent_traces.append(t)

    # Build response with nested children
    result = []
    for t in parent_traces[:limit]:
        trace_dict = _trace_to_dict(t)
        if include_children and t.id in children_by_parent:
            trace_dict["child_traces"] = [
                _trace_to_dict(child) for child in children_by_parent[t.id]
            ]
        else:
            trace_dict["child_traces"] = []
        result.append(trace_dict)

    return {"traces": result}


@router.get("/running")
async def list_running_traces(_auth: bool = Depends(verify_dashboard_auth)):
    """Get currently running traces.

    Requires dashboard authentication.
    """
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


@router.get("/auth/check")
async def check_dashboard_auth_endpoint(_auth: bool = Depends(verify_dashboard_auth)):
    """Check if dashboard authentication is valid.

    Returns 200 if authenticated, 401 if not.
    """
    return {"authenticated": True}


@router.get("/auth/info")
async def get_auth_info():
    """Get authentication requirements.

    Returns whether auth is required (production) or not (development).
    """
    return {
        "auth_required": bool(settings.dashboard_password),
        "environment": settings.environment,
    }


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    """Get a trace with all its spans.

    Note: This endpoint is public to support the discovery feature.
    """
    store = get_trace_store()
    trace = await store.get_trace_async(trace_id, include_spans=True)

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
async def delete_trace(trace_id: str, _auth: bool = Depends(verify_dashboard_auth)):
    """Delete a trace by ID."""
    store = get_trace_store()
    success = await store.delete_trace(trace_id)

    if not success:
        return JSONResponse(status_code=404, content={"error": "Trace not found"})

    return {"status": "deleted", "trace_id": trace_id}


@router.delete("/")
async def clear_all_traces(_auth: bool = Depends(verify_dashboard_auth)):
    """Clear all traces from storage."""
    store = get_trace_store()
    count = await store.clear_all_traces()
    return {"status": "cleared", "deleted_count": count}


@router.post("/cleanup")
async def cleanup_stale_traces(
    stuck_timeout_minutes: int = Query(default=60, ge=1, le=1440),
    _auth: bool = Depends(verify_dashboard_auth),
):
    """Clean up stale traces (stuck in RUNNING state).

    Args:
        stuck_timeout_minutes: Delete traces running longer than this (default: 60)
    """
    store = get_trace_store()
    result = await store.clear_stale_traces(stuck_timeout_minutes=stuck_timeout_minutes)
    return {"status": "cleaned", **result}


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
