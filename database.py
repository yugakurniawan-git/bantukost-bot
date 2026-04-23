import sqlite3
from config import DB_PATH

def init_db():
    """Buat tabel kalau belum ada."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_post_id      TEXT UNIQUE,         -- ID unik postingan FB (cegah duplikat)
            raw_text        TEXT,                -- Teks asli dari FB
            location        TEXT,                -- Lokasi hasil extract
            price           TEXT,                -- Harga hasil extract
            contact         TEXT,                -- Nomor kontak
            image_paths     TEXT,                -- Path foto (dipisah koma)
            caption         TEXT,                -- Caption yang sudah di-generate AI
            status          TEXT DEFAULT 'new',  -- new | captioned | posted | skipped
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at       TIMESTAMP
        )
    """)
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

def save_post(fb_post_id, raw_text, location, price, contact, image_paths):
    """Simpan postingan baru ke database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO posts (fb_post_id, raw_text, location, price, contact, image_paths)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fb_post_id, raw_text, location, price, contact, ",".join(image_paths)))
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

def mark_posted(post_id: int):
    """Tandai postingan sudah di-upload ke Instagram."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE posts SET status = 'posted', posted_at = CURRENT_TIMESTAMP WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

def get_pending_posts():
    """Ambil postingan yang sudah ada caption tapi belum diposting."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE status = 'captioned' ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
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
