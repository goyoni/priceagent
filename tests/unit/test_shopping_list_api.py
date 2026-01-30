"""Tests for shopping list API routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.shopping_list import router as shopping_list_router
from src.api.routes.geo import router as geo_router


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(shopping_list_router)
    app.include_router(geo_router)
    return app


class TestGeoRoutes:
    """Tests for geo API routes."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        app = create_test_app()
        return TestClient(app)

    def test_get_country_default(self, client):
        """Should return default country for local IP."""
        response = client.get("/api/geo/country")

        assert response.status_code == 200
        data = response.json()
        assert data["country"] == "IL"
        assert data["source"] in ("default", "header", "cloudflare")

    def test_get_country_with_header(self, client):
        """Should use X-Country header when provided."""
        response = client.get(
            "/api/geo/country",
            headers={"X-Country": "US"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["country"] == "US"
        assert data["source"] == "header"

    def test_get_country_cloudflare(self, client):
        """Should use CF-IPCountry header when provided."""
        response = client.get(
            "/api/geo/country",
            headers={"CF-IPCountry": "DE"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["country"] == "DE"
        assert data["source"] == "cloudflare"


class TestShoppingListRoutes:
    """Tests for shopping list API routes."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        app = create_test_app()
        return TestClient(app)

    def test_start_search_returns_session(self, client):
        """Should start a search and return session info."""
        request_data = {
            "items": [
                {"product_name": "Samsung Refrigerator", "model_number": "RF72DG9620B1"},
            ],
            "country": "IL",
        }

        response = client.post("/api/shopping-list/search-prices", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "trace_id" in data
        assert data["status"] == "started"

    def test_start_search_empty_list(self, client):
        """Should return error for empty item list."""
        request_data = {
            "items": [],
            "country": "IL",
        }

        response = client.post("/api/shopping-list/search-prices", json=request_data)

        assert response.status_code == 400
        assert "No items to search" in response.json()["detail"]

    def test_start_search_multiple_items(self, client):
        """Should handle multiple items."""
        request_data = {
            "items": [
                {"product_name": "Product 1"},
                {"product_name": "Product 2", "model_number": "MODEL123"},
                {"product_name": "Product 3"},
            ],
            "country": "IL",
        }

        response = client.post("/api/shopping-list/search-prices", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "started"

    def test_get_status_not_found(self, client):
        """Should return 404 for unknown session."""
        response = client.get("/api/shopping-list/search-status/unknown-session-id")

        assert response.status_code == 404

    def test_list_sessions(self, client):
        """Should list all sessions."""
        response = client.get("/api/shopping-list/sessions")

        assert response.status_code == 200
        assert isinstance(response.json(), list)
