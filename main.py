import time
import subprocess
import schedule
from database import init_db, get_pending_posts, get_stats, save_cloudinary_urls
from scraper import scrape_groups, extract_location as _clean_location
from mamikos_scraper import scrape_mamikos
from caption import process_new_posts
from image import process_images, create_fallback_image, create_mamikos_info_card, add_watermark
from uploader import post_to_instagram, upload_to_cloudinary
from config import (
    SCRAPE_INTERVAL_MINUTES,
    POST_INTERVAL_HOURS,
    MAX_POSTS_PER_RUN,
    IMAGES_DIR,
    IMGBB_API_KEY,
)
import os


def _sync_sheets_background():
    """Sync database ke Google Sheets di background (non-blocking)."""
    try:
        subprocess.Popen(
            ["python3", "sync_sheets.py", "all"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("📊 Sync Google Sheets dimulai di background.")
    except Exception as e:
        print(f"⚠️ Sync Sheets gagal: {e}")


def _sync_website_background():
    """Sync listings ke website bantukos.com via GitHub API (non-blocking)."""
    try:
        subprocess.Popen(
            ["python3", "sync_website.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("🌐 Sync website dimulai di background.")
    except Exception as e:
        print(f"⚠️ Sync website gagal: {e}")


def _check_token_expiry():
    """Cek Instagram access token mendekati expired dan cetak peringatan di log."""
    from datetime import date
    expires_str = os.getenv("INSTAGRAM_TOKEN_EXPIRES_AT", "")
    if not expires_str:
        return
    try:
        expires = date.fromisoformat(expires_str)
        days_left = (expires - date.today()).days
        if days_left <= 7:
            print("\n" + "🚨" * 25)
            print(f"🚨 TOKEN INSTAGRAM EXPIRED DALAM {days_left} HARI! ({expires_str})")
            print("   → Generate token baru di: developers.facebook.com/tools/explorer")
            print("   → Kirim ke admin untuk di-update ke server")
            print("🚨" * 25 + "\n")
        elif days_left <= 20:
            print(f"⚠️  Token Instagram akan expired dalam {days_left} hari ({expires_str}). Segera renew!")
        else:
            print(f"✅ Token Instagram valid — {days_left} hari tersisa (expired: {expires_str})")
    except ValueError:
        print(f"⚠️ Format INSTAGRAM_TOKEN_EXPIRES_AT tidak valid: '{expires_str}' (gunakan YYYY-MM-DD)")


def _batch_upload_cloudinary(max_posts: int = 30):
    """Upload foto ke Cloudinary untuk captioned posts yang belum punya CDN URL."""
    import sqlite3
    import hashlib as _hashlib

    db_path = os.path.join("data", "bantukos.db")
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT id, image_paths, location, price
        FROM posts
        WHERE status = 'captioned'
          AND image_paths IS NOT NULL AND image_paths != ''
          AND (cloudinary_urls IS NULL OR cloudinary_urls = '')
        ORDER BY id DESC
        LIMIT ?
    """, (max_posts,)).fetchall()
    conn.close()

    if not rows:
        return

    print(f"\n☁️ Batch upload foto ke Cloudinary: {len(rows)} post belum punya CDN URL...")
    uploaded = 0
    for post_id, image_paths_str, location, price in rows:
        paths = [
            p.strip() for p in image_paths_str.split(",")
            if p.strip() and os.path.exists(p.strip()) and "_wm" not in os.path.basename(p.strip())
        ]
        if not paths:
            continue
        target = add_watermark(paths[0], location=location or "", price=price or "")
        url = upload_to_cloudinary(target)
        if url:
            save_cloudinary_urls(post_id, [url])
            uploaded += 1

    if uploaded > 0:
        print(f"   ✅ {uploaded}/{len(rows)} foto berhasil di-upload ke Cloudinary")
        _sync_website_background()
    else:
        print(f"   ℹ️ Tidak ada foto baru yang berhasil di-upload")


def run_scraping(facebook_only: bool = False):
    """Jalankan scraping + generate caption. facebook_only=True untuk skip Mamikos."""
    print("\n" + "="*50)
    print("🔄 SIKLUS SCRAPING DIMULAI")
    print("="*50)
    scrape_groups()
    if not facebook_only:
        scrape_mamikos()
    process_new_posts()
    get_stats()
    _batch_upload_cloudinary(max_posts=30)

def _parse_raw_text_for_card(raw_text: str) -> dict:
    """Ambil fasilitas, rating, unit_type dari raw_text untuk info card."""
    import re
    result = {"facilities": [], "rating": "", "unit_type": ""}

    for line in raw_text.split("\n"):
        if line.startswith("Fasilitas:"):
            facs = line.replace("Fasilitas:", "").strip()
            result["facilities"] = [f.strip() for f in facs.split(",") if f.strip()]
        elif line.startswith("Tipe:"):
            result["unit_type"] = line.replace("Tipe:", "").strip()
        elif line.startswith("Rating:"):
            m = re.search(r"[\d.]+", line)
            if m:
                result["rating"] = m.group()
    return result


def _upload_one_post(post) -> bool:
    """Upload satu postingan ke Instagram. Return True kalau berhasil."""
    post_id         = post[0]
    location        = _clean_location(post[3] or "")   # re-extract untuk bersihkan nilai lama
    price           = post[4]
    image_paths_str = post[6]
    caption         = post[7]
    source          = post[11] if len(post) > 11 else "facebook"

    if not caption:
        print("⚠️ Caption kosong, skip.")
        return False

    # Siapkan foto
    # dict.fromkeys deduplikasi sambil jaga urutan — cegah carousel dengan slide identik
    # Filter _wm.jpg: file watermark adalah hasil proses, bukan sumber asli.
    # Kalau keduanya ada di DB, add_watermark akan buat _wm_wm.jpg (hash beda) → duplikat di IG.
    image_paths = list(dict.fromkeys(
        p.strip() for p in (image_paths_str or "").split(",")
        if p.strip() and os.path.exists(p.strip()) and "_wm" not in os.path.basename(p.strip())
    ))

    # ── Mamikos: prepend info card branded sebagai slide pertama ──────────
    if source == "mamikos":
        raw_text = post[2] or ""
        name     = next((l for l in raw_text.split("\n") if l and not l.startswith(("Tipe","Kos","Lokasi","Harga","Fasilitas","Ukuran","Furnished","Rating","Foto","Sumber"))), "Kos di Bali")
        extras   = _parse_raw_text_for_card(raw_text)
        card_path = create_mamikos_info_card(
            name       = name,
            price      = price or "Hubungi pemilik",
            location   = location or "Bali",
            facilities = extras["facilities"],
            rating     = extras["rating"],
            unit_type  = extras["unit_type"],
            post_id    = str(post_id),
        )
        if card_path and os.path.exists(card_path):
            image_paths = [card_path] + image_paths  # card jadi slide pertama
            print(f"   🃏 Info card dibuat: {os.path.basename(card_path)}")

    # Fallback kalau tidak ada foto sama sekali
    if not image_paths:
        print("ℹ️ Tidak ada foto, membuat fallback image...")
        fallback = create_fallback_image(location or "Bali", price or "Hubungi pemilik")
        if fallback:
            image_paths = [fallback]

    if not image_paths:
        print("⚠️ Tidak ada foto sama sekali, skip post ini.")
        return False

    # Upload ke Cloudinary — generate watermark dengan lokasi kalau belum ada
    import hashlib as _hashlib
    public_urls = []
    seen_upload_hashes = set()  # cegah foto konten sama di-upload dua kali
    print(f"☁️ Upload {len(image_paths[:5])} foto ke Cloudinary...")
    for path in image_paths[:5]:
        # Card dan fallback sudah punya branding bawaan — skip watermark
        if "card_" in path or "fallback" in os.path.basename(path):
            target = path
        else:
            # Selalu regenerate watermark (jangan pakai cache _wm.jpg lama)
            target = add_watermark(path, location=location or "", price=price or "")
        content_hash = _hashlib.md5(open(target, "rb").read()).hexdigest()
        if content_hash in seen_upload_hashes:
            print(f"   ⚠️ {os.path.basename(target)} duplikat, skip.")
            continue
        seen_upload_hashes.add(content_hash)
        url = upload_to_cloudinary(target)
        if url:
            public_urls.append(url)
            print(f"   ✅ {os.path.basename(target)} → OK")

    caption_with_id = caption + f"\n\n📋 ID: BK-{post_id}"
    result = post_to_instagram(post_id, public_urls, caption_with_id)
    if result is True and public_urls:
        save_cloudinary_urls(post_id, public_urls)
    return result


def run_posting(max_posts: int = 1, source: str = None):
    """
    Upload postingan yang sudah siap ke Instagram.

    max_posts : jumlah post yang diupload. -1 = semua.
    source    : 'facebook' | 'mamikos' | None (semua sumber)
    """
    print("\n" + "="*50)
    label = f"SIKLUS POSTING — {source.upper()}" if source else "SIKLUS POSTING"
    print(f"📤 {label}")
    print("="*50)

    pending = get_pending_posts(source=source)
    if not pending:
        src_label = f"dari {source}" if source else ""
        print(f"ℹ️ Tidak ada postingan siap upload {src_label}.")
        return

    batch = pending if max_posts == -1 else pending[:max_posts]
    src_info = f" [{source}]" if source else ""
    print(f"📋 {len(pending)} post siap{src_info}, akan upload {len(batch)} sekarang")

    uploaded = 0
    for i, post in enumerate(batch):
        src_tag = post[11] if len(post) > 11 else "?"
        print(f"\n[{i+1}/{len(batch)}] Post ID {post[0]} [{src_tag}] — {post[3][:35]}")
        result = _upload_one_post(post)
        if result is True:
            uploaded += 1
        elif result is None:
            print("⏳ Rate limit — menghentikan siklus posting, akan retry di siklus berikutnya.")
            break
        if i < len(batch) - 1:
            time.sleep(5)

    print(f"\n✅ Selesai: {uploaded}/{len(batch)} berhasil diupload")
    if uploaded > 0:
        _sync_sheets_background()
        _sync_website_background()

def run_once():
    """Jalankan satu kali (untuk testing)."""
    init_db()
    run_scraping()
    run_posting()

def run_scheduled(facebook_only: bool = True):
    """
    Jalankan dengan jadwal otomatis.
    facebook_only=True (default): hanya scrape Facebook, skip Mamikos.
    """
    init_db()
    src_label = "Facebook saja" if facebook_only else "Facebook + Mamikos"
    print("\n🤖 Bantu Kos Bot dimulai!")
    print(f"   Sumber scraping  : {src_label}")
    print(f"   Scraping setiap  : {SCRAPE_INTERVAL_MINUTES} menit")
    print(f"   Posting setiap   : {POST_INTERVAL_HOURS} jam ({MAX_POSTS_PER_RUN} post terbaik/siklus)")
    print("   Prioritas upload : Foto > Lokasi detail > No HP > Harga > Teks")
    print("   Tekan Ctrl+C untuk berhenti\n")
    _check_token_expiry()

    _scrape = lambda: run_scraping(facebook_only=facebook_only)
    _post   = lambda: run_posting(max_posts=MAX_POSTS_PER_RUN, source="facebook" if facebook_only else None)

    schedule.every(SCRAPE_INTERVAL_MINUTES).minutes.do(_scrape)
    schedule.every(POST_INTERVAL_HOURS).hours.do(_post)

    # Langsung jalankan sekali saat start
    _scrape()
    _post()

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    import sys

    # ── Parsing argumen ─────────────────────────────────────────────────────
    # python main.py                        → scheduled
    # python main.py once                   → scraping + 1 post (semua sumber)
    # python main.py post                   → upload semua pending (semua sumber)
    # python main.py post facebook          → upload semua dari Facebook
    # python main.py post mamikos           → upload semua dari Mamikos
    # python main.py post facebook 5        → upload 5 dari Facebook
    # python main.py post mamikos 3         → upload 3 dari Mamikos
    # python main.py post 5                 → upload 5 dari semua sumber

    mode = sys.argv[1] if len(sys.argv) > 1 else "scheduled"

    if mode == "once":
        run_once()

    elif mode == "post":
        init_db()
        args = sys.argv[2:]  # sisa argumen setelah "post"

        # Tentukan source dan max_posts dari argumen
        src = None
        n   = -1

        for arg in args:
            if arg in ("facebook", "mamikos"):
                src = arg
            else:
                try:
                    n = int(arg)
                except ValueError:
                    print(f"⚠️ Argumen tidak dikenali: '{arg}', diabaikan.")

        run_posting(max_posts=n, source=src)

    else:
        run_scheduled()
