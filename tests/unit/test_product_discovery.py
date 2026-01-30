"""Tests for product discovery agent and models."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent import router as agent_router
from src.state.models import (
    DiscoveredProduct,
    ShoppingListItem,
    PriceSearchSession,
    PriceSearchStatus,
)
from src.agents.product_discovery import extract_brand, extract_model_number


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(agent_router)
    return app


class TestDiscoveredProductModel:
    """Tests for DiscoveredProduct model."""

    def test_create_discovered_product(self):
        """Should create a discovered product with all fields."""
        product = DiscoveredProduct(
            name="Samsung Family Hub Refrigerator",
            brand="Samsung",
            model_number="RF72DG9620B1",
            category="refrigerator",
            key_specs=["34 dB noise level", "620L capacity", "A++ energy"],
            price_range="8,000-12,000 ILS",
            why_recommended="Silent operation ideal for open kitchen layouts",
        )

        assert product.name == "Samsung Family Hub Refrigerator"
        assert product.brand == "Samsung"
        assert product.model_number == "RF72DG9620B1"
        assert product.category == "refrigerator"
        assert len(product.key_specs) == 3
        assert product.price_range == "8,000-12,000 ILS"
        assert "Silent" in product.why_recommended

    def test_discovered_product_auto_id(self):
        """Should generate unique ID automatically."""
        product1 = DiscoveredProduct(
            name="Product 1",
            category="test",
            why_recommended="Test",
        )
        product2 = DiscoveredProduct(
            name="Product 2",
            category="test",
            why_recommended="Test",
        )

        assert product1.id != product2.id
        assert len(product1.id) == 8


class TestShoppingListItemModel:
    """Tests for ShoppingListItem model."""

    def test_create_shopping_list_item(self):
        """Should create a shopping list item."""
        item = ShoppingListItem(
            product_name="Samsung RF72DG9620B1",
            model_number="RF72DG9620B1",
            specs_summary="620L, 34dB, A++",
            source="discovery",
        )

        assert item.product_name == "Samsung RF72DG9620B1"
        assert item.model_number == "RF72DG9620B1"
        assert item.source == "discovery"
        assert item.added_at is not None

    def test_shopping_list_item_default_source(self):
        """Should default to manual source."""
        item = ShoppingListItem(product_name="Test Product")

        assert item.source == "manual"


class TestPriceSearchSessionModel:
    """Tests for PriceSearchSession model."""

    def test_create_price_search_session(self):
        """Should create a price search session."""
        items = [
            ShoppingListItem(product_name="Product 1"),
            ShoppingListItem(product_name="Product 2"),
        ]
        session = PriceSearchSession(
            list_snapshot=items,
            country="IL",
        )

        assert len(session.list_snapshot) == 2
        assert session.status == PriceSearchStatus.PENDING
        assert session.country == "IL"
        assert session.trace_id is None

    def test_price_search_status_transitions(self):
        """Should allow status transitions."""
        session = PriceSearchSession(list_snapshot=[])

        assert session.status == PriceSearchStatus.PENDING

        session.status = PriceSearchStatus.RUNNING
        assert session.status == PriceSearchStatus.RUNNING

        session.status = PriceSearchStatus.COMPLETED
        assert session.status == PriceSearchStatus.COMPLETED


class TestExtractBrand:
    """Tests for extract_brand utility function."""

    def test_extract_samsung(self):
        """Should extract Samsung brand."""
        assert extract_brand("Samsung Galaxy S24") == "Samsung"
        assert extract_brand("SAMSUNG RF72DG9620B1") == "Samsung"

    def test_extract_lg(self):
        """Should extract LG brand."""
        assert extract_brand("LG OLED TV 55 inch") == "LG"

    def test_extract_apple(self):
        """Should extract Apple brand."""
        assert extract_brand("Apple iPhone 15 Pro") == "Apple"

    def test_no_brand_found(self):
        """Should return None for unknown brand."""
        assert extract_brand("Generic Product XYZ") is None


class TestExtractModelNumber:
    """Tests for extract_model_number utility function."""

    def test_extract_samsung_fridge_model(self):
        """Should extract Samsung refrigerator model number."""
        result = extract_model_number("Samsung RF72DG9620B1 Refrigerator")
        assert result == "RF72DG9620B1"

    def test_extract_sony_headphones_model(self):
        """Should extract Sony headphones model number."""
        result = extract_model_number("Sony WH-1000XM5 Headphones")
        # WH-1000XM5 should match
        assert result is not None
        assert "1000" in result

    def test_no_model_found(self):
        """Should return None when no model number pattern found."""
        result = extract_model_number("Generic Product")
        assert result is None


class TestDiscoveryAgentRoute:
    """Tests for POST /agent/run with discovery agent."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        app = create_test_app()
        return TestClient(app)

    def test_discovery_agent_starts(self, client):
        """Should start discovery agent and return trace_id."""
        request_data = {
            "query": "silent fridge for family of 4",
            "agent": "discovery",
        }

        response = client.post("/agent/run", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "trace_id" in data
        assert data["status"] == "started"

    def test_research_agent_still_works(self, client):
        """Should still support research agent."""
        request_data = {
            "query": "iPhone 15 Pro",
            "agent": "research",
        }

        response = client.post("/agent/run", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "trace_id" in data
