"""State storage using SQLite."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from .models import (
    ApprovalRequest,
    ApprovalStatus,
    NegotiationState,
    NegotiationStatus,
    PurchaseSession,
)


class StateStore:
    """Async SQLite-based state storage."""

    def __init__(self, db_path: str | Path = "data/negotiations.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Create database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS negotiations (
                    id TEXT PRIMARY KEY,
                    product_id TEXT,
                    seller_id TEXT,
                    status TEXT,
                    data TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    negotiation_id TEXT,
                    status TEXT,
                    data TEXT,
                    created_at TEXT,
                    resolved_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    status TEXT,
                    data TEXT,
                    created_at TEXT,
                    completed_at TEXT
                )
            """)
            await db.commit()

    async def save_negotiation(self, state: NegotiationState) -> None:
        """Save or update a negotiation state."""
        state.updated_at = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO negotiations
                   (id, product_id, seller_id, status, data, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    state.id,
                    state.product.id,
                    state.seller.id,
                    state.status.value,
                    state.model_dump_json(),
                    state.started_at.isoformat(),
                    state.updated_at.isoformat(),
                ),
            )
            await db.commit()

    async def get_negotiation(self, negotiation_id: str) -> Optional[NegotiationState]:
        """Retrieve a negotiation by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT data FROM negotiations WHERE id = ?", (negotiation_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return NegotiationState.model_validate_json(row[0])
        return None

    async def get_negotiations_by_status(
        self, status: NegotiationStatus
    ) -> list[NegotiationState]:
        """Get all negotiations with a specific status."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT data FROM negotiations WHERE status = ?", (status.value,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [NegotiationState.model_validate_json(row[0]) for row in rows]

    async def get_active_negotiations(self) -> list[NegotiationState]:
        """Get all non-completed negotiations."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT data FROM negotiations WHERE status NOT IN ('completed', 'failed')"
            ) as cursor:
                rows = await cursor.fetchall()
                return [NegotiationState.model_validate_json(row[0]) for row in rows]

    async def save_approval(self, request: ApprovalRequest) -> None:
        """Save or update an approval request."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO approvals
                   (id, negotiation_id, status, data, created_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    request.id,
                    request.negotiation_id,
                    request.status.value,
                    request.model_dump_json(),
                    request.created_at.isoformat(),
                    request.resolved_at.isoformat() if request.resolved_at else None,
                ),
            )
            await db.commit()

    async def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Retrieve an approval request by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT data FROM approvals WHERE id = ?", (approval_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return ApprovalRequest.model_validate_json(row[0])
        return None

    async def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT data FROM approvals WHERE status = ?",
                (ApprovalStatus.PENDING.value,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [ApprovalRequest.model_validate_json(row[0]) for row in rows]

    async def save_session(self, session: PurchaseSession) -> None:
        """Save or update a purchase session."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO sessions
                   (id, status, data, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session.id,
                    session.status,
                    session.model_dump_json(),
                    session.created_at.isoformat(),
                    session.completed_at.isoformat() if session.completed_at else None,
                ),
            )
            await db.commit()

    async def get_session(self, session_id: str) -> Optional[PurchaseSession]:
        """Retrieve a purchase session by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT data FROM sessions WHERE id = ?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return PurchaseSession.model_validate_json(row[0])
        return None
