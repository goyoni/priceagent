"""State storage using SQLAlchemy for PostgreSQL/SQLite support."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from src.db.base import get_async_session_factory
from src.db.models import ApprovalModel, NegotiationModel, SessionModel

from .models import (
    ApprovalRequest,
    ApprovalStatus,
    NegotiationState,
    NegotiationStatus,
    PurchaseSession,
)


class StateStore:
    """Async SQLAlchemy-based state storage with PostgreSQL/SQLite support."""

    def __init__(self):
        pass

    async def save_negotiation(self, state: NegotiationState) -> None:
        """Save or update a negotiation state."""
        state.updated_at = datetime.now()

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            # Check if exists
            result = await session.execute(
                select(NegotiationModel).where(NegotiationModel.id == state.id)
            )
            model = result.scalar_one_or_none()

            if model:
                model.product_id = state.product.id
                model.seller_id = state.seller.id
                model.status = state.status.value
                model.data_json = state.model_dump_json()
            else:
                model = NegotiationModel(
                    id=state.id,
                    product_id=state.product.id,
                    seller_id=state.seller.id,
                    status=state.status.value,
                    data_json=state.model_dump_json(),
                )
                session.add(model)

            await session.commit()

    async def get_negotiation(self, negotiation_id: str) -> Optional[NegotiationState]:
        """Retrieve a negotiation by ID."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(NegotiationModel).where(NegotiationModel.id == negotiation_id)
            )
            model = result.scalar_one_or_none()

            if model:
                return NegotiationState.model_validate_json(model.data_json)
        return None

    async def get_negotiations_by_status(
        self, status: NegotiationStatus
    ) -> list[NegotiationState]:
        """Get all negotiations with a specific status."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(NegotiationModel).where(NegotiationModel.status == status.value)
            )
            models = result.scalars().all()
            return [NegotiationState.model_validate_json(m.data_json) for m in models]

    async def get_active_negotiations(self) -> list[NegotiationState]:
        """Get all non-completed negotiations."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(NegotiationModel).where(
                    NegotiationModel.status.not_in(["completed", "failed"])
                )
            )
            models = result.scalars().all()
            return [NegotiationState.model_validate_json(m.data_json) for m in models]

    async def save_approval(self, request: ApprovalRequest) -> None:
        """Save or update an approval request."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            # Check if exists
            result = await session.execute(
                select(ApprovalModel).where(ApprovalModel.id == request.id)
            )
            model = result.scalar_one_or_none()

            if model:
                model.negotiation_id = request.negotiation_id
                model.status = request.status.value
                model.data_json = request.model_dump_json()
                model.resolved_at = request.resolved_at
            else:
                model = ApprovalModel(
                    id=request.id,
                    negotiation_id=request.negotiation_id,
                    status=request.status.value,
                    data_json=request.model_dump_json(),
                    resolved_at=request.resolved_at,
                )
                session.add(model)

            await session.commit()

    async def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Retrieve an approval request by ID."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(ApprovalModel).where(ApprovalModel.id == approval_id)
            )
            model = result.scalar_one_or_none()

            if model:
                return ApprovalRequest.model_validate_json(model.data_json)
        return None

    async def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(ApprovalModel).where(
                    ApprovalModel.status == ApprovalStatus.PENDING.value
                )
            )
            models = result.scalars().all()
            return [ApprovalRequest.model_validate_json(m.data_json) for m in models]

    async def save_session(self, session_obj: PurchaseSession) -> None:
        """Save or update a purchase session."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            # Check if exists
            result = await session.execute(
                select(SessionModel).where(SessionModel.id == session_obj.id)
            )
            model = result.scalar_one_or_none()

            if model:
                model.status = session_obj.status
                model.data_json = session_obj.model_dump_json()
                model.completed_at = session_obj.completed_at
            else:
                model = SessionModel(
                    id=session_obj.id,
                    status=session_obj.status,
                    data_json=session_obj.model_dump_json(),
                    completed_at=session_obj.completed_at,
                )
                session.add(model)

            await session.commit()

    async def get_session(self, session_id: str) -> Optional[PurchaseSession]:
        """Retrieve a purchase session by ID."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            )
            model = result.scalar_one_or_none()

            if model:
                return PurchaseSession.model_validate_json(model.data_json)
        return None
