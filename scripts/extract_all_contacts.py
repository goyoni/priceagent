"""Script to search for products and extract phone numbers from ALL sellers."""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.scraping.registry import ScraperRegistry
from src.tools.scraping.google.google_search_scraper import GoogleSearchScraper


async def search_product(product_code: str) -> list[dict]:
    """Search for a product across all scrapers and return seller info."""
    print(f"\n🔍 Searching for: {product_code}")
    print("-" * 40)

    sellers = []

    # Get all registered scrapers for Israel
    scrapers = ScraperRegistry.get_scrapers("IL")

    for scraper in scrapers:
        scraper_name = scraper.config.name
        print(f"  Using scraper: {scraper_name}...")

        try:
            results = await scraper.search(product_code, max_results=10)
            print(f"    Found {len(results)} results")

            for result in results:
                if result.url and result.url.startswith("http"):
                    sellers.append({
                        "product": product_code,
                        "seller_name": result.seller.name,
                        "url": result.url,
                        "price": result.listed_price,
                        "currency": result.currency,
                        "scraper": scraper_name,
                        "existing_phone": result.seller.whatsapp_number,
                    })
        except Exception as e:
            print(f"    Error: {e}")

    return sellers


async def extract_contacts(sellers: list[dict]) -> list[dict]:
    """Extract phone numbers from seller URLs."""
    print(f"\n📞 Extracting contacts from {len(sellers)} sellers...")
    print("=" * 60)

    scraper = GoogleSearchScraper()

    # Deduplicate by URL
    seen_urls = set()
    unique_sellers = []
    for seller in sellers:
        url = seller["url"]
        # Skip Google search result pages
        if "google.com/search" in url:
            continue
        if url not in seen_urls:
            seen_urls.add(url)
            unique_sellers.append(seller)

    print(f"  {len(unique_sellers)} unique seller URLs (excluding Google links)")
    print()

    results = []
    for i, seller in enumerate(unique_sellers, 1):
        url = seller["url"]
        domain = urlparse(url).netloc

        # Skip if already has phone
        if seller.get("existing_phone"):
            print(f"[{i}/{len(unique_sellers)}] {domain}: Already has phone {seller['existing_phone']}")
            seller["phone"] = seller["existing_phone"]
            results.append(seller)
            continue

        print(f"[{i}/{len(unique_sellers)}] {domain}...", end=" ", flush=True)

        try:
            phone = await scraper.extract_contact_info(url)
            if phone:
                print(f"✓ {phone}")
                seller["phone"] = phone
            else:
                print("✗ No phone found")
                seller["phone"] = None
        except Exception as e:
            print(f"✗ Error: {e}")
            seller["phone"] = None

        results.append(seller)

    return results


def display_results(results: list[dict]):
    """Display results grouped by product."""
    print("\n")
    print("=" * 70)
    print("                    CONTACT EXTRACTION RESULTS")
    print("=" * 70)

    # Group by product
    by_product = {}
    for r in results:
        product = r["product"]
        if product not in by_product:
            by_product[product] = []
        by_product[product].append(r)

    total_with_phone = 0
    total_sellers = 0

    for product, sellers in by_product.items():
        print(f"\n📦 {product}")
        print("-" * 50)

        # Sort by price
        sellers.sort(key=lambda x: x.get("price", float("inf")) or float("inf"))

        for seller in sellers:
            total_sellers += 1
            price_str = f"{seller['price']:,.0f} {seller['currency']}" if seller.get("price") else "N/A"
            phone = seller.get("phone")

            if phone:
                total_with_phone += 1
                print(f"  ✓ {seller['seller_name']:<30} {price_str:>15}  📱 {phone}")
            else:
                print(f"  ✗ {seller['seller_name']:<30} {price_str:>15}  (no phone)")

    print("\n" + "=" * 70)
    print(f"SUMMARY: Found phones for {total_with_phone}/{total_sellers} sellers ({100*total_with_phone/total_sellers:.0f}%)")
    print("=" * 70)

    # Show sellers with phones for easy copying
    sellers_with_phones = [r for r in results if r.get("phone")]
    if sellers_with_phones:
        print("\n📋 Sellers with phone numbers (for negotiation):\n")
        for s in sellers_with_phones:
            domain = urlparse(s["url"]).netloc
            print(f"  {s['seller_name']} ({domain})")
            print(f"    Product: {s['product']}")
            print(f"    Price: {s.get('price', 'N/A')} {s.get('currency', '')}")
            print(f"    Phone: {s['phone']}")
            print(f"    WhatsApp: https://wa.me/{s['phone'].replace('+', '')}")
            print()


async def main():
    print("=" * 60)
    print("Searching products and extracting ALL seller contacts")
    print("=" * 60)

    # Products from last 10 searches
    products = ["RF72DG9620B1", "SMV4HAX21E", "BFL523MB1F"]

    # Search for all products
    all_sellers = []
    for product in products:
        sellers = await search_product(product)
        all_sellers.extend(sellers)

    print(f"\n📊 Total sellers found: {len(all_sellers)}")

    # Extract contacts
    results = await extract_contacts(all_sellers)

    # Display results
    display_results(results)

    # Save results to file
    output_path = Path("data/extracted_contacts.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 Results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
