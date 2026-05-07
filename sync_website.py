"""
Sync listings dari bantukos.db ke website bantukos.com via GitHub API.

Cara kerja:
  1. Baca posts dari bantukos.db
  2. Generate listings.json yang sudah dibersihkan
  3. Push ke GitHub repo SupportKos via API → trigger GitHub Actions → deploy ke cPanel

Env vars yang dibutuhkan di .env:
  GITHUB_TOKEN       = Personal Access Token (repo scope)
  GITHUB_REPO        = yugakurniawan-git/kost.yugakurniawan.com
  GITHUB_BRANCH      = main
  BANTUKOS_DB_PATH   = data/bantukos.db
"""
import os
import re
import json
import base64
import sqlite3
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN     = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO      = os.getenv("GITHUB_REPO", "yugakurniawan-git/kost.yugakurniawan.com")
GITHUB_BRANCH    = os.getenv("GITHUB_BRANCH", "main")
BANTUKOS_DB_PATH = os.getenv("BANTUKOS_DB_PATH", "data/bantukos.db")
LISTINGS_FILE    = "public/listings.json"

SEEKING_KW = [
    "cari kos", "nyari kos", "butuh kos", "info kosan dong",
    "looking for", "mau cari", "lagi cari", "mencari kos",
]


def clean_location(loc: str) -> str:
    if not loc:
        return "Bali"
    loc = re.sub(r"[^\x00-\x7FÀ-ɏĀ-ſ]+", "", loc).strip()
    areas = [
        "Canggu", "Seminyak", "Kuta", "Ubud", "Sanur", "Jimbaran", "Nusa Dua",
        "Sesetan", "Renon", "Kerobokan", "Pemogan", "Padangsambian", "Mengwi",
        "Gatsu", "Denpasar", "Tabanan", "Gianyar", "Berawa", "Legian", "Pererenan",
    ]
    for a in areas:
        if a.lower() in loc.lower():
            return a
    parts = loc.split(",")
    return parts[0].strip()[:30] if parts else "Bali"


def normalize_price(price: str):
    if not price:
        return None
    p = price.strip()
    if "\n" in p or p in ("Hubungi pemilik", "N/A", ""):
        return None
    # Mamikos format already clean
    if p.startswith("Rp ") and "/bulan" in p:
        return p.replace("/bulan", "/bln")
    p_lower = p.lower().replace(" ", "")
    m = re.search(r"[\d,\.]+", p_lower)
    if not m:
        return None
    try:
        num = float(m.group().replace(",", "."))
    except ValueError:
        return None
    suffix = p_lower[m.end():]
    if "jt" in suffix or "juta" in suffix:
        amt = int(num * 1_000_000)
    elif "rb" in suffix or "ribu" in suffix or "k" in suffix:
        amt = int(num * 1_000)
    else:
        amt = int(num * 1_000_000) if num < 10 else int(num * 1_000) if num < 10_000 else int(num)
    if amt < 100_000 or amt > 20_000_000:
        return None
    if amt >= 1_000_000:
        label = f"{amt/1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"Rp {label}jt/bln"
    return f"Rp {amt // 1000}rb/bln"


def parse_facilities(raw: str) -> list:
    text = (raw or "").lower()
    checks = [
        ("ac", "AC"), ("wifi", "WiFi"), ("kamar mandi dalam", "KM Dalam"),
        ("furnished", "Furnished"), ("parkir", "Parkir"), ("dapur", "Dapur"),
        ("air panas", "Air Panas"), ("kasur", "Kasur"), ("kulkas", "Kulkas"),
    ]
    return [v for k, v in checks if k in text][:5]


def get_kos_type(raw: str) -> str:
    t = (raw or "").lower()
    if "studio" in t:    return "Studio"
    if "kontrakan" in t: return "Kontrakan"
    if "putri" in t or "wanita" in t: return "Putri"
    if "putra" in t or "pria" in t:   return "Putra"
    if "campur" in t:    return "Campur"
    return "Kos"


def build_listings() -> list:
    if not os.path.exists(BANTUKOS_DB_PATH):
        print(f"❌ DB tidak ditemukan: {BANTUKOS_DB_PATH}")
        return []

    conn = sqlite3.connect(BANTUKOS_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # cloudinary_urls mungkin belum ada di DB lama — pakai COALESCE
    c.execute("""
        SELECT id, location, price, raw_text, source, created_at,
               COALESCE(cloudinary_urls, '') as cloudinary_urls
        FROM posts
        WHERE status = 'posted'
        ORDER BY created_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    listings = []
    seen = set()  # deduplikasi by (location, price)

    for r in rows:
        raw = r["raw_text"] or ""
        if any(kw in raw.lower() for kw in SEEKING_KW):
            continue
        price = normalize_price(r["price"])
        if not price:
            continue

        loc = clean_location(r["location"])
        dedup_key = (loc.lower(), price.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Ambil foto pertama dari Cloudinary URLs
        cdn_urls = [u for u in (r["cloudinary_urls"] or "").split(",") if u.strip()]
        image_url = cdn_urls[0] if cdn_urls else ""

        listings.append({
            "id": r["id"],
            "location": loc,
            "price": price,
            "type": get_kos_type(raw),
            "facilities": parse_facilities(raw),
            "source": r["source"] or "facebook",
            "posted_at": (r["created_at"] or "")[:10],
            "image_url": image_url,
        })
    return listings


def push_to_github(listings: list) -> bool:
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN belum diisi di .env")
        return False

    content = json.dumps(listings, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content.encode()).decode()

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{LISTINGS_FILE}"

    # Get current file SHA (required for update)
    resp = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
    sha = resp.json().get("sha") if resp.status_code == 200 else None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    payload = {
        "message": f"chore: update listings.json ({len(listings)} listing) — {now}",
        "content": content_b64,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print(f"✅ {len(listings)} listing di-push ke GitHub → deploy otomatis")
        return True
    else:
        print(f"❌ GitHub API error {resp.status_code}: {resp.json().get('message')}")
        return False


if __name__ == "__main__":
    print("🌐 Sync listings ke website bantukos.com...")
    listings = build_listings()
    if not listings:
        print("⚠️ Tidak ada listing yang valid, skip push.")
    else:
        print(f"   {len(listings)} listing valid ditemukan")
        push_to_github(listings)
