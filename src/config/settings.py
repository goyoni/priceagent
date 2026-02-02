"""Configuration settings for the ecommerce negotiator."""

from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key (required for agent functionality)",
    )

    # SerpAPI for Google Search/Shopping
    serpapi_key: Optional[str] = Field(
        default=None,
        description="SerpAPI key for Google Shopping and Search integration",
    )

    # WhatsApp Bridge
    whatsapp_bridge_url: str = Field(
        default="http://localhost:8080",
        description="URL of the WhatsApp bridge service",
    )
    whatsapp_bridge_ws_url: str = Field(
        default="ws://localhost:8081",
        description="WebSocket URL for incoming messages",
    )

    # Database
    database_path: Path = Field(
        default=Path("data/negotiations.db"),
        description="Path to SQLite database",
    )

    # Approval settings
    min_discount_for_approval: float = Field(
        default=10.0,
        description="Minimum discount percentage that requires human approval",
    )
    max_auto_approve_amount: float = Field(
        default=100.0,
        description="Maximum amount (USD) that can be auto-approved",
    )
    approval_timeout_seconds: int = Field(
        default=3600,
        description="Timeout for human approval in seconds",
    )

    # API
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")

    # Dashboard authentication
    dashboard_password: Optional[str] = Field(
        default=None,
        description="Password to access dashboard (None = no auth in dev)",
    )
    environment: str = Field(
        default="development",
        description="Environment: 'development' or 'production'",
    )

    # Cache settings
    cache_enabled: bool = Field(default=True, description="Enable caching")
    cache_path: Path = Field(
        default=Path("data/cache.db"), description="SQLite cache path"
    )
    cache_ttl_scraper_hours: int = Field(
        default=24, description="TTL for scraper results in hours"
    )
    cache_ttl_contact_days: int = Field(
        default=7, description="TTL for contact info in days"
    )
    cache_ttl_http_hours: int = Field(
        default=1, description="TTL for HTTP responses in hours"
    )
    cache_ttl_agent_hours: int = Field(
        default=24, description="TTL for agent tool results in hours"
    )
    cache_memory_max_items: int = Field(
        default=1000, description="Max items in memory cache"
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
