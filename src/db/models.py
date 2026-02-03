"""SQLAlchemy ORM models."""

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TraceModel(Base):
    """SQLAlchemy model for traces."""

    __tablename__ = "traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    parent_trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")

    # Input/output
    input_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    final_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Aggregated stats
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Operational summary (stored as JSON)
    operational_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Error info
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship to spans
    spans: Mapped[list["SpanModel"]] = relationship(
        "SpanModel", back_populates="trace", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TraceModel(id={self.id}, status={self.status})>"


class SpanModel(Base):
    """SQLAlchemy model for spans."""

    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_span_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    span_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")

    # LLM-specific fields (stored as JSON where complex)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_messages_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Tool-specific fields (stored as JSON where complex)
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_input_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_output_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cached: Mapped[Optional[bool]] = mapped_column(nullable=True)

    # Handoff-specific fields
    from_agent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    to_agent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Error info
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship to trace
    trace: Mapped["TraceModel"] = relationship("TraceModel", back_populates="spans")

    def __repr__(self) -> str:
        return f"<SpanModel(id={self.id}, name={self.name}, status={self.status})>"


class Seller(Base):
    """Seller entity with contact information."""

    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Identification
    seller_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    domain: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )

    # Contact information
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Details
    website_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(10), default="IL")

    # Metrics
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reliability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timestamps
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Seller(id={self.id}, name={self.seller_name}, domain={self.domain})>"

    @property
    def contact(self) -> Optional[str]:
        """Get preferred contact (WhatsApp or phone)."""
        return self.whatsapp_number or self.phone_number


class CategoryCriteria(Base):
    """Product category criteria for discovery."""

    __tablename__ = "category_criteria"

    category: Mapped[str] = mapped_column(String(100), primary_key=True)
    criteria_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="discovered")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<CategoryCriteria(category={self.category}, source={self.source})>"


class NegotiationModel(Base):
    """SQLAlchemy model for negotiations."""

    __tablename__ = "negotiations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    seller_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<NegotiationModel(id={self.id}, status={self.status})>"


class ApprovalModel(Base):
    """SQLAlchemy model for approval requests."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    negotiation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<ApprovalModel(id={self.id}, status={self.status})>"


class SessionModel(Base):
    """SQLAlchemy model for purchase sessions."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<SessionModel(id={self.id}, status={self.status})>"

