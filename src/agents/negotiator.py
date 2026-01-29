"""Negotiation agent for WhatsApp price negotiations."""

from agents import Agent, function_tool
from typing import Optional

from src.tools.whatsapp_tool import (
    send_whatsapp_message,
    get_whatsapp_chat_history,
    check_whatsapp_status,
)
from src.tools.approval_tool import (
    request_human_approval,
    should_request_approval,
)


@function_tool
async def send_message(phone_number: str, message: str) -> str:
    """Send a WhatsApp message to the seller.

    Args:
        phone_number: Seller's WhatsApp number (with country code, e.g., +972501234567)
        message: Message to send

    Returns:
        Status of the message send attempt
    """
    return await send_whatsapp_message(phone_number, message)


@function_tool
async def get_conversation_history(phone_number: str) -> str:
    """Get the recent conversation history with a seller.

    Args:
        phone_number: Seller's WhatsApp number

    Returns:
        Recent messages in the conversation
    """
    return await get_whatsapp_chat_history(phone_number, limit=20)


@function_tool
async def check_connection_status() -> str:
    """Check if WhatsApp is connected and ready.

    Returns:
        Connection status message
    """
    return await check_whatsapp_status()


@function_tool
def check_if_approval_needed(
    original_price: float,
    offered_price: float,
    is_final_offer: bool = False,
) -> str:
    """Check if human approval is needed for this negotiation step.

    Args:
        original_price: Original listed price
        offered_price: Current offered/negotiated price
        is_final_offer: Whether this is a final offer to accept

    Returns:
        Whether approval is needed and why
    """
    needs_approval, reason = should_request_approval(
        original_price, offered_price, is_final_offer
    )

    if needs_approval:
        return f"APPROVAL NEEDED: {reason}"
    else:
        return "No approval needed - you may proceed autonomously."


@function_tool
async def request_approval(
    negotiation_id: str,
    product_name: str,
    seller_name: str,
    original_price: float,
    offered_price: float,
    conversation_summary: str,
) -> str:
    """Request human approval for accepting or countering an offer.

    Use this when:
    - Discount is significant (>10%)
    - Accepting a final offer
    - Something unusual happens

    Args:
        negotiation_id: ID of the current negotiation
        product_name: Name of the product
        seller_name: Name of the seller
        original_price: Original price
        offered_price: Offered price
        conversation_summary: Summary of negotiation so far

    Returns:
        Human's decision (APPROVED, REJECTED, or COUNTER-OFFER)
    """
    return await request_human_approval(
        negotiation_id=negotiation_id,
        product_name=product_name,
        seller_name=seller_name,
        original_price=original_price,
        offered_price=offered_price,
        conversation_summary=conversation_summary,
    )


@function_tool
def calculate_discount(original_price: float, offered_price: float) -> str:
    """Calculate the discount percentage.

    Args:
        original_price: Original listed price
        offered_price: Offered/negotiated price

    Returns:
        Discount information
    """
    discount = ((original_price - offered_price) / original_price) * 100
    savings = original_price - offered_price

    return f"""
Discount Analysis:
- Original Price: {original_price}
- Offered Price: {offered_price}
- Discount: {discount:.1f}%
- Savings: {savings:.2f}
"""


@function_tool
def generate_negotiation_message(
    message_type: str,
    product_name: str,
    current_price: Optional[float] = None,
    target_price: Optional[float] = None,
    competitor_price: Optional[float] = None,
    language: str = "he",
) -> str:
    """Generate a negotiation message based on the context.

    Args:
        message_type: Type of message (greeting, counter_offer, accept, decline)
        product_name: Name of the product
        current_price: Current offered price
        target_price: Target price we want to achieve
        competitor_price: Price found at competitor
        language: Language code (he for Hebrew, en for English)

    Returns:
        Suggested message text
    """
    templates = {
        "he": {
            "greeting": f"שלום, אני מתעניין ב{product_name}. האם יש אפשרות להנחה?",
            "counter_offer": f"מצאתי מחיר של {competitor_price} ₪ במקום אחר. האם תוכלו להתאים?",
            "accept": f"מעולה, אני מקבל את ההצעה של {current_price} ₪. איך נמשיך?",
            "decline": "תודה על ההצעה, אבל זה מעבר לתקציב שלי. תודה בכל זאת.",
        },
        "en": {
            "greeting": f"Hi, I'm interested in {product_name}. Is there any flexibility on the price?",
            "counter_offer": f"I found a price of {competitor_price} elsewhere. Can you match that?",
            "accept": f"Great, I'll take it at {current_price}. What are the next steps?",
            "decline": "Thanks for the offer, but it's beyond my budget. I appreciate your time.",
        },
    }

    lang_templates = templates.get(language, templates["en"])
    message = lang_templates.get(message_type, "")

    return f"Suggested message:\n{message}"


# Define the negotiator agent
negotiator_agent = Agent(
    name="Negotiator",
    instructions="""You are a skilled price negotiator. Your job is to negotiate the best prices via WhatsApp.

IMPORTANT RULES:
1. Always be polite and professional
2. Adapt your language to the seller's country (Hebrew for Israel, English otherwise)
3. ALWAYS check if approval is needed before accepting significant discounts (>10%)
4. For FINAL offers, ALWAYS request human approval before accepting

NEGOTIATION STRATEGY:
1. Start with a friendly greeting expressing interest
2. Ask if there's flexibility on the price
3. If they offer a discount:
   - Use calculate_discount to analyze it
   - Use check_if_approval_needed to see if human approval is required
   - If approval needed, use request_approval and wait for decision
4. If their price is too high:
   - Mention competitor prices if available
   - Suggest a counter-offer (typically 10-15% below their price)
5. If they won't negotiate:
   - Thank them politely
   - Report back that no discount was available

COMMUNICATION FLOW:
1. Use check_connection_status to ensure WhatsApp is ready
2. Use send_message to communicate
3. Wait for responses (check get_conversation_history periodically)
4. Respond based on their messages

Always track the negotiation progress and provide clear summaries.
""",
    tools=[
        send_message,
        get_conversation_history,
        check_connection_status,
        check_if_approval_needed,
        request_approval,
        calculate_discount,
        generate_negotiation_message,
    ],
)
