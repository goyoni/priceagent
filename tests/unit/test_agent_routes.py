"""Tests for agent API routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent import router as agent_router


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(agent_router)
    return app


class TestGenerateDrafts:
    """Tests for POST /agent/generate-drafts endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        app = create_test_app()
        return TestClient(app)

    def test_generate_drafts_returns_drafts(self, client):
        """Should generate draft messages for sellers."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "product_name": "iPhone 15",
                    "listed_price": 4500,
                }
            ],
            "language": "he",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "drafts" in data
        assert len(data["drafts"]) == 1

        draft = data["drafts"][0]
        assert draft["seller_name"] == "Test Store"
        assert draft["phone_number"] == "+972501234567"
        assert draft["product_name"] == "iPhone 15"
        assert "message" in draft
        assert "wa_link" in draft

    def test_generate_drafts_hebrew_message(self, client):
        """Should generate Hebrew message when language is 'he'."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "product_name": "iPhone 15",
                    "listed_price": 4500,
                }
            ],
            "language": "he",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        # Should contain Hebrew greeting
        assert "שלום" in draft["message"]
        assert "iPhone 15" in draft["message"]

    def test_generate_drafts_english_message(self, client):
        """Should generate English message when language is 'en'."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "product_name": "iPhone 15",
                    "listed_price": 4500,
                }
            ],
            "language": "en",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        # Should contain English greeting
        assert "Hi" in draft["message"] or "interested" in draft["message"]

    def test_generate_drafts_wa_link_format(self, client):
        """Should generate valid WhatsApp link with encoded message."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972-50-123-4567",
                    "product_name": "iPhone 15",
                    "listed_price": 4500,
                }
            ],
            "language": "he",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        # Link should have phone number without special characters
        assert "wa.me/972501234567" in draft["wa_link"]
        # Link should have text parameter
        assert "?text=" in draft["wa_link"]

    def test_generate_drafts_multiple_sellers(self, client):
        """Should generate drafts for multiple sellers."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Store A",
                    "phone_number": "+972501111111",
                    "product_name": "iPhone 15",
                    "listed_price": 4500,
                },
                {
                    "seller_name": "Store B",
                    "phone_number": "+972502222222",
                    "product_name": "iPhone 15",
                    "listed_price": 4300,
                },
            ],
            "language": "he",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert len(data["drafts"]) == 2
        assert data["drafts"][0]["seller_name"] == "Store A"
        assert data["drafts"][1]["seller_name"] == "Store B"

    def test_generate_drafts_empty_sellers_list(self, client):
        """Should return empty drafts for empty sellers list."""
        request_data = {
            "sellers": [],
            "language": "he",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["drafts"] == []

    def test_generate_drafts_default_language(self, client):
        """Should default to Hebrew when language not specified."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "product_name": "iPhone 15",
                    "listed_price": 4500,
                }
            ],
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        # Should contain Hebrew greeting (default)
        assert "שלום" in draft["message"]
