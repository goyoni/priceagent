"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
