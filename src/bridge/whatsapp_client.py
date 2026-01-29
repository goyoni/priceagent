"""Python client for the WhatsApp Node.js bridge."""

import asyncio
import json
from typing import Callable, Optional, Any
from datetime import datetime

import httpx
import websockets
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


class WhatsAppMessage(BaseModel):
    """Incoming WhatsApp message."""

    from_number: str
    body: str
    timestamp: int
    chat_id: str
    has_media: bool = False
    is_forwarded: bool = False

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp)


class ChatMessage(BaseModel):
    """A message from chat history."""

    id: str
    body: str
    from_me: bool
    timestamp: int
    has_media: bool = False


class WhatsAppBridgeClient:
    """Async client for the WhatsApp bridge service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        ws_url: str = "ws://localhost:8081",
    ):
        self.base_url = base_url
        self.ws_url = ws_url
        self._message_handlers: list[Callable[[WhatsAppMessage], Any]] = []
        self._status_handlers: list[Callable[[dict], Any]] = []
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False

    async def check_health(self) -> dict:
        """Check if the bridge is healthy."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/health")
            return response.json()

    async def get_status(self) -> dict:
        """Get WhatsApp connection status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/status")
            return response.json()

    async def is_ready(self) -> bool:
        """Check if WhatsApp client is ready."""
        try:
            status = await self.get_status()
            return status.get("ready", False)
        except Exception:
            return False

    async def send_message(self, phone_number: str, message: str) -> dict:
        """Send a WhatsApp message.

        Args:
            phone_number: Phone number (with country code, no + or spaces)
            message: Message text to send

        Returns:
            Response dict with success status and chat_id
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/messages/send",
                json={"phoneNumber": phone_number, "message": message},
            )
            result = response.json()

            if result.get("success"):
                logger.info("Message sent", phone=phone_number, chat_id=result.get("chatId"))
            else:
                logger.error("Failed to send message", phone=phone_number, error=result.get("error"))

            return result

    async def verify_number(self, phone_number: str) -> bool:
        """Check if a phone number is registered on WhatsApp.

        Args:
            phone_number: Phone number to verify

        Returns:
            True if the number is on WhatsApp
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/contacts/verify/{phone_number}")
            result = response.json()
            return result.get("exists", False)

    async def get_chat_history(self, chat_id: str, limit: int = 50) -> list[ChatMessage]:
        """Retrieve chat history with a contact.

        Args:
            chat_id: Chat ID or phone number
            limit: Maximum number of messages to retrieve

        Returns:
            List of messages from the chat
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/chats/{chat_id}/messages",
                params={"limit": limit},
            )
            result = response.json()

            return [
                ChatMessage(
                    id=m["id"],
                    body=m["body"],
                    from_me=m["fromMe"],
                    timestamp=m["timestamp"],
                    has_media=m.get("hasMedia", False),
                )
                for m in result.get("messages", [])
            ]

    async def get_chats(self) -> list[dict]:
        """Get list of all chats."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/chats")
            result = response.json()
            return result.get("chats", [])

    def on_message(self, handler: Callable[[WhatsAppMessage], Any]) -> None:
        """Register a handler for incoming messages.

        Args:
            handler: Async function that receives WhatsAppMessage
        """
        self._message_handlers.append(handler)

    def on_status(self, handler: Callable[[dict], Any]) -> None:
        """Register a handler for status updates.

        Args:
            handler: Async function that receives status dict
        """
        self._status_handlers.append(handler)

    async def start_listening(self) -> None:
        """Start listening for incoming messages via WebSocket."""
        if self._running:
            return

        self._running = True
        self._ws_task = asyncio.create_task(self._ws_listener())
        logger.info("Started WebSocket listener")

    async def stop_listening(self) -> None:
        """Stop listening for incoming messages."""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped WebSocket listener")

    async def _ws_listener(self) -> None:
        """Internal WebSocket listener loop."""
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("Connected to WebSocket")

                    async for raw_message in ws:
                        if not self._running:
                            break

                        try:
                            data = json.loads(raw_message)
                            await self._handle_ws_message(data)
                        except json.JSONDecodeError:
                            logger.error("Failed to parse WebSocket message")

            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error("WebSocket error", error=str(e))
                await asyncio.sleep(5)

    async def _handle_ws_message(self, data: dict) -> None:
        """Handle a message from WebSocket."""
        msg_type = data.get("type")

        if msg_type == "incoming_message":
            message = WhatsAppMessage(
                from_number=data["from"],
                body=data["body"],
                timestamp=data["timestamp"],
                chat_id=data["chatId"],
                has_media=data.get("hasMedia", False),
                is_forwarded=data.get("isForwarded", False),
            )
            logger.info("Received message", from_number=message.from_number)

            for handler in self._message_handlers:
                try:
                    result = handler(message)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("Message handler error", error=str(e))

        else:
            # Status updates (qr, ready, disconnected, etc.)
            for handler in self._status_handlers:
                try:
                    result = handler(data)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("Status handler error", error=str(e))


# Convenience function for creating a client
def create_whatsapp_client(
    base_url: str = "http://localhost:8080",
    ws_url: str = "ws://localhost:8081",
) -> WhatsAppBridgeClient:
    """Create a WhatsApp bridge client.

    Args:
        base_url: REST API URL of the bridge
        ws_url: WebSocket URL for incoming messages

    Returns:
        Configured WhatsAppBridgeClient
    """
    return WhatsAppBridgeClient(base_url=base_url, ws_url=ws_url)
