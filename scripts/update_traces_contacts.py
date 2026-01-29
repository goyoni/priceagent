"""Extract phone numbers from ALL seller URLs in traces and update traces.json."""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.scraping.google.google_search_scraper import GoogleSearchScraper


async def extract_all_urls_from_traces(traces_path: Path, num_traces: int = 10) -> list[dict]:
    """Extract all seller URLs from traces."""
    with open(traces_path, 'r') as f:
        data = json.load(f)

    traces = data.get('traces', [])
    all_urls = []

    for trace_data in traces[-num_traces:]:
        trace = trace_data['trace']
        trace_id = trace['id']
        final_output = trace.get('final_output', '')

        if not final_output:
            continue

        # Extract URLs from markdown links [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        matches = re.findall(link_pattern, final_output)

        for text, url in matches:
            if url.startswith('http') and 'google.com' not in url:
                all_urls.append({
                    'trace_id': trace_id,
                    'seller_text': text,
                    'url': url,
                    'domain': urlparse(url).netloc,
                })

    return all_urls


async def extract_phones_batch(urls: list[dict]) -> dict[str, str]:
    """Extract phone numbers from URLs. Returns dict mapping URL to phone."""
    scraper = GoogleSearchScraper()

    # Deduplicate by URL
    unique_urls = list(set(u['url'] for u in urls))
    print(f"Extracting contacts from {len(unique_urls)} unique URLs...")
    print("-" * 60)

    results = {}

    for i, url in enumerate(unique_urls, 1):
        domain = urlparse(url).netloc
        print(f"[{i}/{len(unique_urls)}] {domain}...", end=" ", flush=True)

        try:
            phone = await scraper.extract_contact_info(url)
            if phone:
                print(f"✓ {phone}")
                results[url] = phone
            else:
                print("✗ No phone")
        except Exception as e:
            print(f"✗ Error: {str(e)[:50]}")

    return results


def update_traces_with_phones(traces_path: Path, phone_map: dict[str, str], num_traces: int = 10):
    """Update traces.json with extracted phone numbers."""
    with open(traces_path, 'r') as f:
        data = json.load(f)

    traces = data.get('traces', [])
    updated_count = 0

    # Update last N traces
    for trace_data in traces[-num_traces:]:
        trace = trace_data['trace']
        final_output = trace.get('final_output', '')

        if not final_output:
            continue

        # Find all URLs in the output and add phone info
        new_output = final_output

        for url, phone in phone_map.items():
            if url in new_output:
                # Check if phone is already there
                if phone not in new_output:
                    # Find the line containing this URL and add phone after it
                    # Pattern: [Link](url) or similar
                    pattern = re.escape(url) + r'\)'
                    if re.search(pattern, new_output):
                        # Add phone after the link
                        replacement = f"{url}) | 📱 {phone}"
                        new_output = re.sub(pattern, replacement, new_output, count=1)
                        updated_count += 1

        trace['final_output'] = new_output

    # Save updated traces
    with open(traces_path, 'w') as f:
        json.dump(data, f, default=str)

    return updated_count


async def main():
    print("=" * 60)
    print("Extracting phones from ALL sellers in traces.json")
    print("=" * 60)
    print()

    traces_path = Path("data/traces.json")

    # Step 1: Extract all URLs
    print("Step 1: Extracting URLs from last 10 traces...")
    urls = await extract_all_urls_from_traces(traces_path, num_traces=10)

    print(f"Found {len(urls)} seller URLs")

    # Group by domain for summary
    by_domain = {}
    for u in urls:
        domain = u['domain']
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(u)

    print("\nDomains to process:")
    for domain, items in sorted(by_domain.items()):
        print(f"  {domain}: {len(items)} links")
    print()

    # Step 2: Extract phones
    print("\nStep 2: Extracting phone numbers...")
    phone_map = await extract_phones_batch(urls)

    print(f"\n✓ Extracted {len(phone_map)} phone numbers")

    # Step 3: Update traces
    print("\nStep 3: Updating traces.json with phone numbers...")
    updated = update_traces_with_phones(traces_path, phone_map, num_traces=10)
    print(f"✓ Updated {updated} links with phone numbers")

    # Summary
    print("\n" + "=" * 60)
    print("EXTRACTED CONTACTS")
    print("=" * 60)

    if phone_map:
        for url, phone in sorted(phone_map.items(), key=lambda x: urlparse(x[0]).netloc):
            domain = urlparse(url).netloc
            print(f"  {domain}: {phone}")
            print(f"    WhatsApp: https://wa.me/{phone.replace('+', '')}")
    else:
        print("  No phone numbers found")

    print("\n✓ traces.json has been updated with contact info")


if __name__ == "__main__":
    asyncio.run(main())
