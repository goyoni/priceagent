"""Web scraping tools for price comparison sites."""

from .base_scraper import BaseScraper, ScraperConfig
from .registry import ScraperRegistry

# Import country-specific scrapers to register them
from . import israel

# Import Google scrapers (work for any country with SerpAPI)
from . import google

__all__ = ["BaseScraper", "ScraperConfig", "ScraperRegistry"]
