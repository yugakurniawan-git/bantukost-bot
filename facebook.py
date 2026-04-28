"""
python3 facebook.py                  → scraping saja
python3 facebook.py post             → upload Facebook ke Instagram saja
python3 facebook.py post 3           → upload 3 post Facebook saja
python3 facebook.py all              → scraping + upload sekaligus
python3 facebook.py --export-session → export session login ke fb_session.json
"""
import sys
from database import init_db, get_stats

init_db()
mode = sys.argv[1] if len(sys.argv) > 1 else "scrape"

if mode == "--export-session":
    from playwright.sync_api import sync_playwright
    print("🔐 Export session Facebook...")
    print("   Browser akan terbuka. Pastikan sudah login, lalu tutup browser.")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir="data/browser_session",
            headless=False,
        )
        # Buka Facebook untuk pastikan session valid
        page = ctx.new_page()
        page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=20000)
        import time
        time.sleep(3)
        if "login" in page.url:
            print("   ⚠️ Belum login — silakan login manual di browser, lalu tekan Enter.")
            input()
        ctx.storage_state(path="data/fb_session.json")
        ctx.close()
    import os
    size = os.path.getsize("data/fb_session.json") / 1024
    print(f"✅ Session disimpan: data/fb_session.json ({size:.1f} KB)")
    print("   Upload ke server:")
    print("   scp data/fb_session.json root@SERVER_IP:/data/bantukos/fb_session.json")

elif mode in ("scrape", "all"):
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
