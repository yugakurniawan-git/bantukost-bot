"""
Scraper untuk Mamikos.com — listing kos di Bali.

Strategi (reverse-engineered dari browser):
1. Navigate ke https://mamikos.com/kos/andalan/bali
   → Browser otomatis call garuda/sanjunipero/list?slug=%2Fkos%2Fandalan%2Fbali&child_id=279
   → API mengembalikan ±20 kos di Bali (Kota Denpasar + Kabupaten Badung)
2. Dari tiap room, gunakan `_id` untuk call garuda/stories/{_id}/gallery
   → API mengembalikan semua foto dalam beberapa kategori (bangunan, kamar, dll.)
3. Semua data (nama, harga, fasilitas, lokasi) sudah ada di listing API
   → Tidak perlu visit detail page
4. Simpan ke database yang sama dengan Facebook scraper
"""

import os
import json
import time
import random
import hashlib
import requests
from playwright.sync_api import sync_playwright
from config import IMAGES_DIR
from database import is_duplicate, save_post

os.makedirs(IMAGES_DIR, exist_ok=True)

# ─── Konfigurasi ───────────────────────────────────────────────────────────────

# Halaman Mamikos yang mengembalikan kos Bali via sanjunipero/list API.
# URL ini valid dan ter-verified mengembalikan Kota Denpasar + Kabupaten Badung.
MAMIKOS_BALI_URL = "https://mamikos.com/kos/andalan/bali"

MAX_ROOMS     = 20   # max rooms per siklus (API hanya return ~20 rooms dari halaman ini)
MAX_TOTAL     = 20   # max total per cycle
MAX_PHOTOS    = 5    # max foto per listing
HEADLESS      = True


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _download_image(session: requests.Session, url: str, filepath: str) -> bool:
    """Download gambar ke disk."""
    try:
        r = session.get(url, timeout=15, stream=True)
        if r.status_code == 200 and len(r.content) > 4000:
            with open(filepath, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"      ⚠️ Download gagal: {e}")
    return False


def _format_price(room: dict) -> str:
    """
    Ambil harga dari room dict.
    Coba price_title_format dulu, lalu price_title, lalu price.
    """
    fmt = room.get("price_title_format")
    if isinstance(fmt, dict):
        symbol = fmt.get("currency_symbol", "Rp")
        price  = fmt.get("price", "")
        unit   = fmt.get("rent_type_unit", "bulan")
        if price:
            return f"{symbol} {price}/{unit}"

    pt = room.get("price_title", "")
    if pt:
        return f"Rp {pt}/bulan"

    p = room.get("price", 0)
    if isinstance(p, (int, float)) and p > 0:
        return f"Rp {int(p):,}".replace(",", ".")

    return "Hubungi pemilik"


def _get_gallery_photos(page, room_id: int) -> list:
    """
    Panggil garuda/stories/{room_id}/gallery via page.evaluate (pakai session browser).
    Return list URL foto (large size, 540x720).
    """
    try:
        result = page.evaluate(f"""
            async () => {{
                const r = await fetch('/garuda/stories/{room_id}/gallery', {{
                    headers: {{
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json'
                    }}
                }});
                if (!r.ok) return null;
                return await r.json();
            }}
        """)
        if not result or not result.get("status"):
            return []

        photos = []
        for category in result.get("data", []):
            for item in category.get("items", []):
                url_obj = item.get("url", {})
                # Gunakan large (540x720) untuk kualitas terbaik
                url = (url_obj.get("large") or
                       url_obj.get("medium") or
                       url_obj.get("small") or "")
                if url and url.startswith("http") and url not in photos:
                    photos.append(url)
        return photos[:10]  # max 10 foto dari gallery
    except Exception as e:
        print(f"      ⚠️ Gallery API error: {e}")
        return []


