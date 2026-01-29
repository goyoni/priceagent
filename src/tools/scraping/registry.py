"""Scraper registry for managing country-specific scrapers."""

from typing import Type, Optional
import yaml
from pathlib import Path

from .base_scraper import BaseScraper, ScraperConfig


class ScraperRegistry:
    """Registry for country and site specific scrapers."""

    _scrapers: dict[str, dict[str, Type[BaseScraper]]] = {}
    _configs: dict[str, dict] = {}

    @classmethod
    def register(cls, country: str, site_name: str):
        """Decorator to register a scraper for a country/site combination.

        Usage:
            @ScraperRegistry.register("IL", "zap")
            class ZapScraper(BaseScraper):
                ...
        """

        def decorator(scraper_class: Type[BaseScraper]):
            if country not in cls._scrapers:
                cls._scrapers[country] = {}
            cls._scrapers[country][site_name] = scraper_class
            return scraper_class

        return decorator

    @classmethod
    def load_country_config(cls, country: str) -> Optional[dict]:
        """Load country configuration from YAML file."""
        if country in cls._configs:
            return cls._configs[country]

        config_path = Path(__file__).parent.parent.parent / "config" / "countries" / f"{country.lower()}.yaml"

        if not config_path.exists():
            return None

        with open(config_path) as f:
            config = yaml.safe_load(f)
            cls._configs[country] = config
            return config

    @classmethod
    def get_scrapers_for_country(cls, country: str) -> list[BaseScraper]:
        """Get all registered scrapers for a country, ordered by priority.

        Args:
            country: Country code (e.g., "IL", "US")

        Returns:
            List of scraper instances
        """
        config = cls.load_country_config(country)
        if not config:
            return []

        scrapers = []
        country_scrapers = cls._scrapers.get(country, {})

        for site_config in config.get("price_comparison_sites", []):
            site_name = site_config["name"]
            if scraper_class := country_scrapers.get(site_name):
                scraper_config = ScraperConfig(
                    name=site_name,
                    base_url=site_config["base_url"],
                    search_path=site_config["search_path"],
                    priority=site_config.get("priority", 1),
                )
                scrapers.append(scraper_class(scraper_config))

        # Sort by priority
        scrapers.sort(key=lambda s: s.config.priority)
        return scrapers

    @classmethod
    def get_scraper(cls, country: str, site_name: str) -> Optional[BaseScraper]:
        """Get a specific scraper by country and site name."""
        config = cls.load_country_config(country)
        if not config:
            return None

        scraper_class = cls._scrapers.get(country, {}).get(site_name)
        if not scraper_class:
            return None

        for site_config in config.get("price_comparison_sites", []):
            if site_config["name"] == site_name:
                scraper_config = ScraperConfig(
                    name=site_name,
                    base_url=site_config["base_url"],
                    search_path=site_config["search_path"],
                    priority=site_config.get("priority", 1),
                )
                return scraper_class(scraper_config)

        return None

    @classmethod
    def list_supported_countries(cls) -> list[str]:
        """List all countries with registered scrapers."""
        return list(cls._scrapers.keys())

    @classmethod
    def list_sites_for_country(cls, country: str) -> list[str]:
        """List all registered sites for a country."""
        return list(cls._scrapers.get(country, {}).keys())
