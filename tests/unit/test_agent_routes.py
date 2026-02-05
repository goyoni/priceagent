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

    def test_generate_drafts_country_based_language(self, client):
        """Should use Hebrew for IL country."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "product_name": "iPhone 15",
                }
            ],
            "country": "IL",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        assert "שלום" in draft["message"]
        assert "תודה רבה" in draft["message"]

    def test_generate_drafts_country_us_english(self, client):
        """Should use English for US country."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+1555123456",
                    "product_name": "iPhone 15",
                }
            ],
            "country": "US",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        assert "Hi" in draft["message"]
        assert "Thank you" in draft["message"]

    def test_generate_drafts_multiple_products(self, client):
        """Should list multiple products in the message."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "products": ["Samsung Fridge", "Samsung Washer", "Samsung Dryer"],
                }
            ],
            "country": "IL",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        # Should mention all products
        assert "Samsung Fridge" in draft["message"]
        assert "Samsung Washer" in draft["message"]
        assert "Samsung Dryer" in draft["message"]
        # Should mention bundle discount
        assert "במרוכז" in draft["message"]  # "in bulk"
        # Should return products array
        assert draft["products"] == ["Samsung Fridge", "Samsung Washer", "Samsung Dryer"]

    def test_generate_drafts_single_product_no_bundle_text(self, client):
        """Should not mention bundle discount for single product."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "products": ["iPhone 15"],
                }
            ],
            "country": "IL",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        assert "iPhone 15" in draft["message"]
        # Should NOT mention bundle purchase
        assert "כולם יחד" not in draft["message"]

    def test_generate_drafts_products_array_takes_precedence(self, client):
        """Products array should take precedence over product_name."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    "products": ["Product A", "Product B"],
                    "product_name": "Legacy Product",  # Should be ignored
                }
            ],
            "country": "IL",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        assert "Product A" in draft["message"]
        assert "Product B" in draft["message"]
        assert "Legacy Product" not in draft["message"]

    def test_generate_drafts_comma_separated_products_split(self, client):
        """Comma-separated products string should be split into individual products."""
        request_data = {
            "sellers": [
                {
                    "seller_name": "Test Store",
                    "phone_number": "+972501234567",
                    # Products passed as comma-separated string (common from multi-product search)
                    "products": ["BFL523MB1F, HBG578EB3, PVS631HC1E"],
                }
            ],
            "country": "IL",
        }

        response = client.post("/agent/generate-drafts", json=request_data)

        assert response.status_code == 200
        draft = response.json()["drafts"][0]
        # Should be split into separate bullet points
        assert "• BFL523MB1F" in draft["message"]
        assert "• HBG578EB3" in draft["message"]
        assert "• PVS631HC1E" in draft["message"]
        # Should use plural form (multiple products)
        assert "המוצרים הבאים" in draft["message"]
        # Should mention bulk purchase discount
        assert "במרוכז" in draft["message"]
