#!/usr/bin/env python3
"""Script to verify and update seller phone numbers using HTTP requests."""

import asyncio
import re
import sqlite3
from typing import Optional
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup


@dataclass
class SellerPhoneUpdate:
    """Represents a potential phone number update."""
    id: int
    name: str
    domain: str
    current_phone: str
    new_phone: Optional[str]
    source: str  # How the phone was found (whatsapp, footer, body, etc.)


def find_phone_in_html(html: str) -> tuple[Optional[str], str]:
    """Find phone numbers in HTML content.

    Returns tuple of (phone_number, source_description).

    Prioritizes phone numbers from:
    1. WhatsApp links (most reliable)
    2. Footer and contact sections
    3. Page body (fallback)
    """
    # Check for WhatsApp API links first - most reliable
    # Matches: api.whatsapp.com/send/?phone=972545472406 or api.whatsapp.com/send?phone=...
    wa_api_pattern = r'api\.whatsapp\.com/send/?\?phone=(\d+)'
    wa_api_matches = re.findall(wa_api_pattern, html)
    if wa_api_matches:
        phone = wa_api_matches[0]
        if not phone.startswith('+'):
            phone = '+' + phone
        return phone, "whatsapp_api"

    # Check for wa.me links
    wa_pattern = r'wa\.me/(\d+)'
    wa_matches = re.findall(wa_pattern, html)
    if wa_matches:
        phone = wa_matches[0]
        if not phone.startswith('+'):
            phone = '+' + phone
        return phone, "whatsapp_link"

    # Also check for whatsapp:// protocol
    wa_protocol_pattern = r'whatsapp://send\?phone=(\d+)'
    wa_protocol_matches = re.findall(wa_protocol_pattern, html)
    if wa_protocol_matches:
        phone = wa_protocol_matches[0]
        if not phone.startswith('+'):
            phone = '+' + phone
        return phone, "whatsapp_protocol"

    # Israeli phone patterns
    phone_patterns = [
        r"05\d[\s-]?\d{3}[\s-]?\d{4}",  # Mobile: 05X-XXX-XXXX
        r"0[2-9][\s-]?\d{7}",  # Landline: 0X-XXXXXXX
        r"\+972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",  # International mobile
        r"\+972[\s-]?[2-9][\s-]?\d{7}",  # International landline
        r"972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",  # International without +
    ]

    # Parse HTML to look in specific sections first
    soup = BeautifulSoup(html, "lxml")

    # Priority sections to search for phone numbers
    priority_selectors = [
        ("footer", "footer"),
        (".footer", "footer_class"),
        ("#footer", "footer_id"),
        ("[class*='contact']", "contact_section"),
        ("[id*='contact']", "contact_id"),
        ("[class*='phone']", "phone_class"),
        ("[id*='phone']", "phone_id"),
        ("[class*='whatsapp']", "whatsapp_class"),
        (".about", "about_section"),
        ("#about", "about_id"),
        ("[itemtype*='LocalBusiness']", "schema_localbusiness"),
        ("[itemtype*='Organization']", "schema_org"),
    ]

    # Search in priority sections first
    for selector, source in priority_selectors:
        elements = soup.select(selector)
        for element in elements:
            text = element.get_text()
            for pattern in phone_patterns:
                matches = re.findall(pattern, text)
                if matches:
                    phone = re.sub(r"[\s-]", "", matches[0])
                    if phone.startswith("972") and not phone.startswith("+"):
                        phone = "+" + phone
                    elif phone.startswith("0"):
                        phone = "+972" + phone[1:]
                    return phone, source

    # Fallback: search the entire page, but start from the bottom (footer area)
    lines = html.split('\n')
    bottom_half = '\n'.join(lines[len(lines)//2:])

    for pattern in phone_patterns:
        matches = re.findall(pattern, bottom_half)
        if matches:
            phone = re.sub(r"[\s-]", "", matches[0])
            if phone.startswith("972") and not phone.startswith("+"):
                phone = "+" + phone
            elif phone.startswith("0"):
                phone = "+972" + phone[1:]
            return phone, "bottom_half"

    # Final fallback: search entire page
    for pattern in phone_patterns:
        matches = re.findall(pattern, html)
        if matches:
            phone = re.sub(r"[\s-]", "", matches[0])
            if phone.startswith("972") and not phone.startswith("+"):
                phone = "+" + phone
            elif phone.startswith("0"):
                phone = "+972" + phone[1:]
            return phone, "full_page"

    return None, "not_found"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he,en;q=0.9",
}


async def fetch_page(url: str) -> Optional[str]:
    """Fetch page HTML using HTTP requests."""
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=30.0,
            verify=False,  # Some sites have SSL issues
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


async def check_seller(seller_id: int, name: str, domain: str, current_phone: str) -> SellerPhoneUpdate:
    """Check a single seller's website for phone number."""
    url = f"https://www.{domain}"
    print(f"Checking {name} ({domain})...")

    html = await fetch_page(url)
    if not html:
        return SellerPhoneUpdate(
            id=seller_id,
            name=name,
            domain=domain,
            current_phone=current_phone,
            new_phone=None,
            source="fetch_failed"
        )

    new_phone, source = find_phone_in_html(html)

    return SellerPhoneUpdate(
        id=seller_id,
        name=name,
        domain=domain,
        current_phone=current_phone,
        new_phone=new_phone,
        source=source
    )


async def main():
    """Main function to check all sellers."""
    # Connect to database
    db_path = "data/negotiations.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all sellers
    cursor.execute("SELECT id, seller_name, domain, phone_number FROM sellers WHERE domain IS NOT NULL AND domain != ''")
    sellers = cursor.fetchall()

    print(f"\nChecking {len(sellers)} sellers...\n")
    print("=" * 80)

    updates = []
    for seller_id, name, domain, current_phone in sellers:
        if not domain or domain == "teststore.co.il":  # Skip test entries
            continue
        result = await check_seller(seller_id, name, domain, current_phone or "")
        updates.append(result)
        # Small delay between requests
        await asyncio.sleep(0.5)

    # Print results table
    print("\n" + "=" * 100)
    print(f"{'ID':<4} {'Name':<25} {'Current Phone':<18} {'New Phone':<18} {'Source':<20} {'Status':<10}")
    print("=" * 100)

    changes = []
    for u in updates:
        status = ""
        if u.new_phone is None:
            status = "NO PHONE"
        elif u.current_phone == u.new_phone:
            status = "OK"
        else:
            status = "CHANGED"
            changes.append(u)

        print(f"{u.id:<4} {u.name[:24]:<25} {u.current_phone:<18} {(u.new_phone or 'N/A'):<18} {u.source:<20} {status:<10}")

    print("=" * 100)

    # Summary
    print(f"\nSummary:")
    print(f"  Total sellers checked: {len(updates)}")
    print(f"  Phone numbers to update: {len(changes)}")

    if changes:
        print(f"\n  Sellers needing update:")
        for c in changes:
            print(f"    - {c.name}: {c.current_phone} -> {c.new_phone} (from {c.source})")

        # Ask for confirmation
        print(f"\nTo apply these updates, run:")
        for c in changes:
            print(f'  sqlite3 {db_path} "UPDATE sellers SET phone_number=\'{c.new_phone}\' WHERE id={c.id};"')

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
