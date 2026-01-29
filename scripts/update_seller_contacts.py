#!/usr/bin/env python3
"""Update existing sellers in the database with WhatsApp contact extraction.

This script:
1. Loads all sellers from the database
2. For each seller with a website URL but no WhatsApp number, tries to extract contact
3. Uses the new WhatsApp button extraction (first priority)
4. Updates the database with found contacts
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.session import get_db_session
from src.db.repository.sellers import SellerRepository
from src.tools.scraping.google.google_search_scraper import GoogleSearchScraper


async def update_seller_contacts():
    """Update all sellers with missing contacts."""
    scraper = GoogleSearchScraper()

    async with get_db_session() as session:
        repo = SellerRepository(session)
        sellers = await repo.list_all()

        print(f"Found {len(sellers)} sellers in database")

        updated = 0
        skipped = 0
        failed = 0

        for seller in sellers:
            # Skip if already has contact
            if seller.whatsapp_number or seller.phone_number:
                print(f"  [SKIP] {seller.seller_name} - already has contact: {seller.whatsapp_number or seller.phone_number}")
                skipped += 1
                continue

            # Skip if no website URL
            if not seller.website_url:
                print(f"  [SKIP] {seller.seller_name} - no website URL")
                skipped += 1
                continue

            print(f"  [PROC] {seller.seller_name} ({seller.website_url})...")

            try:
                # Use the scraper's contact extraction (now with WhatsApp priority)
                contact = await scraper._scrape_contact_from_page(seller.website_url)

                if contact:
                    # Update the seller
                    await repo.update(
                        seller.id,
                        whatsapp_number=contact,
                    )
                    print(f"    [OK] Found contact: {contact}")
                    updated += 1
                else:
                    print(f"    [FAIL] No contact found")
                    failed += 1

            except Exception as e:
                print(f"    [ERROR] {str(e)}")
                failed += 1

        print(f"\nSummary:")
        print(f"  Updated: {updated}")
        print(f"  Skipped: {skipped}")
        print(f"  Failed: {failed}")


async def rescrape_all_sellers():
    """Re-scrape ALL sellers (even those with existing contacts) to get fresh data."""
    scraper = GoogleSearchScraper()

    async with get_db_session() as session:
        repo = SellerRepository(session)
        sellers = await repo.list_all()

        print(f"Found {len(sellers)} sellers in database")
        print("Re-scraping ALL sellers (including those with existing contacts)...")

        updated = 0
        unchanged = 0
        failed = 0

        for seller in sellers:
            # Skip if no website URL
            if not seller.website_url:
                print(f"  [SKIP] {seller.seller_name} - no website URL")
                unchanged += 1
                continue

            print(f"  [PROC] {seller.seller_name} ({seller.website_url})...")
            old_contact = seller.whatsapp_number or seller.phone_number

            try:
                # Use the scraper's contact extraction (now with WhatsApp priority)
                contact = await scraper._scrape_contact_from_page(seller.website_url)

                if contact:
                    if contact != old_contact:
                        # Update the seller
                        await repo.update(
                            seller.id,
                            whatsapp_number=contact,
                        )
                        print(f"    [UPDATED] {old_contact or 'None'} -> {contact}")
                        updated += 1
                    else:
                        print(f"    [SAME] Contact unchanged: {contact}")
                        unchanged += 1
                else:
                    print(f"    [FAIL] No contact found (keeping old: {old_contact})")
                    failed += 1

            except Exception as e:
                print(f"    [ERROR] {str(e)}")
                failed += 1

        print(f"\nSummary:")
        print(f"  Updated: {updated}")
        print(f"  Unchanged: {unchanged}")
        print(f"  Failed: {failed}")


async def add_specific_sellers():
    """Add specific sellers mentioned by user for testing."""
    test_urls = [
        ("Electric Shop", "https://www.electricshop.co.il/"),
        ("Zabilo", "https://zabilo.com/"),
        ("Better Shop", "https://www.bettershop.co.il/"),
    ]

    scraper = GoogleSearchScraper()

    async with get_db_session() as session:
        repo = SellerRepository(session)

        for name, url in test_urls:
            print(f"Processing {name} ({url})...")

            try:
                contact = await scraper._scrape_contact_from_page(url)

                if contact:
                    await repo.create_or_update(
                        seller_name=name,
                        website_url=url,
                        whatsapp_number=contact,
                    )
                    print(f"  [OK] Saved contact: {contact}")
                else:
                    print(f"  [FAIL] No contact found")

            except Exception as e:
                print(f"  [ERROR] {str(e)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Update seller contacts in database")
    parser.add_argument(
        "--mode",
        choices=["update", "rescrape", "test"],
        default="update",
        help="Mode: 'update' fills missing contacts, 'rescrape' re-fetches all, 'test' adds specific test sellers",
    )
    args = parser.parse_args()

    if args.mode == "update":
        print("Updating sellers with missing contacts...")
        asyncio.run(update_seller_contacts())
    elif args.mode == "rescrape":
        print("Re-scraping ALL sellers...")
        asyncio.run(rescrape_all_sellers())
    elif args.mode == "test":
        print("Testing specific sellers...")
        asyncio.run(add_specific_sellers())
