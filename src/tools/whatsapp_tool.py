"""WhatsApp messaging tool for agents."""

from typing import Optional
from src.bridge.whatsapp_client import WhatsAppBridgeClient, create_whatsapp_client


# Global client instance (initialized on first use)
_client: Optional[WhatsAppBridgeClient] = None


def _get_client() -> WhatsAppBridgeClient:
    """Get or create the WhatsApp client."""
    global _client
    if _client is None:
        _client = create_whatsapp_client()
    return _client


async def send_whatsapp_message(phone_number: str, message: str) -> str:
    """Send a WhatsApp message to a phone number.

    Args:
        phone_number: The phone number to send to (with country code, e.g., 972501234567)
        message: The message text to send

    Returns:
        A status message indicating success or failure
    """
    client = _get_client()

    # Check if client is ready
    if not await client.is_ready():
        return "Error: WhatsApp client is not connected. Please scan the QR code first."

    result = await client.send_message(phone_number, message)

    if result.get("success"):
        return f"Message sent successfully to {phone_number}"
    else:
        return f"Failed to send message: {result.get('error', 'Unknown error')}"


async def verify_whatsapp_number(phone_number: str) -> str:
    """Check if a phone number is registered on WhatsApp.

    Args:
        phone_number: The phone number to verify (with country code)

    Returns:
        A message indicating if the number is on WhatsApp
    """
    client = _get_client()

    if not await client.is_ready():
        return "Error: WhatsApp client is not connected."

    exists = await client.verify_number(phone_number)

    if exists:
        return f"The number {phone_number} is registered on WhatsApp."
    else:
        return f"The number {phone_number} is NOT on WhatsApp."


async def get_whatsapp_chat_history(phone_number: str, limit: int = 20) -> str:
    """Get recent chat history with a WhatsApp contact.

    Args:
        phone_number: The phone number to get history for
        limit: Maximum number of messages to retrieve (default 20)

    Returns:
        A formatted string of the chat history
    """
    client = _get_client()

    if not await client.is_ready():
        return "Error: WhatsApp client is not connected."

    messages = await client.get_chat_history(phone_number, limit)

    if not messages:
        return f"No chat history found with {phone_number}"

    history = []
    for msg in messages:
        sender = "You" if msg.from_me else "Seller"
        history.append(f"[{sender}]: {msg.body}")

    return "\n".join(history)


async def check_whatsapp_status() -> str:
    """Check the WhatsApp connection status.

    Returns:
        A message describing the connection status
    """
    client = _get_client()

    try:
        health = await client.check_health()
        if health.get("whatsappReady"):
            return "WhatsApp is connected and ready."
        else:
            return "WhatsApp is not ready. Please scan the QR code in the terminal running the bridge."
    except Exception as e:
        return f"Cannot connect to WhatsApp bridge: {str(e)}"
