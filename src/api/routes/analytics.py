"""Analytics API routes for receiving client-side events."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.logging import log_user_action, UserAction, logger

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class AnalyticsEvent(BaseModel):
    """Client-side analytics event."""
    category: str
    action: str
    label: Optional[str] = None
    value: Optional[float] = None
    data: Optional[dict] = None
    timestamp: int


class EventBatch(BaseModel):
    """Batch of analytics events."""
    events: list[AnalyticsEvent]
    session_id: Optional[str] = None


# Map client actions to server UserAction enum
ACTION_MAP = {
    ("page_view", "view"): UserAction.PAGE_VIEW,
    ("search", "submit"): UserAction.SEARCH_SUBMIT,
    ("result_interaction", "click"): UserAction.RESULT_CLICK,
    ("contact", "whatsapp"): UserAction.WHATSAPP_CLICK,
    ("result_interaction", "generate_draft"): UserAction.DRAFT_GENERATE,
    ("result_interaction", "copy_draft"): UserAction.DRAFT_COPY,
}


@router.post("/events")
async def receive_events(batch: EventBatch, request: Request):
    """Receive analytics events from client.

    Args:
        batch: Batch of events
        request: FastAPI request

    Returns:
        Acknowledgment
    """
    session_id = batch.session_id or request.headers.get("X-Session-ID")

    for event in batch.events:
        # Map to UserAction if possible
        action_key = (event.category, event.action)
        user_action = ACTION_MAP.get(action_key)

        if user_action:
            log_user_action(
                action=user_action,
                data={
                    "label": event.label,
                    "value": event.value,
                    "session_id": session_id,
                    **(event.data or {}),
                },
            )
        else:
            # Log as generic event
            logger.info(
                "client_event",
                category=event.category,
                action=event.action,
                label=event.label,
                value=event.value,
                data=event.data,
                session_id=session_id,
                client_timestamp=event.timestamp,
            )

    return {"received": len(batch.events)}


@router.get("/health")
async def analytics_health():
    """Health check for analytics endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
