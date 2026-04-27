"""
python3 facebook.py          → scraping saja
python3 facebook.py post     → upload Facebook ke Instagram saja
python3 facebook.py post 3   → upload 3 post Facebook saja
python3 facebook.py all      → scraping + upload sekaligus
"""
import sys
from database import init_db, get_stats

init_db()
mode = sys.argv[1] if len(sys.argv) > 1 else "scrape"

if mode in ("scrape", "all"):
    from scraper import scrape_groups
    from caption import process_new_posts
    print("\n🔵 FACEBOOK — Scraping")
    print("="*45)
    scrape_groups()
    process_new_posts()
    get_stats()

if mode in ("post", "all"):
    from main import run_posting
    n = int(sys.argv[2]) if len(sys.argv) > 2 else -1
    print("\n🔵 FACEBOOK — Upload ke Instagram")
    print("="*45)
    run_posting(max_posts=n, source="facebook")
