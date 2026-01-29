"""State models for the ecommerce negotiator."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())[:8]


class NegotiationStatus(str, Enum):
    """Status of a negotiation."""

    PENDING = "pending"
    RESEARCHING = "researching"
    CONTACTING = "contacting"
    NEGOTIATING = "negotiating"
    AWAITING_APPROVAL = "awaiting_approval"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COUNTER_OFFER = "counter_offer"


class ProductRequest(BaseModel):
    """A product the user wants to purchase."""

    id: str = Field(default_factory=generate_id)
    name: str
    description: Optional[str] = None
    target_price: Optional[float] = None
    max_price: Optional[float] = None
    quantity: int = 1
    country: str = "IL"
    priority: int = 1
    created_at: datetime = Field(default_factory=datetime.now)


class SellerInfo(BaseModel):
    """Information about a seller."""

    id: str = Field(default_factory=generate_id)
    name: str
    website: Optional[str] = None
    whatsapp_number: Optional[str] = None
    country: str
    source: str = "scraped"  # "scraped" or "manual"
    reliability_score: Optional[float] = None


class PriceOption(BaseModel):
    """A price option for a product from a seller."""

    id: str = Field(default_factory=generate_id)
    product_id: str
    seller: SellerInfo
    listed_price: float
    currency: str = "ILS"
    url: str
    scraped_at: datetime = Field(default_factory=datetime.now)


class SellerAggregation(BaseModel):
    """Aggregated data for a seller across multiple products."""

    seller_name: str  # Original seller name (display)
    normalized_name: str  # Normalized for matching
    products: list[PriceOption]  # All products from this seller
    product_queries: list[str]  # Which queries matched
    total_price: float  # Sum of all product prices
    average_rating: Optional[float] = None  # Average seller rating
    contact: Optional[str] = None  # WhatsApp/phone if available
    sources: list[str] = Field(default_factory=list)  # Which scrapers found them

    @property
    def product_count(self) -> int:
        """Number of products available from this seller."""
        return len(self.products)


class Message(BaseModel):
    """A message in a conversation."""

    role: str  # "agent" or "seller"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class NegotiationState(BaseModel):
    """State of a negotiation with a seller."""

    id: str = Field(default_factory=generate_id)
    product: ProductRequest
    seller: SellerInfo
    price_option: PriceOption
    status: NegotiationStatus = NegotiationStatus.PENDING
    conversation_history: list[Message] = Field(default_factory=list)
    current_offer: Optional[float] = None
    best_offer: Optional[float] = None
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    approval_request_id: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    """A request for human approval."""

    id: str = Field(default_factory=generate_id)
    negotiation_id: str
    product_name: str
    seller_name: str
    original_price: float
    offered_price: float
    discount_percentage: float
    market_average: Optional[float] = None
    conversation_summary: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    human_response: Optional[str] = None
    counter_offer_amount: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None


class PurchaseSession(BaseModel):
    """A session of purchasing multiple products."""

    id: str = Field(default_factory=generate_id)
    products: list[ProductRequest] = Field(default_factory=list)
    negotiations: list[NegotiationState] = Field(default_factory=list)
    status: str = "active"
    total_potential_savings: float = 0
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
