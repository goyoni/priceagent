"""API routes for running agent queries."""

import asyncio
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter
from pydantic import BaseModel

from agents import Runner
from src.agents.product_research import product_research_agent
from src.agents.product_discovery import product_discovery_agent
from src.agents.orchestrator import orchestrator_agent
from src.observability import ObservabilityHooks, get_trace_store

router = APIRouter(prefix="/agent", tags=["agent"])


class ConversationMessage(BaseModel):
    """A message in the conversation history."""
    role: str
    content: str


class QueryRequest(BaseModel):
    """Request to run an agent query."""
    query: str
    agent: str = "research"  # research, orchestrator, negotiate, discovery
    country: str = "IL"  # Country code for localization
    conversation_history: list[ConversationMessage] = []  # Previous conversation for refinements
    session_id: Optional[str] = None  # Session ID for tracking conversation
    parent_trace_id: Optional[str] = None  # Links to parent trace in conversation flow


class QueryResponse(BaseModel):
    """Response from agent query."""
    trace_id: str
    status: str = "started"


@router.post("/run")
async def run_agent_query(request: QueryRequest) -> QueryResponse:
    """Run an agent query in the background.

    The agent runs asynchronously and results can be viewed in the dashboard.
    """
    store = get_trace_store()
    hooks = ObservabilityHooks(store)

    # Determine the prompt based on request
    if request.agent == "negotiate" or request.query.lower().startswith("negotiate "):
        agent = orchestrator_agent
        prompt = f"Negotiate the best price for: {request.query.replace('negotiate ', '')}"
    elif request.agent == "orchestrator":
        agent = orchestrator_agent
        prompt = request.query
    elif request.agent == "discovery":
        agent = product_discovery_agent
        # Build prompt with conversation history for refinements
        if request.conversation_history:
            history_text = "\n".join([
                f"{msg.role.capitalize()}: {msg.content}"
                for msg in request.conversation_history[:-1]  # Exclude current message
            ])
            prompt = f"""Previous conversation:
{history_text}

User's refinement request: {request.query}
User country: {request.country}

Based on the conversation history, refine the product recommendations accordingly."""
        else:
            prompt = f"Find products matching: {request.query}\nUser country: {request.country}"
    else:
        agent = product_research_agent
        prompt = f"Search for: {request.query}"

    # Start trace with session ID and parent trace ID if provided
    trace = await hooks.start_trace(
        input_prompt=prompt,
        session_id=request.session_id,
        parent_trace_id=request.parent_trace_id
    )
    trace_id = trace.id if trace else ""

    # Run agent in background using asyncio.create_task
    # This schedules the coroutine on the current event loop
    async def run_agent():
        try:
            result = await Runner.run(agent, prompt, hooks=hooks)
            await hooks.end_trace(final_output=result.final_output)
        except Exception as e:
            await hooks.end_trace(error=str(e))

    # Create task directly on the running event loop
    asyncio.create_task(run_agent())

    return QueryResponse(trace_id=trace_id, status="started")


class SellerDraftRequest(BaseModel):
    """Single seller for draft generation."""

    seller_name: str
    phone_number: str
    products: list[str] = []  # List of product names/model numbers
    product_name: str = ""  # Legacy single product (for backwards compatibility)
    listed_price: float = 0
    currency: str = "ILS"
    competitor_price: Optional[float] = None


class GenerateDraftsRequest(BaseModel):
    """Request to generate negotiation drafts."""

    sellers: list[SellerDraftRequest]
    language: str = "he"  # Language override (he/en)
    country: str = "IL"  # Country for auto-detecting language


class DraftMessage(BaseModel):
    """Generated draft message for a seller."""

    seller_name: str
    phone_number: str
    product_name: str  # Legacy field for display
    products: list[str] = []  # List of products in this message
    message: str
    wa_link: str


class GenerateDraftsResponse(BaseModel):
    """Response with generated draft messages."""

    drafts: list[DraftMessage]


# Country to language mapping
COUNTRY_LANGUAGES = {
    "IL": "he",  # Israel -> Hebrew
    "US": "en",
    "UK": "en",
    "GB": "en",
}


def generate_message(products: list[str], language: str) -> str:
    """Generate a polite negotiation message in the specified language.

    Args:
        products: List of product names/model numbers
        language: Language code (he/en)

    Returns:
        Formatted message string
    """
    if language == "he":
        if len(products) == 1:
            return f"""שלום,
ראיתי את המוצר הבא באתר שלכם ורציתי לשאול האם יש אפשרות להנחה:

• {products[0]}

תודה רבה!"""
        else:
            products_list = "\n".join(f"• {p}" for p in products)
            return f"""שלום,
ראיתי את המוצרים הבאים באתר שלכם ורציתי לשאול האם יש אפשרות להנחה במידה ואקנה אצלכם במרוכז:

{products_list}

תודה רבה!"""
    else:
        if len(products) == 1:
            return f"""Hi,
I saw the following item on your website and was wondering if there's a discount available:

• {products[0]}

Thank you!"""
        else:
            products_list = "\n".join(f"• {p}" for p in products)
            return f"""Hi,
I saw the following items on your website and was wondering if there's a discount for purchasing all of them together:

{products_list}

Thank you!"""


def normalize_products(products: list[str]) -> list[str]:
    """Normalize products list - split comma-separated strings into individual products.

    Args:
        products: List that may contain comma-separated product strings

    Returns:
        Flattened list with individual product names
    """
    result = []
    for p in products:
        # If a product contains commas, it might be a comma-separated list
        if "," in p:
            # Split and strip whitespace
            parts = [part.strip() for part in p.split(",") if part.strip()]
            result.extend(parts)
        else:
            result.append(p.strip())
    return result


@router.post("/generate-drafts")
async def generate_negotiation_drafts(
    request: GenerateDraftsRequest,
) -> GenerateDraftsResponse:
    """Generate editable negotiation message drafts for sellers."""
    # Determine language: explicit language takes precedence, then country-based, then default
    if request.language and request.language != "he":
        # Explicit language override (except default 'he' which means "use country")
        language = request.language
    elif request.country and request.country in COUNTRY_LANGUAGES:
        # Country-based language detection
        language = COUNTRY_LANGUAGES[request.country]
    else:
        # Default to Hebrew
        language = "he"

    drafts = []
    for seller in request.sellers:
        # Get products list - use products array if provided, else fall back to product_name
        products = seller.products if seller.products else (
            [seller.product_name] if seller.product_name else []
        )

        if not products:
            continue

        # Normalize products - split comma-separated strings into individual products
        products = normalize_products(products)

        # Generate polite message with product list
        message = generate_message(products, language)

        # Generate wa.me link with pre-filled message
        phone_clean = seller.phone_number.replace("+", "").replace(" ", "").replace("-", "")
        wa_link = f"https://wa.me/{phone_clean}?text={quote(message)}"

        drafts.append(
            DraftMessage(
                seller_name=seller.seller_name,
                phone_number=seller.phone_number,
                product_name=products[0] if products else "",  # Legacy field
                products=products,
                message=message,
                wa_link=wa_link,
            )
        )

    return GenerateDraftsResponse(drafts=drafts)
