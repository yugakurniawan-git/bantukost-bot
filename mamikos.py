"""
python3 mamikos.py          → scraping saja
python3 mamikos.py post     → upload Mamikos ke Instagram saja
python3 mamikos.py post 3   → upload 3 post Mamikos saja
python3 mamikos.py all      → scraping + upload sekaligus
"""
import sys
from database import init_db, get_stats

init_db()
mode = sys.argv[1] if len(sys.argv) > 1 else "scrape"

if mode in ("scrape", "all"):
    from mamikos_scraper import scrape_mamikos
    from caption import process_new_posts
    print("\n🟠 MAMIKOS — Scraping")
    print("="*45)
    scrape_mamikos()
    process_new_posts()
    get_stats()

if mode in ("post", "all"):
    from main import run_posting
    n = int(sys.argv[2]) if len(sys.argv) > 2 else -1
    print("\n🟠 MAMIKOS — Upload ke Instagram")
    print("="*45)
    run_posting(max_posts=n, source="mamikos")
