"""API routes for shopping list price search."""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents import Runner
from src.agents.product_research import product_research_agent
from src.observability import ObservabilityHooks, get_trace_store
from src.state.models import ShoppingListItem, PriceSearchSession, PriceSearchStatus
import structlog

router = APIRouter(prefix="/api/shopping-list", tags=["shopping-list"])
logger = structlog.get_logger()

# In-memory store for search sessions (in production, use database)
_search_sessions: dict[str, PriceSearchSession] = {}


class ShoppingListItemRequest(BaseModel):
    """Request model for a shopping list item."""
    product_name: str
    model_number: Optional[str] = None


class StartSearchRequest(BaseModel):
    """Request to start a price search for shopping list items."""
    items: list[ShoppingListItemRequest]
    country: str = "IL"


class StartSearchResponse(BaseModel):
    """Response from starting a price search."""
    session_id: str
    trace_id: str
    status: str


class SearchStatusResponse(BaseModel):
    """Response for search status check."""
    session_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    trace_id: Optional[str] = None
    error: Optional[str] = None


@router.post("/search-prices")
async def start_price_search(request: StartSearchRequest) -> StartSearchResponse:
    """Start a background price search for shopping list items.

    Creates a snapshot of the current items and triggers search_multiple_products.
    User can continue browsing while search runs in background.
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="No items to search")

    # Create session with snapshot of items
    snapshot = [
        ShoppingListItem(
            product_name=item.product_name,
            model_number=item.model_number,
            source="manual",
        )
        for item in request.items
    ]

    session = PriceSearchSession(
        list_snapshot=snapshot,
        country=request.country,
        status=PriceSearchStatus.RUNNING,
    )

    store = get_trace_store()
    hooks = ObservabilityHooks(store)

    # Build search query
    product_names = [item.model_number or item.product_name for item in request.items]
    if len(product_names) == 1:
        prompt = f"Search for: {product_names[0]}"
    else:
        prompt = f"Search for multiple products: {', '.join(product_names)}"

    # Start trace
    trace = await hooks.start_trace(input_prompt=prompt)
    session.trace_id = trace.id

    # Store session
    _search_sessions[session.id] = session

    # Run search in background
    async def run_search():
        try:
            result = await Runner.run(
                product_research_agent,
                prompt,
                hooks=hooks,
            )
            await hooks.end_trace(final_output=result.final_output)

            # Update session status
            session.status = PriceSearchStatus.COMPLETED
            session.completed_at = datetime.now()
            logger.info(
                "price_search_completed",
                session_id=session.id,
                trace_id=trace.id,
            )

        except Exception as e:
            await hooks.end_trace(error=str(e))
            session.status = PriceSearchStatus.FAILED
            session.error = str(e)
            session.completed_at = datetime.now()
            logger.error(
                "price_search_failed",
                session_id=session.id,
                trace_id=trace.id,
                error=str(e),
            )

    asyncio.create_task(run_search())

    logger.info(
        "price_search_started",
        session_id=session.id,
        trace_id=trace.id,
        item_count=len(request.items),
        country=request.country,
    )

    return StartSearchResponse(
        session_id=session.id,
        trace_id=trace.id,
        status="started",
    )


@router.get("/search-status/{session_id}")
async def get_search_status(session_id: str) -> SearchStatusResponse:
    """Check the status of a price search session."""
    session = _search_sessions.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Search session not found")

    return SearchStatusResponse(
        session_id=session.id,
        status=session.status.value,
        started_at=session.started_at.isoformat(),
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        trace_id=session.trace_id,
        error=session.error,
    )


@router.get("/sessions")
async def list_sessions() -> list[SearchStatusResponse]:
    """List all search sessions (for debugging)."""
    return [
        SearchStatusResponse(
            session_id=session.id,
            status=session.status.value,
            started_at=session.started_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            trace_id=session.trace_id,
            error=session.error,
        )
        for session in _search_sessions.values()
    ]
