"""
Scraper untuk Mamikos.com — listing kos di Bali.

Strategi:
1. Navigate ke halaman search Mamikos per area (Playwright headless)
2. Extract data dari __NEXT_DATA__ script tag (Next.js SSR — 100% reliable)
3. Scroll & klik pagination untuk load lebih banyak
4. Untuk tiap listing, buka detail page dan ambil foto + fasilitas
5. Simpan ke database yang sama dengan Facebook scraper
"""

import re
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

# ─── Konfigurasi Area ──────────────────────────────────

# Tambah/hapus area sesuai kebutuhan
MAMIKOS_AREAS = [
    ("Denpasar",  "https://mamikos.com/cari/denpasar--bali--indonesia"),
    ("Canggu",    "https://mamikos.com/cari/canggu--kuta-utara--badung--bali--indonesia"),
    ("Seminyak",  "https://mamikos.com/cari/seminyak--kuta--badung--bali--indonesia"),
    ("Kuta",      "https://mamikos.com/cari/kuta--badung--bali--indonesia"),
    ("Ubud",      "https://mamikos.com/cari/ubud--gianyar--bali--indonesia"),
    ("Sanur",     "https://mamikos.com/cari/sanur--denpasar-selatan--denpasar--bali--indonesia"),
    ("Jimbaran",  "https://mamikos.com/cari/jimbaran--kuta-selatan--badung--bali--indonesia"),
]

MAX_PER_AREA      = 8    # max listing per area per run
MAX_TOTAL         = 30   # max total per cycle
HEADLESS          = True # False = bisa lihat browser


# ─── Helpers ──────────────────────────────────────────

def _safe_json(text: str):
    """Parse JSON, return None kalau gagal."""
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_next_data(page) -> dict:
    """
    Ambil data dari __NEXT_DATA__ script tag — Next.js menyimpan
    seluruh page props di sini, termasuk daftar listing.
    """
    content = page.evaluate("""
        () => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? el.textContent : '';
        }
    """)
    if not content:
        return {}
    return _safe_json(content) or {}


def _find_listings_in_props(data: dict) -> list:
    """
    Cari daftar listing dari props Next.js.
    Mamikos biasanya menyimpan di: props.pageProps.rooms / .data.rooms / .kos
    Fungsi ini mencari secara rekursif.
    """
    if not isinstance(data, dict):
        return []

    # Kunci yang biasanya berisi list kos
    for key in ("rooms", "kos", "listings", "data", "result", "items"):
        val = data.get(key)
        if isinstance(val, list) and len(val) > 0:
            # Verifikasi ini memang list listing (punya field harga/nama)
            if any(isinstance(v, dict) and
                   any(k in v for k in ("price", "name", "room_name", "monthly_price"))
                   for v in val[:3]):
                return val
        if isinstance(val, dict):
            found = _find_listings_in_props(val)
            if found:
                return found

    # Coba 1 level lebih dalam
    for v in data.values():
        if isinstance(v, dict):
            found = _find_listings_in_props(v)
            if found:
                return found

    return []


def _extract_listing_urls_from_dom(page) -> list:
    """
    Fallback: ambil URL listing dari link di halaman.
    Mamikos detail page ada di /detail/...
    """
    urls = page.evaluate("""
        () => {
            const seen = new Set();
            const links = document.querySelectorAll('a[href*="/detail/"]');
            return Array.from(links)
                .map(a => a.href)
                .filter(h => h.includes('/detail/') && !seen.has(h) && seen.add(h))
                .slice(0, 30);
        }
    """)
    return urls or []


def _download_image(session: requests.Session, url: str, filepath: str) -> bool:
    """Download gambar pakai requests (tidak perlu browser session)."""
    try:
        r = session.get(url, timeout=15, stream=True)
        if r.status_code == 200 and len(r.content) > 5000:
            with open(filepath, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"      ⚠️ Download gagal: {e}")
    return False


