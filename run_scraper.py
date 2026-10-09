import sys
import os
import argparse

sys.path.append(os.path.abspath('Backend'))

from scrappers.controller import run
from scrappers.base import ScrapeParams

def main():
    parser = argparse.ArgumentParser(description="Run a specific scraper")
    parser.add_argument("scraper_id", help="The ID of the scraper to run (e.g., bonfire, dasny, jwiz, nyscr)")
    parser.add_argument("--limit", type=int, default=3, help="Number of records to scrape (default: 3)")
    parser.add_argument("--keyword", type=str, default=None, help="Keyword to search for")
    parser.add_argument("--city", type=str, default=None, help="City to search in")
    parser.add_argument("--us_state", type=str, default=None, help="State to search in (e.g., NY)")
    
    args = parser.parse_args()

    params = ScrapeParams(
        limit=args.limit,
        keyword=args.keyword,
        city=args.city,
        us_state=args.us_state
    )

    print(f"--- Running {args.scraper_id} ---")
    try:
        results = run(args.scraper_id, params)
        count = 0
        for r in results:
            print(r.model_dump_json(indent=2))
            count += 1
            if count >= args.limit:
                break
        print(f"--- Completed {args.scraper_id}: {count} records extracted ---")
    except Exception as e:
        print(f"Error running {args.scraper_id}: {e}")

if __name__ == "__main__":
    main()
