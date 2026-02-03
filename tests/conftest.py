"""Pytest configuration and fixtures for e2e testing."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

CASSETTES_DIR = Path(__file__).parent / "fixtures" / "cassettes"


@pytest.fixture(autouse=True)
def disable_trace_logging():
    """Disable trace logging for all tests to prevent test traces from polluting storage."""
    # Patch settings directly since the module is already imported
    from src.config import settings as settings_module

    original_value = settings_module.settings.trace_enabled
    settings_module.settings.trace_enabled = False
    yield
    settings_module.settings.trace_enabled = original_value


@pytest.fixture(autouse=True)
def init_test_database(tmp_path: Path):
    """Initialize test database with all tables for tests that need it."""
    import asyncio
    from src.db.base import Base, get_engine, reset_engine
    from src.db import models  # noqa: F401 - Import to register models
    from src.config import settings as settings_module

    # Reset global engine to use test database
    reset_engine()

    # Ensure we use SQLite for tests (not PostgreSQL)
    original_database_url = settings_module.settings.database_url
    settings_module.settings.database_url = None

    # Set the database path to the test temp directory
    test_db_path = tmp_path / "test.db"
    original_database_path = settings_module.settings.database_path
    settings_module.settings.database_path = test_db_path

    async def init():
        engine = get_engine(test_db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop().run_until_complete(init())
    yield

    # Reset after test
    reset_engine()
    settings_module.settings.database_url = original_database_url
    settings_module.settings.database_path = original_database_path


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options."""
    parser.addoption(
        "--record",
        action="store_true",
        default=False,
        help="Record new cassettes from live API calls (costs credits!)",
    )


@pytest.fixture
def record_mode(request: pytest.FixtureRequest) -> bool:
    """Check if we're in record mode (use real APIs)."""
    return request.config.getoption("--record", default=False)


@pytest.fixture
def cache_manager(tmp_path: Path):
    """Provide a fresh cache manager for each test."""
    from src.cache.manager import CacheManager

    manager = CacheManager(db_path=tmp_path / "test_cache.db", max_memory_items=100)
    return manager


@pytest.fixture
def mock_cache_manager(tmp_path: Path):
    """Patch the global cache manager with a test instance."""
    from src.cache import manager as cache_module

    test_manager = cache_module.CacheManager(
        db_path=tmp_path / "test_cache.db", max_memory_items=100
    )

    original_get = cache_module.get_cache_manager

    def get_test_manager():
        return test_manager

    with patch.object(cache_module, "get_cache_manager", get_test_manager):
        yield test_manager

    # Reset global manager after test
    cache_module.reset_cache_manager()


@pytest.fixture
def mock_settings(tmp_path: Path):
    """Test settings with cache enabled and tracing disabled."""
    from src.config.settings import Settings

    # Create a test settings instance
    test_settings = Settings(
        openai_api_key="test-key",
        cache_enabled=True,
        cache_path=tmp_path / "cache.db",
        cache_ttl_scraper_hours=24,
        cache_ttl_contact_days=7,
        cache_ttl_agent_hours=24,
        trace_enabled=False,  # Disable tracing in tests
    )

    with patch("src.config.settings.settings", test_settings):
        with patch("src.cache.decorators.settings", test_settings):
            yield test_settings


@pytest.fixture
def recorded_responses():
    """Load recorded API responses from cassettes.

    Returns a callable that loads cassette data by name.
    """

    def _load(cassette_name: str) -> dict[str, Any]:
        path = CASSETTES_DIR / f"{cassette_name}.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

    return _load


@pytest.fixture
def save_cassette():
    """Save response data to a cassette file.

    Returns a callable that saves data to cassette by name.
    """

    def _save(cassette_name: str, data: dict[str, Any]) -> Path:
        CASSETTES_DIR.mkdir(parents=True, exist_ok=True)
        path = CASSETTES_DIR / f"{cassette_name}.json"

        cassette_data = {
            **data,
            "recorded_at": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(cassette_data, indent=2, default=str))
        return path

    return _save


class CassetteRecorder:
    """Helper class for recording and replaying API responses."""

    def __init__(self, cassette_name: str, record_mode: bool):
        self.cassette_name = cassette_name
        self.record_mode = record_mode
        self.recordings: dict[str, Any] = {}
        self._cassette_path = CASSETTES_DIR / f"{cassette_name}.json"

        if not record_mode and self._cassette_path.exists():
            self.recordings = json.loads(self._cassette_path.read_text())

    def get(self, key: str) -> Any | None:
        """Get recorded value for key."""
        return self.recordings.get(key)

    def set(self, key: str, value: Any) -> None:
        """Record a value for key."""
        self.recordings[key] = value

    def save(self) -> None:
        """Save recordings to cassette file."""
        if self.record_mode and self.recordings:
            CASSETTES_DIR.mkdir(parents=True, exist_ok=True)
            self.recordings["recorded_at"] = datetime.now().isoformat()
            self._cassette_path.write_text(
                json.dumps(self.recordings, indent=2, default=str)
            )


@pytest.fixture
def cassette_recorder(request: pytest.FixtureRequest, record_mode: bool):
    """Create a cassette recorder for the test.

    Usage:
        def test_something(cassette_recorder):
            recorder = cassette_recorder("my_test")
            if recorder.record_mode:
                # Make real call and record
                result = real_api_call()
                recorder.set("result", result)
            else:
                # Use recorded data
                result = recorder.get("result")
    """

    recorders: list[CassetteRecorder] = []

    def _create_recorder(cassette_name: str) -> CassetteRecorder:
        recorder = CassetteRecorder(cassette_name, record_mode)
        recorders.append(recorder)
        return recorder

    yield _create_recorder

    # Save all recorders after test
    for recorder in recorders:
        recorder.save()