def _download_photos(session: requests.Session, photo_urls: list,
                     post_id: str) -> list:
    """Download foto ke lokal, return list path yang berhasil."""
    saved = []
    seen_hashes = set()  # deduplikasi by MD5 konten
    hash_prefix = hashlib.md5(post_id.encode()).hexdigest()[:8]
    for i, url in enumerate(photo_urls[:MAX_PHOTOS]):
        fname = f"mami_{hash_prefix}_{i}.jpg"
        fpath = os.path.join(IMAGES_DIR, fname)
        if _download_image(session, url, fpath):
            content_hash = hashlib.md5(open(fpath, "rb").read()).hexdigest()
            if content_hash in seen_hashes:
                os.remove(fpath)
                print(f"      ⚠️ Foto {i+1} duplikat (konten sama), skip.")
                continue
            seen_hashes.add(content_hash)
            saved.append(fpath)
            size_kb = os.path.getsize(fpath) // 1024
            print(f"      📷 Foto {i+1} OK ({size_kb} KB): {fname}")
    return saved


def _build_raw_text(room: dict, price_str: str, photo_count: int) -> str:
    """Susun raw_text dari data listing."""
    name         = room.get("room-title") or room.get("name") or "Kos di Bali"
    area_label   = room.get("area_label") or ""
    city         = room.get("city") or ""
    subdistrict  = room.get("subdistrict") or ""
    facilities   = room.get("top_facility") or []
    unit_type    = room.get("unit_type") or ""
    size         = room.get("size") or ""
    gender_map   = {0: "Campur", 1: "Putra", 2: "Putri"}
    gender       = gender_map.get(room.get("gender"), "")
    rating       = room.get("rating_string") or room.get("rating") or ""
    share_url    = room.get("share_url") or ""
    furnished    = room.get("furnished_status") or ""

    parts = [name]
    if unit_type:
        parts.append(f"Tipe: {unit_type}")
    if gender:
        parts.append(f"Kos {gender}")
    if area_label:
        parts.append(f"Lokasi: {area_label}")
    parts.append(f"Harga: {price_str}/bulan")
    if facilities:
        parts.append(f"Fasilitas: {', '.join(str(f) for f in facilities[:8])}")
    if size:
        parts.append(f"Ukuran: {size} m²")
    if furnished:
        parts.append(f"Furnished: {furnished}")
    if rating:
        parts.append(f"Rating: ⭐ {rating}")
    if photo_count:
        parts.append(f"Foto: {photo_count} foto")
    if share_url:
        parts.append(f"Sumber: Mamikos | {share_url}")

    return "\n".join(parts)


# ─── Main Scraper ──────────────────────────────────────────────────────────────

