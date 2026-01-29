"""Human-in-the-loop approval tool for agents."""

import asyncio
from datetime import datetime
from typing import Optional

import structlog

from src.state.models import ApprovalRequest, ApprovalStatus
from src.state.store import StateStore
from src.config.settings import settings

logger = structlog.get_logger()

# Global approval queue (for awaiting human decisions)
_pending_events: dict[str, asyncio.Event] = {}


class ApprovalQueue:
    """Manages human approval requests."""

    def __init__(self, store: StateStore):
        self.store = store
        self.timeout = settings.approval_timeout_seconds

    async def request_approval(
        self,
        negotiation_id: str,
        product_name: str,
        seller_name: str,
        original_price: float,
        offered_price: float,
        conversation_summary: str,
        market_average: Optional[float] = None,
    ) -> ApprovalRequest:
        """Request human approval for a negotiation decision.

        This will block until a human approves, rejects, or the request times out.

        Args:
            negotiation_id: ID of the negotiation
            product_name: Name of the product being negotiated
            seller_name: Name of the seller
            original_price: Original listed price
            offered_price: Current offered price
            conversation_summary: Summary of the negotiation so far
            market_average: Optional market average price for comparison

        Returns:
            The approval request with the human's decision
        """
        discount = ((original_price - offered_price) / original_price) * 100

        request = ApprovalRequest(
            negotiation_id=negotiation_id,
            product_name=product_name,
            seller_name=seller_name,
            original_price=original_price,
            offered_price=offered_price,
            discount_percentage=round(discount, 1),
            market_average=market_average,
            conversation_summary=conversation_summary,
        )

        # Save to database
        await self.store.save_approval(request)

        # Create event for waiting
        event = asyncio.Event()
        _pending_events[request.id] = event

        logger.info(
            "Approval requested",
            request_id=request.id,
            product=product_name,
            discount=f"{discount:.1f}%",
        )

        # Wait for human decision (with timeout)
        try:
            await asyncio.wait_for(event.wait(), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.warning("Approval request timed out", request_id=request.id)
            request.status = ApprovalStatus.REJECTED
            request.human_response = "Timed out - auto-rejected"
            request.resolved_at = datetime.now()
            await self.store.save_approval(request)
        finally:
            _pending_events.pop(request.id, None)

        # Get updated request from database
        updated = await self.store.get_approval(request.id)
        return updated or request

    async def submit_decision(
        self,
        request_id: str,
        approved: bool,
        counter_offer: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Submit a human decision for an approval request.

        Args:
            request_id: ID of the approval request
            approved: Whether to approve or reject
            counter_offer: Optional counter-offer amount
            notes: Optional notes from the human

        Returns:
            True if the decision was recorded successfully
        """
        request = await self.store.get_approval(request_id)
        if not request:
            logger.error("Approval request not found", request_id=request_id)
            return False

        if request.status != ApprovalStatus.PENDING:
            logger.warning("Approval already resolved", request_id=request_id)
            return False

        # Update status
        if counter_offer is not None:
            request.status = ApprovalStatus.COUNTER_OFFER
            request.counter_offer_amount = counter_offer
        elif approved:
            request.status = ApprovalStatus.APPROVED
        else:
            request.status = ApprovalStatus.REJECTED

        request.human_response = notes
        request.resolved_at = datetime.now()

        await self.store.save_approval(request)

        logger.info(
            "Approval decision submitted",
            request_id=request_id,
            status=request.status.value,
        )

        # Wake up waiting agent
        if request_id in _pending_events:
            _pending_events[request_id].set()

        return True


# Singleton instance
_approval_queue: Optional[ApprovalQueue] = None


def get_approval_queue(store: StateStore) -> ApprovalQueue:
    """Get or create the approval queue instance."""
    global _approval_queue
    if _approval_queue is None:
        _approval_queue = ApprovalQueue(store)
    return _approval_queue


# Tool functions for agents


async def request_human_approval(
    negotiation_id: str,
    product_name: str,
    seller_name: str,
    original_price: float,
    offered_price: float,
    conversation_summary: str,
) -> str:
    """Request human approval for a negotiation decision.

    Use this when:
    - The discount offered is significant (>10%)
    - You're about to accept a final offer
    - Something seems unusual about the negotiation

    Args:
        negotiation_id: ID of the current negotiation
        product_name: Name of the product
        seller_name: Name of the seller
        original_price: Original listed price
        offered_price: Current offered price
        conversation_summary: Brief summary of the negotiation

    Returns:
        A message with the human's decision
    """
    from src.state.store import StateStore

    store = StateStore()
    queue = get_approval_queue(store)

    result = await queue.request_approval(
        negotiation_id=negotiation_id,
        product_name=product_name,
        seller_name=seller_name,
        original_price=original_price,
        offered_price=offered_price,
        conversation_summary=conversation_summary,
    )

    if result.status == ApprovalStatus.APPROVED:
        return "APPROVED: Human approved this offer. You may proceed with acceptance."
    elif result.status == ApprovalStatus.COUNTER_OFFER:
        return f"COUNTER-OFFER: Human wants to counter with {result.counter_offer_amount}. Send this counter-offer to the seller."
    else:
        reason = result.human_response or "No reason provided"
        return f"REJECTED: Human rejected this offer. Reason: {reason}"


def should_request_approval(
    original_price: float,
    offered_price: float,
    is_final_offer: bool = False,
) -> tuple[bool, str]:
    """Check if human approval should be requested.

    Args:
        original_price: Original listed price
        offered_price: Current offered price
        is_final_offer: Whether this is a final offer

    Returns:
        Tuple of (needs_approval, reason)
    """
    discount = ((original_price - offered_price) / original_price) * 100

    if is_final_offer:
        return True, "Final offer requires human approval"

    if discount > settings.min_discount_for_approval:
        return True, f"Discount of {discount:.1f}% exceeds threshold"

    if offered_price > settings.max_auto_approve_amount:
        return True, f"Amount ${offered_price} exceeds auto-approve limit"

    return False, ""
