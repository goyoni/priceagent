"""Persistent store for product category criteria.

This store learns category-specific criteria over time. When a new product
category is encountered, the agent discovers relevant criteria and saves
them for future use.
"""

import json
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import delete, select

from .base import get_async_session_factory
from .models import CategoryCriteria

logger = structlog.get_logger()

# Default seed criteria for common categories (bootstrap data)
SEED_CRITERIA = {
    "oven": [
        {"name": "volume", "unit": "liters", "description": "Internal oven capacity"},
        {"name": "programs", "unit": "count", "description": "Number of cooking programs/modes"},
        {"name": "cleaning_method", "options": ["pyrolytic", "catalytic", "steam", "manual"], "description": "Self-cleaning method"},
        {"name": "max_temperature", "unit": "°C", "description": "Maximum temperature"},
        {"name": "energy_rating", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
        {"name": "convection", "options": ["yes", "no"], "description": "Hot air circulation"},
    ],
    "refrigerator": [
        {"name": "total_volume", "unit": "liters", "description": "Total storage capacity"},
        {"name": "freezer_volume", "unit": "liters", "description": "Freezer capacity"},
        {"name": "noise_level", "unit": "dB", "description": "Operating noise in decibels"},
        {"name": "energy_rating", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
        {"name": "no_frost", "options": ["yes", "no"], "description": "No-frost technology"},
    ],
    "washing_machine": [
        {"name": "capacity", "unit": "kg", "description": "Load capacity in kg"},
        {"name": "spin_speed", "unit": "rpm", "description": "Maximum spin speed"},
        {"name": "noise_level", "unit": "dB", "description": "Operating noise"},
        {"name": "energy_rating", "options": ["A+++", "A++", "A+", "A", "B"], "description": "Energy efficiency class"},
        {"name": "programs", "unit": "count", "description": "Number of wash programs"},
    ],
}


class CriteriaStore:
    """Persistent store for product category criteria using SQLAlchemy."""

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """Initialize the store and seed with default criteria if empty."""
        if self._initialized:
            return

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            # Check if we have any criteria
            result = await session.execute(select(CategoryCriteria).limit(1))
            existing = result.scalar_one_or_none()

            if existing is None:
                # Seed with default criteria
                now = datetime.utcnow()
                for category, criteria in SEED_CRITERIA.items():
                    model = CategoryCriteria(
                        category=category.lower(),
                        criteria_json=json.dumps(criteria, ensure_ascii=False),
                        source="seed",
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(model)

                await session.commit()
                logger.info("Seeded criteria store", categories=list(SEED_CRITERIA.keys()))

        self._initialized = True

    async def get_criteria(self, category: str) -> Optional[list[dict]]:
        """Get criteria for a category. Returns None if not found."""
        await self.initialize()

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(CategoryCriteria).where(CategoryCriteria.category == category.lower())
            )
            model = result.scalar_one_or_none()

            if model:
                return json.loads(model.criteria_json)
            return None

    async def save_criteria(self, category: str, criteria: list[dict], source: str = "discovered"):
        """Save criteria for a category."""
        await self.initialize()

        criteria_json = json.dumps(criteria, ensure_ascii=False)
        now = datetime.utcnow()

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            # Check if exists
            result = await session.execute(
                select(CategoryCriteria).where(CategoryCriteria.category == category.lower())
            )
            model = result.scalar_one_or_none()

            if model:
                model.criteria_json = criteria_json
                model.source = source
                model.updated_at = now
            else:
                model = CategoryCriteria(
                    category=category.lower(),
                    criteria_json=criteria_json,
                    source=source,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)

            await session.commit()

        logger.info("Saved category criteria",
                   category=category,
                   criteria_count=len(criteria),
                   source=source)

    async def list_categories(self) -> list[dict]:
        """List all known categories with metadata."""
        await self.initialize()

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(CategoryCriteria).order_by(CategoryCriteria.category)
            )
            models = result.scalars().all()

            return [
                {
                    "category": model.category,
                    "source": model.source,
                    "criteria_count": len(json.loads(model.criteria_json)),
                    "created_at": model.created_at.isoformat() if model.created_at else None,
                    "updated_at": model.updated_at.isoformat() if model.updated_at else None,
                }
                for model in models
            ]

    async def delete_category(self, category: str) -> bool:
        """Delete a category. Returns True if deleted."""
        await self.initialize()

        session_factory = get_async_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                delete(CategoryCriteria).where(CategoryCriteria.category == category.lower())
            )
            await session.commit()
            return result.rowcount > 0


# Global instance
_criteria_store: Optional[CriteriaStore] = None


def get_criteria_store() -> CriteriaStore:
    """Get the global criteria store instance."""
    global _criteria_store
    if _criteria_store is None:
        _criteria_store = CriteriaStore()
    return _criteria_store


def set_criteria_store(store: CriteriaStore):
    """Set the global criteria store instance (for testing)."""
    global _criteria_store
    _criteria_store = store
