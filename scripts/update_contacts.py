"""Script to extract phone numbers from seller URLs in saved searches."""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.scraping.google.google_search_scraper import GoogleSearchScraper


def extract_urls_from_traces(traces_path: Path, num_traces: int = 10) -> dict[str, set[str]]:
    """Extract seller URLs from the last N traces.

    Returns dict mapping trace_id to set of URLs.
    """
    with open(traces_path, 'r') as f:
        data = json.load(f)

    traces = data.get('traces', [])
    result = {}

    for trace_data in traces[-num_traces:]:
        trace = trace_data['trace']
        trace_id = trace['id']
        final_output = trace.get('final_output', '')

        if not final_output:
            continue

        # Extract URLs from markdown links [text](url)
        urls = set()
        link_pattern = r'\[(?:[^\]]+)\]\(([^)]+)\)'
        matches = re.findall(link_pattern, final_output)

        for url in matches:
            # Skip Google search result pages - we want actual seller pages
            if 'google.com/search' in url:
                continue
            # Only include http/https URLs
            if url.startswith('http'):
                urls.add(url)

        if urls:
            result[trace_id] = urls
            print(f"Trace {trace_id[:8]}...: Found {len(urls)} seller URLs")

    return result


async def extract_contacts_for_urls(urls: set[str]) -> dict[str, str]:
    """Extract phone numbers from seller URLs using Playwright.

    Returns dict mapping URL to phone number (or None if not found).
    """
    scraper = GoogleSearchScraper()
    results = {}

    for url in urls:
        try:
            print(f"  Extracting from: {urlparse(url).netloc}...")
            phone = await scraper.extract_contact_info(url)
            if phone:
                results[url] = phone
                print(f"    ✓ Found: {phone}")
            else:
                print(f"    ✗ No phone found")
        except Exception as e:
            print(f"    ✗ Error: {e}")

    return results


async def main():
    print("=" * 60)
    print("Extracting contacts from last 10 saved searches")
    print("=" * 60)
    print()

    traces_path = Path("data/traces.json")
    if not traces_path.exists():
        print("No traces.json found")
        return

    # Get URLs from traces
    print("Step 1: Extracting URLs from saved searches...")
    trace_urls = extract_urls_from_traces(traces_path, num_traces=10)

    if not trace_urls:
        print("No seller URLs found in traces")
        return

    # Collect all unique URLs
    all_urls = set()
    for urls in trace_urls.values():
        all_urls.update(urls)

    print(f"\nFound {len(all_urls)} unique seller URLs across {len(trace_urls)} traces")
    print()

    # Extract contacts
    print("Step 2: Extracting phone numbers from seller pages...")
    print("-" * 40)
    contacts = await extract_contacts_for_urls(all_urls)

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    if contacts:
        print(f"\nSuccessfully extracted {len(contacts)} phone numbers:\n")
        for url, phone in contacts.items():
            domain = urlparse(url).netloc
            print(f"  {domain}: {phone}")
    else:
        print("\nNo phone numbers found on any seller pages.")

    print()
    print("Note: These contacts can now be used for negotiation drafts.")


if __name__ == "__main__":
    asyncio.run(main())
