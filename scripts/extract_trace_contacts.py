"""Extract phone numbers for ALL sellers in a specific trace."""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.scraping.google.google_search_scraper import GoogleSearchScraper


async def extract_contacts_for_trace(trace_id: str):
    """Extract contacts for all sellers in a trace."""

    traces_path = Path("data/traces.json")
    with open(traces_path, 'r') as f:
        data = json.load(f)

    # Find the trace
    trace_data = None
    for td in data.get('traces', []):
        if td['trace']['id'] == trace_id:
            trace_data = td
            break

    if not trace_data:
        print(f"Trace {trace_id} not found")
        return

    # Get the tool output which has all sellers
    tool_output = None
    for span in trace_data.get('spans', []):
        if span.get('tool_output'):
            tool_output = span['tool_output']
            break

    if not tool_output:
        print("No tool output found in trace")
        return

    # Extract all seller URLs from tool output
    # Pattern: URL: https://...
    url_pattern = r'URL:\s*(https?://[^\s]+)'
    urls = re.findall(url_pattern, tool_output)

    # Also extract seller names for each URL
    seller_info = []
    lines = tool_output.split('\n')
    current_seller = None

    for line in lines:
        # Match seller line: "1. Seller Name [source]" or "1. Seller Name (Rating)"
        seller_match = re.match(r'^\d+\.\s+(.+?)(?:\s+\[|\s+\(Rating)', line)
        if seller_match:
            current_seller = seller_match.group(1).strip()

        # Match URL line
        url_match = re.search(r'URL:\s*(https?://[^\s]+)', line)
        if url_match and current_seller:
            seller_info.append({
                'seller': current_seller,
                'url': url_match.group(1),
            })

    # Also get bundle seller URLs (different format)
    # Pattern: "- PRODUCT: PRICE ILS | URL"
    bundle_pattern = r'-\s+\w+:\s+[\d,]+\s+ILS\s+\|\s+(https?://[^\s]+)'
    bundle_urls = re.findall(bundle_pattern, tool_output)

    # Deduplicate
    seen_urls = set()
    unique_sellers = []
    for s in seller_info:
        if s['url'] not in seen_urls:
            seen_urls.add(s['url'])
            unique_sellers.append(s)

    print(f"Trace: {trace_id}")
    print(f"Found {len(unique_sellers)} unique seller URLs")
    print("=" * 70)

    # Extract contacts
    scraper = GoogleSearchScraper()
    results = {}

    for i, s in enumerate(unique_sellers, 1):
        seller = s['seller']
        url = s['url']
        domain = urlparse(url).netloc if 'google.com' not in url else 'google.com'

        print(f"[{i}/{len(unique_sellers)}] {seller} ({domain})...", end=" ", flush=True)

        try:
            phone = await scraper.extract_contact_info(url)
            if phone:
                print(f"✓ {phone}")
                results[seller] = phone
            else:
                print("✗ No phone")
        except Exception as e:
            print(f"✗ Error: {str(e)[:40]}")

    # Update the trace with contact info
    print("\n" + "=" * 70)
    print("UPDATING TRACE")
    print("=" * 70)

    # Update tool_output with contact info
    updated_output = tool_output
    for seller, phone in results.items():
        # Find lines with this seller and add contact info
        pattern = rf'(\d+\.\s+{re.escape(seller)}.*?URL:\s*https?://[^\s]+)'
        def add_contact(m):
            if 'Contact:' not in m.group(0):
                return m.group(0) + f'\n   Contact: {phone}'
            return m.group(0)
        updated_output = re.sub(pattern, add_contact, updated_output, flags=re.DOTALL)

    # Update the span
    for span in trace_data.get('spans', []):
        if span.get('tool_output'):
            span['tool_output'] = updated_output
            break

    # Also update final_output
    final_output = trace_data['trace'].get('final_output', '')
    for seller, phone in results.items():
        # Add contact to seller lines in final output
        # Pattern: **Seller:** PRICE ILS | [Link](URL)
        pattern = rf'(\*\*{re.escape(seller)}[^|]*\|\s*\[Link\]\([^)]+\))'
        def add_contact_final(m):
            if 'Contact:' not in m.group(0):
                return m.group(0) + f' | Contact: {phone}'
            return m.group(0)
        final_output = re.sub(pattern, add_contact_final, final_output)

    trace_data['trace']['final_output'] = final_output

    # Save updated traces
    with open(traces_path, 'w') as f:
        json.dump(data, f, default=str)

    print(f"\n✓ Updated trace with {len(results)} contacts")

    # Summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"Total sellers: {len(unique_sellers)}")
    print(f"Contacts found: {len(results)}")
    print(f"Coverage: {100 * len(results) / len(unique_sellers):.0f}%")
    print()

    for seller, phone in sorted(results.items()):
        print(f"  {seller}: {phone}")


if __name__ == "__main__":
    trace_id = "13c97969-0e6f-4e31-a186-ae57131e6dae"
    asyncio.run(extract_contacts_for_trace(trace_id))
