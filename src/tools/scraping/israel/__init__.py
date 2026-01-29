"""Israel-specific scrapers."""

from .zap_scraper import ZapScraper
from .zap_http_scraper import ZapHttpScraper
from .wisebuy_scraper import WiseBuyScraper

__all__ = ["ZapScraper", "ZapHttpScraper", "WiseBuyScraper"]
