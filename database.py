import sqlite3
import re
import os
from config import DB_PATH


def score_post(post) -> int:
    """
    Skor kualitas post untuk menentukan urutan prioritas upload.

    Prioritas (dari tertinggi):
      1. Foto          — max 80 poin
      2. Lokasi detail — max 30 poin  (sampai no rumah / gang / RT)
      3. No HP         — 25 poin
      4. Harga jelas   — 15 poin
      5. Teks detail   — max 10 poin
    """
    raw_text    = post[2] or ""
    location    = post[3] or ""
    price       = post[4] or ""
    contact     = post[5] or ""
    image_paths = post[6] or ""

    score = 0

    # ── 1. Foto ──────────────────────────────────────── max 80 poin ─────
    photos = [p for p in image_paths.split(",")
              if p.strip() and os.path.exists(p.strip())]
    if photos:
        score += 60
        score += min(len(photos) - 1, 4) * 5   # +5 per foto tambahan, max +20

    # ── 2. Lokasi detail ─────────────────────────────── max 30 poin ─────
    loc_combined = f"{location} {raw_text}".lower()
    if re.search(r'\b(?:jl\.?|jalan|gang|gg\.?|blok|no\.?\s*\d|nomor\s*\d|rt\s*\d|rw\s*\d)', loc_combined):
        score += 30           # ada alamat lengkap (jalan/gang/nomor)
    elif "," in location:
        score += 20           # "Sesetan, Denpasar Selatan" — sub-area + area
    elif location and location.lower() not in ("bali", ""):
        score += 10           # minimal ada nama area spesifik

    # ── 3. No HP ─────────────────────────────────────── 25 poin ─────────
    if re.search(r'(?:08|62|\+62)\d{7,}', f"{contact} {raw_text}"):
        score += 25

    # ── 4. Harga jelas ───────────────────────────────── 15 poin ─────────
    if price and price.strip().lower() not in ("hubungi pemilik", ""):
        score += 15

    # ── 5. Teks detail ───────────────────────────────── max 10 poin ─────
    tlen = len(raw_text)
    if tlen > 300:
        score += 10
    elif tlen > 150:
        score += 6
    elif tlen > 80:
        score += 3

    return score

def init_db():
    """Buat tabel kalau belum ada, dan migrate kalau perlu."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_post_id      TEXT UNIQUE,
            raw_text        TEXT,
            location        TEXT,
            price           TEXT,
            contact         TEXT,
            image_paths     TEXT,
            caption         TEXT,
            status          TEXT DEFAULT 'new',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at       TIMESTAMP,
            source          TEXT DEFAULT 'facebook'
        )
    """)
    for col, definition in [
        ("source", "TEXT DEFAULT 'facebook'"),
        ("cloudinary_urls", "TEXT DEFAULT ''"),
    ]:
        try:
            c.execute(f"ALTER TABLE posts ADD COLUMN {col} {definition}")
            conn.commit()
            print(f"🔄 Migrasi DB: kolom '{col}' ditambahkan.")
        except Exception:
            pass
    conn.commit()
    conn.close()
    print("✅ Database siap.")

def is_duplicate(fb_post_id: str) -> bool:
    """Cek apakah postingan sudah pernah diproses."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM posts WHERE fb_post_id = ?", (fb_post_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def save_post(fb_post_id, raw_text, location, price, contact, image_paths,
              source: str = "facebook"):
    """Simpan postingan baru ke database. source: 'facebook' atau 'mamikos'."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO posts (fb_post_id, raw_text, location, price, contact, image_paths, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (fb_post_id, raw_text, location, price, contact,
              ",".join(image_paths), source))
        conn.commit()
        post_id = c.lastrowid
        print(f"💾 Tersimpan: {fb_post_id[:20]}...")
        return post_id
    except sqlite3.IntegrityError:
        print(f"⚠️ Duplikat, skip: {fb_post_id[:20]}...")
        return None
    finally:
        conn.close()

def update_caption(post_id: int, caption: str):
    """Update caption setelah di-generate AI."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE posts SET caption = ?, status = 'captioned' WHERE id = ?", (caption, post_id))
    conn.commit()
    conn.close()

def save_cloudinary_urls(post_id: int, urls: list):
    """Simpan Cloudinary URLs setelah berhasil upload."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE posts SET cloudinary_urls = ? WHERE id = ?",
              (",".join(urls), post_id))
    conn.commit()
    conn.close()


def mark_posted(post_id: int):
    """Tandai postingan sudah di-upload ke Instagram."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE posts SET status = 'posted', posted_at = CURRENT_TIMESTAMP WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

def get_pending_posts(source: str = None):
    """
    Ambil postingan yang sudah ada caption tapi belum diposting.
    source: 'facebook' | 'mamikos' | None (semua)
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if source:
        c.execute("""
            SELECT id, fb_post_id, raw_text, location, price, contact,
                   image_paths, caption, status, created_at, posted_at,
                   COALESCE(source, 'facebook') as source
            FROM posts WHERE status = 'captioned'
              AND COALESCE(source, 'facebook') = ?
            ORDER BY created_at ASC
        """, (source,))
    else:
        c.execute("""
            SELECT id, fb_post_id, raw_text, location, price, contact,
                   image_paths, caption, status, created_at, posted_at,
                   COALESCE(source, 'facebook') as source
            FROM posts WHERE status = 'captioned' ORDER BY created_at ASC
        """)
    rows = c.fetchall()
    conn.close()
    # Urutkan berdasarkan skor kualitas — terbaik duluan
    rows.sort(key=score_post, reverse=True)
    return rows

def get_stats():
    """Tampilkan statistik singkat."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) FROM posts GROUP BY status")
    stats = dict(c.fetchall())
    conn.close()
    print("\n📊 Statistik Database:")
    print(f"   Baru      : {stats.get('new', 0)}")
    print(f"   Siap post : {stats.get('captioned', 0)}")
    print(f"   Sudah post: {stats.get('posted', 0)}")
    print(f"   Di-skip   : {stats.get('skipped', 0)}\n")
