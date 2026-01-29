"""Script to record fresh cassettes for E2E tests.

This script makes real API calls to record responses for testing.
Run this sparingly as it consumes API credits!

Usage:
    python tests/record_cassettes.py
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

CASSETTES_DIR = Path(__file__).parent / "fixtures" / "cassettes"

# Queries to record
QUERIES = [
    ("RF72DG9620B1", "IL"),  # Samsung refrigerator
    ("BFL523MB1F", "IL"),    # Bosch oven
]


async def record_all() -> None:
    """Record responses for all test queries."""
    # Import after path setup
    from src.agents.product_research import _search_products_cached

    CASSETTES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Recording {len(QUERIES)} queries to {CASSETTES_DIR}")
    print("-" * 50)

    for query, country in QUERIES:
        print(f"\nRecording: {query} in {country}...")

        try:
            # Get results with no_cache to ensure fresh data
            result = await _search_products_cached(
                query, country=country, no_cache=True
            )

            # Save as cassette
            cassette_name = f"search_{query.lower()}"
            cassette_path = CASSETTES_DIR / f"{cassette_name}.json"

            cassette_data = {
                "query": query,
                "country": country,
                "result": result,
                "recorded_at": datetime.now().isoformat(),
            }
            cassette_path.write_text(json.dumps(cassette_data, indent=2))

            # Print summary
            lines = result.split("\n") if result else []
            print(f"  Saved to {cassette_path.name}")
            print(f"  Result length: {len(result)} chars, {len(lines)} lines")

            # Show first few results
            if lines:
                print("  Preview:")
                for line in lines[:5]:
                    if line.strip():
                        print(f"    {line[:80]}...")

        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "-" * 50)
    print("Recording complete!")


def main() -> None:
    """Entry point."""
    print("=" * 50)
    print("CASSETTE RECORDER")
    print("This will make REAL API calls and consume credits!")
    print("=" * 50)

    response = input("\nProceed? (y/N): ")
    if response.lower() != "y":
        print("Cancelled.")
        return

    asyncio.run(record_all())


if __name__ == "__main__":
    main()
