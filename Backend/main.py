#!/usr/bin/env python3
"""
Dallas City Hall Bonfire Scraper - Main Entry Point
Target: https://dallascityhall.bonfirehub.com/portal/?tab=openOpportunities
"""

import sys
from dallas_bonfire_scraper import DallasBonfireScraper, BASE_URL


def main():
    print("=" * 60)
    print("  Dallas City Hall Bonfire Opportunities Scraper")
    print(f"  Target: {BASE_URL}")
    print("=" * 60)

    # Use headless=False if user wants to see the browser, or headless=True
    scraper = DallasBonfireScraper(headless=True)

    try:
        print("\nStarting browser session...")
        if not scraper.setup_chrome():
            print("Failed to initialize Chrome browser.")
            return

        print(f"Discovering open opportunities...")
        queue = scraper.discover_opportunities()

        if len(queue) == 0:
            print("No Opportunities Found")
            return

        print(f"\nDiscovered {len(queue)} opportunities.")
        print("\nTesting FIRST opportunity details extraction...\n")

        raw = scraper.extract_details(queue[0])

        print("\nExtraction Successful:")
        print(raw)

        # Also save all discovered opportunities
        scraper.save(queue, "dallas_bonfire_data.json")
        print(f"\nSaved {len(queue)} opportunities to dallas_bonfire_data.json")

    except KeyboardInterrupt:
        print("\nOperation interrupted by user.")
    except Exception as e:
        print(f"Error during execution: {e}")
    finally:
        scraper.close()
        print("Browser closed.")


if __name__ == "__main__":
    main()