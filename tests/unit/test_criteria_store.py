"""Tests for the criteria store."""

import pytest

from src.db.criteria_store import CriteriaStore, get_criteria_store, set_criteria_store


class TestCriteriaStore:
    """Tests for CriteriaStore."""

    @pytest.fixture
    def store(self):
        """Create a test store using the centralized database."""
        # The init_test_database fixture in conftest.py sets up the test database
        store = CriteriaStore()
        # Reset initialized flag to allow re-seeding for each test
        store._initialized = False
        set_criteria_store(store)
        return store

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, store):
        """Should create tables and seed data on first init."""
        await store.initialize()

        # Should have seeded categories
        categories = await store.list_categories()
        assert len(categories) >= 3  # At least oven, refrigerator, washing_machine

        category_names = [c["category"] for c in categories]
        assert "oven" in category_names
        assert "refrigerator" in category_names
        assert "washing_machine" in category_names

    @pytest.mark.asyncio
    async def test_get_criteria_returns_seeded(self, store):
        """Should return seeded criteria for known categories."""
        await store.initialize()

        criteria = await store.get_criteria("oven")
        assert criteria is not None
        assert len(criteria) > 0

        # Check criteria structure
        criterion = criteria[0]
        assert "name" in criterion
        assert "description" in criterion

    @pytest.mark.asyncio
    async def test_get_criteria_returns_none_for_unknown(self, store):
        """Should return None for unknown categories."""
        await store.initialize()

        criteria = await store.get_criteria("spaceship")
        assert criteria is None

    @pytest.mark.asyncio
    async def test_save_criteria_creates_new(self, store):
        """Should save new category criteria."""
        await store.initialize()

        new_criteria = [
            {"name": "horsepower", "unit": "hp", "description": "Engine power"},
            {"name": "fuel_type", "options": ["gasoline", "diesel", "electric"], "description": "Fuel type"},
        ]

        await store.save_criteria("car", new_criteria, source="discovered")

        # Should be retrievable
        criteria = await store.get_criteria("car")
        assert criteria == new_criteria

        # Should appear in list
        categories = await store.list_categories()
        category_names = [c["category"] for c in categories]
        assert "car" in category_names

    @pytest.mark.asyncio
    async def test_save_criteria_updates_existing(self, store):
        """Should update existing category criteria."""
        await store.initialize()

        # Get original
        original = await store.get_criteria("oven")
        assert original is not None

        # Update
        new_criteria = [{"name": "new_criterion", "description": "New"}]
        await store.save_criteria("oven", new_criteria, source="updated")

        # Should return new criteria
        updated = await store.get_criteria("oven")
        assert updated == new_criteria

    @pytest.mark.asyncio
    async def test_delete_category(self, store):
        """Should delete a category."""
        await store.initialize()

        # Verify exists
        criteria = await store.get_criteria("oven")
        assert criteria is not None

        # Delete
        result = await store.delete_category("oven")
        assert result is True

        # Should be gone
        criteria = await store.get_criteria("oven")
        assert criteria is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, store):
        """Should return False when deleting nonexistent category."""
        await store.initialize()

        result = await store.delete_category("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_categories_includes_metadata(self, store):
        """Should include metadata in category list."""
        await store.initialize()

        categories = await store.list_categories()

        # Find oven (seeded)
        oven = next((c for c in categories if c["category"] == "oven"), None)
        assert oven is not None
        assert oven["source"] == "seed"
        assert "created_at" in oven
        assert "updated_at" in oven

    @pytest.mark.asyncio
    async def test_category_names_normalized_to_lowercase(self, store):
        """Should normalize category names to lowercase."""
        await store.initialize()

        criteria = [{"name": "test", "description": "Test"}]
        await store.save_criteria("CAR", criteria)

        # Should be retrievable with any case
        assert await store.get_criteria("car") == criteria
        assert await store.get_criteria("CAR") == criteria
        assert await store.get_criteria("Car") == criteria
