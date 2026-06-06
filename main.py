import time
import random
import datetime
import threading
import subprocess
import schedule
from database import init_db, get_pending_posts, get_stats, save_cloudinary_urls, mark_posted
from scraper import scrape_groups, get_rotation_batch, extract_location as _clean_location
from mamikos_scraper import scrape_mamikos
from caption import process_new_posts
from outreach import run_outreach, init_outreach_db
from image import process_images, create_fallback_image, create_mamikos_info_card, add_watermark
from uploader import post_to_instagram, upload_to_cloudinary
from config import (
    POST_INTERVAL_HOURS,
    MAX_POSTS_PER_RUN,
    IMAGES_DIR,
    IMGBB_API_KEY,
    SCRAPE_INTERVAL_MIN_MINUTES,
    SCRAPE_INTERVAL_MAX_MINUTES,
    SCRAPE_ACTIVE_HOUR_START,
    SCRAPE_ACTIVE_HOUR_END,
    SCRAPE_GROUPS_PER_RUN,
    SCRAPE_SKIP_CHANCE,
)
import os


def _notify_wa(message: str, key: str = "default"):
    """
    Kirim notifikasi ke owner via WA bot, max 1x per hari per key.
    key: identifier unik per jenis alert (misal 'token_expiry', 'fb_session').
    """
    import urllib.request, urllib.error, json as _json
    from datetime import date

    # Rate-limit: simpan tanggal terakhir kirim per key di data/notify_log.json
    log_path = os.path.join("data", "notify_log.json")
    today = str(date.today())
    try:
        log = _json.loads(open(log_path).read()) if os.path.exists(log_path) else {}
    except Exception:
        log = {}

    if log.get(key) == today:
        print(f"ℹ️ WA notify '{key}' sudah dikirim hari ini, skip.")
        return

    wa_url = os.getenv("WA_NOTIFY_URL", "http://bantukos-wa-bot:3001/notify")
    try:
        data = _json.dumps({"message": message, "system": True}).encode()
        req = urllib.request.Request(wa_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
        log[key] = today
        open(log_path, "w").write(_json.dumps(log))
        print(f"🔔 WA notify '{key}' terkirim.")
    except Exception as e:
        print(f"⚠️ WA notify gagal: {e}")


def _sync_sheets_background():
    """Sync database ke Google Sheets di background (non-blocking)."""
    try:
        import sys as _sys
        subprocess.Popen(
            [_sys.executable, "sync_sheets.py", "all"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("📊 Sync Google Sheets dimulai di background.")
    except Exception as e:
        print(f"⚠️ Sync Sheets gagal: {e}")


def _sync_website_background():
    """Sync listings ke website bantukos.com via GitHub API (non-blocking)."""
    try:
        import sys as _sys
        subprocess.Popen(
            [_sys.executable, "sync_website.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("🌐 Sync website dimulai di background.")
    except Exception as e:
        print(f"⚠️ Sync website gagal: {e}")


def _refresh_ig_token():
    """
    Auto-refresh Instagram long-lived token setiap minggu.
    Token yang masih valid diperpanjang 60 hari. Hasilnya ditulis ke /app/.env.
    """
    import requests
    from config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID
    if not INSTAGRAM_ACCESS_TOKEN:
        return
    try:
        resp = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": INSTAGRAM_ACCESS_TOKEN},
            timeout=15,
        )
        data = resp.json()
        new_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 0)  # seconds
        if not new_token:
            err = data.get("error", {}).get("message", str(data))
            print(f"⚠️ Token refresh gagal: {err}")
            _notify_wa(f"⚠️ *Bantukos Bot*: Gagal auto-refresh token Instagram!\n\n{err}\n\nSegera update manual di Coolify.", key="token_refresh_fail")
            return

        days_left = round(expires_in / 86400)
        print(f"✅ Token Instagram di-refresh! Berlaku {days_left} hari lagi.")

        # Update /app/.env agar persisten sampai restart berikutnya
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        lines = []
        found = False
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("INSTAGRAM_ACCESS_TOKEN="):
                    lines.append(f"INSTAGRAM_ACCESS_TOKEN={new_token}\n")
                    found = True
                else:
                    lines.append(line)
        if not found:
            lines.append(f"INSTAGRAM_ACCESS_TOKEN={new_token}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)

        # Patch config module in-memory agar siklus posting berikutnya pakai token baru
        import config as _cfg
        _cfg.INSTAGRAM_ACCESS_TOKEN = new_token
        import uploader as _up
        _up.INSTAGRAM_ACCESS_TOKEN = new_token

        _notify_wa(
            f"✅ *Bantukos Bot*: Token Instagram berhasil di-refresh otomatis.\n"
            f"Berlaku {days_left} hari lagi.\n\n"
            f"Update juga di Coolify env agar permanen setelah redeploy.",
            key="token_refresh_ok"
        )
    except Exception as e:
        print(f"⚠️ Token refresh error: {e}")


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
            _notify_wa(
                f"🚨 *ALERT Bantukos Bot*\n\n"
                f"Token Instagram akan expired dalam *{days_left} hari* ({expires_str})!\n\n"
                f"Segera generate token baru:\n"
                f"developers.facebook.com/tools/explorer\n\n"
                f"Kirim token baru ke admin untuk di-update.",
                key="token_expiry_critical"
            )
        elif days_left <= 20:
            print(f"⚠️  Token Instagram akan expired dalam {days_left} hari ({expires_str}). Segera renew!")
            _notify_wa(
                f"⚠️ *Bantukos Bot*: Token Instagram akan expired dalam {days_left} hari ({expires_str}). Segera renew!",
                key="token_expiry_warning"
            )
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


def run_scraping(facebook_only: bool = False, groups: list = None):
    """
    Jalankan scraping + generate caption.
    facebook_only=True untuk skip Mamikos.
    groups: subset grup FB untuk run ini (rotasi). None = semua grup.
    """
    print("\n" + "="*50)
    print("🔄 SIKLUS SCRAPING DIMULAI")
    print("="*50)
    scrape_groups(groups=groups)
    if not facebook_only:
        scrape_mamikos()
    process_new_posts()
    get_stats()
    _batch_upload_cloudinary(max_posts=30)


def _bali_now() -> datetime.datetime:
    """Waktu sekarang di zona Bali (WITA, UTC+8)."""
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)


def _is_scrape_active_hours() -> bool:
    """True kalau sekarang dalam jam aktif scraping (waktu Bali). Malam = bot diam."""
    return SCRAPE_ACTIVE_HOUR_START <= _bali_now().hour < SCRAPE_ACTIVE_HOUR_END


def _next_scrape_interval_minutes() -> int:
    """Interval acak sampai siklus scraping berikutnya — hindari pola tetap."""
    return random.randint(SCRAPE_INTERVAL_MIN_MINUTES, SCRAPE_INTERVAL_MAX_MINUTES)

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
    import sqlite3 as _sqlite3
    post_id          = post[0]
    location         = _clean_location(post[3] or "")
    price            = post[4]
    image_paths_str  = post[6]
    caption          = post[7]
    source           = post[11] if len(post) > 11 else "facebook"
    cloudinary_saved = post[12] if len(post) > 12 else ""

    if not caption:
        print("⚠️ Caption kosong, skip.")
        return False

    # ── Cek apakah sudah punya cloudinary_urls tersimpan ─────────────────
    # Jika sudah ada, pakai langsung tanpa upload ulang ke Cloudinary
    existing_cdn = [u.strip() for u in (cloudinary_saved or "").split(",") if u.strip().startswith("http")]
    if existing_cdn:
        print(f"   ♻️ Pakai {len(existing_cdn)} cloudinary URL yang sudah ada")
        caption_with_id = caption + f"\n\n📋 ID: BK-{post_id}"
        return post_to_instagram(post_id, existing_cdn, caption_with_id)

    # ── Siapkan foto dari lokal ───────────────────────────────────────────
    # dict.fromkeys: deduplikasi sambil jaga urutan
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
            image_paths = [card_path] + image_paths
            print(f"   🃏 Info card dibuat: {os.path.basename(card_path)}")

    # ── Tidak ada foto sama sekali → skip, jangan pakai template ─────────
    if not image_paths:
        print(f"   ⏭️ Post BK-{post_id} tidak punya foto — skip (tidak akan pakai template).")
        conn = _sqlite3.connect(os.path.join("data", "bantukos.db"))
        conn.execute("UPDATE posts SET status='skipped' WHERE id=?", (post_id,))
        conn.commit()
        conn.close()
        return False

    # Upload ke Cloudinary
    import hashlib as _hashlib
    public_urls = []
    seen_upload_hashes = set()
    print(f"☁️ Upload {min(len(image_paths), 5)} foto ke Cloudinary...")
    for path in image_paths[:5]:
        if "card_" in path:
            target = path
        else:
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

    if not public_urls:
        print(f"   ⏭️ Post BK-{post_id} gagal upload semua foto ke Cloudinary — skip.")
        return False

    caption_with_id = caption + f"\n\n📋 ID: BK-{post_id}"
    result = post_to_instagram(post_id, public_urls, caption_with_id)
    if result is True:
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
    init_outreach_db()
    src_label = "Facebook saja" if facebook_only else "Facebook + Mamikos"
    print("\n🤖 Bantu Kos Bot dimulai!")
    print(f"   Sumber scraping  : {src_label}")
    print(f"   Scraping setiap  : {SCRAPE_INTERVAL_MIN_MINUTES}-{SCRAPE_INTERVAL_MAX_MINUTES} menit (acak)")
    print(f"   Jam aktif        : {SCRAPE_ACTIVE_HOUR_START}:00-{SCRAPE_ACTIVE_HOUR_END}:00 WITA")
    print(f"   Grup per siklus  : {SCRAPE_GROUPS_PER_RUN} grup (rotasi)")
    print(f"   Posting setiap   : {POST_INTERVAL_HOURS} jam ({MAX_POSTS_PER_RUN} post terbaik/siklus)")
    print(f"   Outreach setiap  : 15 menit")
    print("   Prioritas upload : Foto > Lokasi detail > No HP > Harga > Teks")
    print("   Tekan Ctrl+C untuk berhenti\n")
    _check_token_expiry()

    def _scrape():
        batch = get_rotation_batch(SCRAPE_GROUPS_PER_RUN)
        names = [g.rstrip("/").split("/")[-1] for g in batch]
        print(f"🔁 Rotasi grup run ini ({len(batch)}): {', '.join(names)}")
        run_scraping(facebook_only=facebook_only, groups=batch)

    _post = lambda: run_posting(max_posts=MAX_POSTS_PER_RUN, source="facebook" if facebook_only else None)

    # Lock agar tidak ada 2 outreach berjalan bersamaan
    _outreach_lock = threading.Lock()

    def _run_outreach_safe():
        if _outreach_lock.acquire(blocking=False):
            try:
                run_outreach()
            finally:
                _outreach_lock.release()
        else:
            print("⏭️ Outreach masih berjalan, skip siklus ini.")

    # Posting/outreach/token tetap pakai schedule (jadwal tetap aman).
    # Scraping TIDAK pakai schedule — dikelola manual agar bisa jam aktif,
    # interval acak, dan sesekali skip (semua untuk meredam pola robot).
    schedule.every(POST_INTERVAL_HOURS).hours.do(_post)
    schedule.every(15).minutes.do(_run_outreach_safe)
    schedule.every(7).days.do(_refresh_ig_token)

    # Startup: outreach paralel (tidak saling tunggu)
    threading.Thread(target=_run_outreach_safe, daemon=True).start()
    _post()

    next_scrape_at = time.time()  # coba scrape segera setelah startup (kalau jam aktif)

    while True:
        schedule.run_pending()

        if time.time() >= next_scrape_at:
            if not _is_scrape_active_hours():
                jam = _bali_now().strftime("%H:%M")
                print(f"🌙 {jam} WITA — di luar jam aktif "
                      f"({SCRAPE_ACTIVE_HOUR_START}:00-{SCRAPE_ACTIVE_HOUR_END}:00), scraping ditunda.")
                next_scrape_at = time.time() + 20 * 60   # cek lagi 20 menit
            elif random.random() < SCRAPE_SKIP_CHANCE:
                skip_min = _next_scrape_interval_minutes()
                print(f"🎲 Sengaja lewati siklus scraping ini (irregularitas manusia). "
                      f"Lanjut ~{skip_min} menit lagi.")
                next_scrape_at = time.time() + skip_min * 60
            else:
                _scrape()
                wait_min = _next_scrape_interval_minutes()
                next_scrape_at = time.time() + wait_min * 60
                jam = _bali_now().strftime("%H:%M")
                print(f"⏰ Scraping berikutnya ~{wait_min} menit lagi (sekarang {jam} WITA).")

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
