"""Israel-specific scrapers."""

from .zap_scraper import ZapScraper
from .zap_http_scraper import ZapHttpScraper
from .wisebuy_scraper import WiseBuyScraper
from .alm_scraper import AlmScraper, get_alm_price, is_alm_url

__all__ = ["ZapScraper", "ZapHttpScraper", "WiseBuyScraper", "AlmScraper", "get_alm_price", "is_alm_url"]
