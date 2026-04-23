import time
import schedule
from database import init_db, get_pending_posts, get_stats
from scraper import scrape_groups
from mamikos_scraper import scrape_mamikos
from caption import process_new_posts
from image import process_images, create_fallback_image
from uploader import post_to_instagram, upload_to_cloudinary
from config import (
    SCRAPE_INTERVAL_MINUTES,
    POST_INTERVAL_HOURS,
    IMAGES_DIR,
    IMGBB_API_KEY,
)
import os

def run_scraping():
    """Jalankan scraping Facebook + Mamikos + generate caption."""
    print("\n" + "="*50)
    print("🔄 SIKLUS SCRAPING DIMULAI")
    print("="*50)
    scrape_groups()      # Facebook Groups
    scrape_mamikos()     # Mamikos.com
    process_new_posts()  # Generate caption AI
    get_stats()

def run_posting():
    """Upload postingan yang sudah siap ke Instagram."""
    print("\n" + "="*50)
    print("📤 SIKLUS POSTING DIMULAI")
    print("="*50)

    pending = get_pending_posts()
    if not pending:
        print("ℹ️ Tidak ada postingan siap upload.")
        return

    # Ambil 1 postingan per siklus (tidak spam)
    post = pending[0]
    # Urutan kolom: id, fb_post_id, raw_text, location, price, contact, image_paths, caption, status, ...
    post_id         = post[0]
    location        = post[3]  # location
    price           = post[4]  # price
    image_paths_str = post[6]  # image_paths
    caption         = post[7]  # caption

    if not caption:
        print("⚠️ Caption kosong, skip.")
        return

    # Siapkan daftar foto yang tersedia
    image_paths = [p for p in image_paths_str.split(",") if p and os.path.exists(p)] if image_paths_str else []

    # Kalau tidak ada foto → buat fallback image branded
    if not image_paths:
        print("ℹ️ Tidak ada foto dari FB, membuat fallback image...")
        fallback = create_fallback_image(location or "Bali", price or "Hubungi pemilik")
        if fallback:
            image_paths = [fallback]

    if not image_paths:
        print("⚠️ Tidak ada foto sama sekali, skip post ini.")
        return

    # Upload foto ke Cloudinary untuk dapat URL publik yang diterima Instagram
    public_urls = []
    print("☁️ Upload foto ke Cloudinary...")
    for path in image_paths[:5]:
        # Pakai versi watermark kalau ada
        wm_path = path.replace(".jpg", "_wm.jpg")
        target  = wm_path if os.path.exists(wm_path) else path
        url = upload_to_cloudinary(target)
        if url:
            public_urls.append(url)
            print(f"   ✅ {os.path.basename(target)} → OK")

    # Post ke Instagram
    post_to_instagram(post_id, public_urls, caption)

def run_once():
    """Jalankan satu kali (untuk testing)."""
    init_db()
    run_scraping()
    run_posting()

def run_scheduled():
    """Jalankan dengan jadwal otomatis."""
    init_db()
    print("\n🤖 Bantu Kos Bot dimulai!")
    print(f"   Scraping setiap  : {SCRAPE_INTERVAL_MINUTES} menit")
    print(f"   Posting setiap   : {POST_INTERVAL_HOURS} jam")
    print("   Tekan Ctrl+C untuk berhenti\n")

    # Jadwalkan
    schedule.every(SCRAPE_INTERVAL_MINUTES).minutes.do(run_scraping)
    schedule.every(POST_INTERVAL_HOURS).hours.do(run_posting)

    # Langsung jalankan sekali saat start
    run_scraping()
    run_posting()

    # Loop utama
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "scheduled"

    if mode == "once":
        # Jalankan sekali: python main.py once
        run_once()
    else:
        # Jalankan terjadwal: python main.py
        run_scheduled()
