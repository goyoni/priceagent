"""Google search scrapers.

Uses direct HTTP scraping (free, no API key needed).
"""

# Use direct scrapers (no API key needed)
from .google_shopping_direct import GoogleShoppingDirectScraper as GoogleShoppingScraper
from .google_search_direct import GoogleSearchDirectScraper as GoogleSearchScraper

__all__ = ["GoogleShoppingScraper", "GoogleSearchScraper"]
