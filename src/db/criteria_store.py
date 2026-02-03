"""Persistent store for product category criteria.

This store learns category-specific criteria over time. When a new product
category is encountered, the agent discovers relevant criteria and saves
them for future use.
"""

import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

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
    """Persistent store for product category criteria."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("data/criteria.db")
        self._initialized = False

    async def initialize(self):
        """Initialize the database and seed with default criteria."""
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS category_criteria (
                    category TEXT PRIMARY KEY,
                    criteria TEXT NOT NULL,
                    source TEXT DEFAULT 'discovered',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.commit()

            # Seed with default criteria if empty
            cursor = await db.execute("SELECT COUNT(*) FROM category_criteria")
            count = (await cursor.fetchone())[0]

            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                for category, criteria in SEED_CRITERIA.items():
                    await db.execute(
                        """INSERT INTO category_criteria (category, criteria, source, created_at, updated_at)
                           VALUES (?, ?, 'seed', ?, ?)""",
                        (category, json.dumps(criteria, ensure_ascii=False), now, now)
                    )
                await db.commit()
                logger.info("Seeded criteria store", categories=list(SEED_CRITERIA.keys()))

        self._initialized = True

    async def get_criteria(self, category: str) -> Optional[list[dict]]:
        """Get criteria for a category. Returns None if not found."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT criteria FROM category_criteria WHERE category = ?",
                (category.lower(),)
            )
            row = await cursor.fetchone()

            if row:
                return json.loads(row[0])
            return None

    async def save_criteria(self, category: str, criteria: list[dict], source: str = "discovered"):
        """Save criteria for a category."""
        await self.initialize()

        now = datetime.now(timezone.utc).isoformat()
        criteria_json = json.dumps(criteria, ensure_ascii=False)

        async with aiosqlite.connect(self.db_path) as db:
            # Check if exists
            cursor = await db.execute(
                "SELECT 1 FROM category_criteria WHERE category = ?",
                (category.lower(),)
            )
            exists = await cursor.fetchone()

            if exists:
                await db.execute(
                    """UPDATE category_criteria
                       SET criteria = ?, source = ?, updated_at = ?
                       WHERE category = ?""",
                    (criteria_json, source, now, category.lower())
                )
            else:
                await db.execute(
                    """INSERT INTO category_criteria (category, criteria, source, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (category.lower(), criteria_json, source, now, now)
                )

            await db.commit()

        logger.info("Saved category criteria",
                   category=category,
                   criteria_count=len(criteria),
                   source=source)

    async def list_categories(self) -> list[dict]:
        """List all known categories with metadata."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT category, source, created_at, updated_at FROM category_criteria ORDER BY category"
            )
            rows = await cursor.fetchall()

            return [
                {
                    "category": row[0],
                    "source": row[1],
                    "created_at": row[2],
                    "updated_at": row[3],
                }
                for row in rows
            ]

    async def delete_category(self, category: str) -> bool:
        """Delete a category. Returns True if deleted."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM category_criteria WHERE category = ?",
                (category.lower(),)
            )
            await db.commit()
            return cursor.rowcount > 0


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
