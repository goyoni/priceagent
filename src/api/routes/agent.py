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

    return QueryResponse(trace_id=trace.id, status="started")


class SellerDraftRequest(BaseModel):
    """Single seller for draft generation."""

    seller_name: str
    phone_number: str
    product_name: str
    listed_price: float
    currency: str = "ILS"
    competitor_price: Optional[float] = None


class GenerateDraftsRequest(BaseModel):
    """Request to generate negotiation drafts."""

    sellers: list[SellerDraftRequest]
    language: str = "he"


class DraftMessage(BaseModel):
    """Generated draft message for a seller."""

    seller_name: str
    phone_number: str
    product_name: str
    message: str
    wa_link: str


class GenerateDraftsResponse(BaseModel):
    """Response with generated draft messages."""

    drafts: list[DraftMessage]


@router.post("/generate-drafts")
async def generate_negotiation_drafts(
    request: GenerateDraftsRequest,
) -> GenerateDraftsResponse:
    """Generate editable negotiation message drafts for sellers."""
    drafts = []
    for seller in request.sellers:
        # Generate message based on language
        if request.language == "he":
            message = f"שלום, אני מתעניין ב{seller.product_name}. האם יש אפשרות להנחה?"
        else:
            message = f"Hi, I'm interested in {seller.product_name}. Is there any flexibility on the price?"

        # Generate wa.me link with pre-filled message
        phone_clean = seller.phone_number.replace("+", "").replace(" ", "").replace("-", "")
        wa_link = f"https://wa.me/{phone_clean}?text={quote(message)}"

        drafts.append(
            DraftMessage(
                seller_name=seller.seller_name,
                phone_number=seller.phone_number,
                product_name=seller.product_name,
                message=message,
                wa_link=wa_link,
            )
        )

    return GenerateDraftsResponse(drafts=drafts)