def scrape_mamikos():
    print("\n🏠 Mulai scraping Mamikos.com...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Referer": "https://mamikos.com",
    })

    total_new = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="id-ID",
        )
        page = ctx.new_page()

        # ── Intercept sanjunipero/list response ────────────────────────────
        intercepted_rooms = []

        def on_listing_response(resp):
            if "sanjunipero/list" in resp.url and resp.status == 200:
                try:
                    body = resp.json()
                    rooms = body.get("rooms") or []
                    intercepted_rooms.extend(rooms)
                    cities = set(r.get("city", "?")[:20] for r in rooms[:5])
                    print(f"   📡 API: {len(rooms)} rooms | cities: {cities}")
                except Exception as e:
                    print(f"   ⚠️ API parse error: {e}")

        page.on("response", on_listing_response)

        # ── Navigate ke halaman Bali ────────────────────────────────────────
        print(f"\n📍 Loading: {MAMIKOS_BALI_URL}")
        try:
            page.goto(MAMIKOS_BALI_URL, wait_until="networkidle", timeout=35000)
        except Exception as e:
            print(f"   ⚠️ Timeout/error saat navigate, coba lanjut: {e}")
        time.sleep(random.uniform(5, 8))

        # Scroll sedikit untuk memastikan API fire
        for _ in range(5):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(0.5)
        time.sleep(2)

        page.remove_listener("response", on_listing_response)

        if not intercepted_rooms:
            print("   ❌ Tidak ada room dari API. Coba fallback...")
            # Fallback: DOM links
            dom_links = page.evaluate("""
                () => Array.from(
                    document.querySelectorAll('a[href*="/room/"], a[href*="/kos/"]')
                ).map(a => a.href)
                .filter(h => h.includes('/room/') || h.includes('/kos/'))
                .slice(0, 20)
            """) or []
            print(f"   DOM fallback: {len(dom_links)} links")
            ctx.close()
            browser.close()
            print("⚠️ Tidak ada data dari Mamikos saat ini.")
            return 0

        print(f"   ✅ {len(intercepted_rooms)} rooms ter-intercept")

        # ── Proses tiap room ────────────────────────────────────────────────
        for room in intercepted_rooms[:MAX_ROOMS]:
            if total_new >= MAX_TOTAL:
                break

            room_id   = room.get("_id") or room.get("id")
            name      = room.get("room-title") or room.get("name") or "Kos di Bali"
            share_url = room.get("share_url") or ""
            area      = room.get("area_label") or room.get("city") or "Bali"

            if not room_id:
                print(f"   ⚠️ Skip: tidak ada ID untuk {name[:30]}")
                continue

            # Dedup berdasarkan room_id
            url_id = hashlib.md5(str(room_id).encode()).hexdigest()
            if is_duplicate(url_id):
                print(f"   ⏭️ Duplikat: {name[:40]}")
                continue

            price_str = _format_price(room)
            print(f"\n   🏠 {name[:50]}")
            print(f"      💰 {price_str} | 📍 {area[:40]}")

            # ── Ambil foto dari gallery API ───────────────────────────────
            photo_urls = _get_gallery_photos(page, room_id)
            print(f"      📸 Gallery: {len(photo_urls)} foto")

            # Fallback: thumbnail dari listing API
            if not photo_urls:
                thumb = room.get("photo_url", {})
                if isinstance(thumb, dict):
                    url = thumb.get("large") or thumb.get("medium") or thumb.get("small") or ""
                    if url:
                        photo_urls = [url]

            # ── Susun data ─────────────────────────────────────────────────
            raw_text = _build_raw_text(room, price_str, len(photo_urls))
            location = area[:100]

            # ── Download foto ──────────────────────────────────────────────
            img_paths = _download_photos(session, photo_urls, url_id)

            # ── Simpan ke DB ───────────────────────────────────────────────
            saved_id = save_post(
                url_id,
                raw_text[:2000],
                location,
                price_str,
                "",
                img_paths,
                source="mamikos",
            )
            if saved_id:
                total_new += 1
                print(f"      ✅ Tersimpan ID {saved_id} | {len(img_paths)} foto")

            # Jeda sopan
            time.sleep(random.uniform(1.5, 3))

        ctx.close()
        browser.close()

    print(f"\n✅ Mamikos selesai. Total baru: {total_new} listing")
    return total_new


# ─── Debug helper ──────────────────────────────────────────────────────────────

def debug_mamikos():
    """
    Jalankan untuk cek output API dan struktur data.
    python mamikos_scraper.py debug
    """
    import pprint

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Buka browser agar bisa lihat
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="id-ID",
        )
        page = ctx.new_page()
        rooms_captured = []

        def on_resp(resp):
            if "sanjunipero/list" in resp.url and resp.status == 200:
                try:
                    body = resp.json()
                    rooms = body.get("rooms") or []
                    rooms_captured.extend(rooms)
                    print(f"\n✅ API: {len(rooms)} rooms")
                    print(f"   URL: {resp.url[:120]}")
                    if rooms:
                        cities = set(r.get("city", "?") for r in rooms[:5])
                        print(f"   Cities: {cities}")
                except Exception as e:
                    print(f"   error: {e}")

        page.on("response", on_resp)

        print(f"🌐 {MAMIKOS_BALI_URL}")
        page.goto(MAMIKOS_BALI_URL, wait_until="networkidle", timeout=35000)
        time.sleep(8)

        if rooms_captured:
            r0 = rooms_captured[0]
            print(f"\n📋 Sample room:")
            pprint.pprint({
                k: v for k, v in r0.items()
                if k in ("_id", "room-title", "city", "area_label",
                         "price_title_format", "top_facility", "share_url",
                         "photo_url", "photo_count", "unit_type", "size",
                         "gender", "rating_string")
            }, indent=2)

            # Test gallery
            room_id = r0.get("_id")
            if room_id:
                photos = _get_gallery_photos(page, room_id)
                print(f"\n📷 Gallery photos ({len(photos)}): {photos[:3]}")

        os.makedirs("data", exist_ok=True)
        with open("data/mamikos_debug.json", "w") as f:
            json.dump(rooms_captured[:5], f, indent=2, ensure_ascii=False, default=str)
        print(f"\n💾 data/mamikos_debug.json")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        debug_mamikos()
    else:
        scrape_mamikos()