def _parse_listing_detail(page, url: str, session: requests.Session):
    """
    Buka halaman detail listing, extract semua data.
    Return dict atau None kalau gagal.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(random.uniform(2, 3.5))
    except Exception as e:
        print(f"      ⚠️ Gagal buka {url[-40:]}: {e}")
        return None

    # ── Ambil dari __NEXT_DATA__ ──────────────────────────────────────────────
    nd = _extract_next_data(page)
    props = nd.get("props", {}).get("pageProps", {})

    # Cari data listing dari berbagai kunci
    listing = None
    for key in ("room", "kos", "detail", "data"):
        val = props.get(key)
        if isinstance(val, dict) and val:
            listing = val
            break

    # ── Fallback: cari dari semua props ──────────────────────────────────────
    if not listing:
        listing = props  # gunakan seluruh pageProps

    # ── Extract fields ────────────────────────────────────────────────────────
    def _get(*keys, default=""):
        """Cari nilai dari nested dict dengan beberapa kemungkinan kunci."""
        for k in keys:
            val = listing.get(k) if listing else None
            if val is not None and val != "":
                return val
        return default

    name     = _get("name", "room_name", "kos_name", "title", default="Kos di Bali")
    price    = _get("price", "monthly_price", "price_per_month", default=0)
    location = _get("address", "location", "full_address", "city", default="Bali")
    area     = _get("area", "district", "sub_district", default="")
    city     = _get("city", "regency", default="")
    desc     = _get("description", "detail_description", "info", default="")
    facilities_raw = _get("facilities", "facility", "fasilitas", default=[])

    # Format harga ke string
    if isinstance(price, (int, float)) and price > 0:
        price_str = f"Rp {int(price):,}".replace(",", ".")
    elif isinstance(price, str) and price:
        price_str = price
    else:
        price_str = "Hubungi pemilik"

    # Format lokasi
    parts = [p for p in [area, city, "Bali"] if p and p not in location]
    location_str = location + (", " + ", ".join(parts) if parts else "")

    # Fasilitas jadi string
    if isinstance(facilities_raw, list):
        facility_names = []
        for f in facilities_raw[:10]:
            if isinstance(f, str):
                facility_names.append(f)
            elif isinstance(f, dict):
                facility_names.append(f.get("name", f.get("facility_name", "")))
        facilities_str = ", ".join(x for x in facility_names if x)
    else:
        facilities_str = str(facilities_raw)

    # ── Susun teks raw (untuk DB & caption AI) ────────────────────────────────
    raw_text_parts = [name]
    if location_str:
        raw_text_parts.append(f"Lokasi: {location_str}")
    if price_str:
        raw_text_parts.append(f"Harga: {price_str}/bulan")
    if facilities_str:
        raw_text_parts.append(f"Fasilitas: {facilities_str}")
    if desc:
        raw_text_parts.append(desc[:500])
    raw_text_parts.append(f"Sumber: Mamikos | {url}")
    raw_text = "\n".join(raw_text_parts)

    # ── Ambil URL foto ─────────────────────────────────────────────────────────
    photo_urls = []
    # Cari di __NEXT_DATA__ dulu
    images_raw = (_get("images", "photos", "image", "gallery", default=[])
                  or listing.get("room_images", [])
                  or listing.get("kos_images", []))
    if isinstance(images_raw, list):
        for img in images_raw[:8]:
            if isinstance(img, str) and img.startswith("http"):
                photo_urls.append(img)
            elif isinstance(img, dict):
                u = img.get("url", img.get("image_url", img.get("path", "")))
                if u and u.startswith("http"):
                    photo_urls.append(u)

    # Fallback: cari dari DOM
    if not photo_urls:
        photo_urls = page.evaluate("""
            () => {
                const imgs = document.querySelectorAll(
                    'img[src*="mamikos"], img[src*="cloudinary"], img[src*="amazonaws"]'
                );
                const seen = new Set();
                return Array.from(imgs)
                    .map(i => i.src || i.getAttribute('data-src') || '')
                    .filter(s => s.startsWith('http') && !seen.has(s) && seen.add(s)
                            && !s.includes('avatar') && !s.includes('icon'))
                    .slice(0, 6);
            }
        """) or []

    print(f"      📋 {name[:50]} | {price_str} | {len(photo_urls)} foto")
    return {
        "url":       url,
        "raw_text":  raw_text,
        "location":  location_str[:100],
        "price":     price_str,
        "contact":   "",           # Mamikos sembunyikan kontak
        "photo_urls": photo_urls,
    }


def _download_listing_photos(session, photo_urls, post_id, max_photos=5):
    """Download foto listing ke lokal."""
    saved = []
    for i, url in enumerate(photo_urls[:max_photos]):
        name = f"mami_{hashlib.md5(post_id.encode()).hexdigest()[:8]}_{i}.jpg"
        path = os.path.join(IMAGES_DIR, name)
        if _download_image(session, url, path):
            saved.append(path)
            size_kb = os.path.getsize(path) // 1024
            print(f"      📷 Foto {i+1} OK ({size_kb}KB): {name}")
    return saved


# ─── Main Scraper ──────────────────────────────────────

def scrape_mamikos():
    print("\n🏠 Mulai scraping Mamikos.com...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
    })

    total_new = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox"],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
            locale="id-ID",
        )
        page = ctx.new_page()

        for area_name, search_url in MAMIKOS_AREAS:
            if total_new >= MAX_TOTAL:
                break

            print(f"\n📍 Area: {area_name}")
            print(f"   URL: {search_url}")

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(3, 5))

                # Scroll sedikit untuk trigger lazy-load
                for _ in range(5):
                    page.evaluate("window.scrollBy(0, 500)")
                    time.sleep(0.8)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(1)

                # ── Coba ambil listing URLs dari __NEXT_DATA__ ────────────────
                nd = _extract_next_data(page)
                listing_urls = []

                props = nd.get("props", {}).get("pageProps", {})
                listings_data = _find_listings_in_props(props)

                if listings_data:
                    print(f"   ✅ __NEXT_DATA__: {len(listings_data)} listing ditemukan")
                    # Bangun URL detail dari slug/id
                    for item in listings_data:
                        slug = item.get("slug", item.get("room_slug", item.get("id", "")))
                        if slug:
                            listing_urls.append(f"https://mamikos.com/detail/{slug}")
                else:
                    print("   ⚠️ Tidak ada listing di __NEXT_DATA__, coba DOM...")

                # ── Fallback: ambil dari DOM links ────────────────────────────
                if not listing_urls:
                    listing_urls = _extract_listing_urls_from_dom(page)
                    print(f"   DOM links: {len(listing_urls)} URL ditemukan")

                if not listing_urls:
                    print(f"   ⚠️ Tidak ada listing URL ditemukan untuk {area_name}")
                    page.screenshot(path=f"data/debug_mamikos_{area_name}.png")
                    continue

                print(f"   🔗 {len(listing_urls)} listing URL, proses max {MAX_PER_AREA}")
                area_new = 0

                for listing_url in listing_urls[:MAX_PER_AREA]:
                    if area_new >= MAX_PER_AREA or total_new >= MAX_TOTAL:
                        break

                    # Dedup berdasarkan URL
                    url_id = hashlib.md5(listing_url.encode()).hexdigest()
                    if is_duplicate(url_id):
                        print(f"   ⏭️ Duplikat: {listing_url[-40:]}")
                        continue

                    detail = _parse_listing_detail(page, listing_url, session)
                    if not detail:
                        continue

                    # Download foto
                    img_paths = _download_listing_photos(
                        session, detail["photo_urls"], url_id
                    )

                    # Simpan ke DB (pakai URL hash sebagai post_id)
                    saved_id = save_post(
                        url_id,
                        detail["raw_text"][:2000],
                        detail["location"],
                        detail["price"],
                        detail["contact"],
                        img_paths,
                    )
                    if saved_id:
                        area_new  += 1
                        total_new += 1
                        print(f"   ✅ Tersimpan ID {saved_id} | "
                              f"{detail['location'][:20]} | {detail['price']} | "
                              f"{len(img_paths)} foto")

                    # Jeda sopan antar request
                    time.sleep(random.uniform(2, 4))

                print(f"   📊 {area_name}: {area_new} listing baru")

            except Exception as e:
                print(f"   ❌ Error area {area_name}: {e}")
                import traceback; traceback.print_exc()
                continue

            # Jeda antar area
            if total_new < MAX_TOTAL:
                wait = random.randint(5, 12)
                print(f"   ⏳ Jeda {wait}s sebelum area berikutnya...")
                time.sleep(wait)

        ctx.close()
        browser.close()

    print(f"\n✅ Mamikos selesai. Total baru: {total_new} listing")
    return total_new


if __name__ == "__main__":
    scrape_mamikos()
