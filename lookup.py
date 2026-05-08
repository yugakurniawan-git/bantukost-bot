"""
Tool untuk lookup info kos dari database — termasuk no telp pemilik.

Cara pakai:
  python3 lookup.py          → list semua post + no telp (yang ada)
  python3 lookup.py 34       → detail post ID 34
  python3 lookup.py cari kuta → cari post berdasarkan kata kunci lokasi
"""
import sys
import sqlite3
from config import DB_PATH


def _short(text, n=60):
    return (text or "")[:n] + ("…" if len(text or "") > n else "")


def list_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, location, price, contact, source, status, created_at
        FROM posts ORDER BY id DESC
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("Database kosong.")
        return

    print(f"\n{'ID':<5} {'Lokasi':<35} {'Harga':<20} {'No Telp':<18} {'Src':<9} {'Status'}")
    print("-" * 105)
    for pid, loc, price, contact, src, status, created in rows:
        has_contact = "✅ " + (contact or "")[:15] if contact else "—"
        print(f"{pid:<5} {_short(loc,33):<35} {_short(price,18):<20} {has_contact:<18} {(src or 'fb'):<9} {status}")

    total_with_contact = sum(1 for r in rows if r[3])
    print(f"\nTotal: {len(rows)} post, {total_with_contact} punya no telp\n")


def show_detail(post_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, location, price, contact, source, status, raw_text, caption, created_at,
               COALESCE(source_url, '') as source_url
        FROM posts WHERE id = ?
    """, (post_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        print(f"Post ID {post_id} tidak ditemukan.")
        return

    pid, loc, price, contact, src, status, raw_text, caption, created, source_url = row

    print(f"\n{'='*50}")
    print(f"POST ID   : {pid}")
    print(f"Sumber    : {src or 'facebook'}")
    print(f"Status    : {status}")
    print(f"Tanggal   : {created}")
    print(f"Lokasi    : {loc}")
    print(f"Harga     : {price}")
    print(f"No Telp   : {contact or '(tidak ada — Mamikos tidak tampilkan kontak)'}")
    print(f"Link Post : {source_url or '(tidak ada)'}")
    print(f"\n--- Raw Text ---")
    print(raw_text or "(kosong)")
    if caption:
        print(f"\n--- Caption Instagram ---")
        print(caption)
    print(f"{'='*50}\n")


def search(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, location, price, contact, source, status
        FROM posts
        WHERE lower(location) LIKE ? OR lower(raw_text) LIKE ?
        ORDER BY id DESC
    """, (f"%{keyword.lower()}%", f"%{keyword.lower()}%"))
    rows = c.fetchall()
    conn.close()

    if not rows:
        print(f"Tidak ada hasil untuk '{keyword}'.")
        return

    print(f"\nHasil pencarian '{keyword}' ({len(rows)} post):\n")
    print(f"{'ID':<5} {'Lokasi':<35} {'Harga':<20} {'No Telp'}")
    print("-" * 85)
    for pid, loc, price, contact, src, status in rows:
        has_contact = contact or "—"
        print(f"{pid:<5} {_short(loc,33):<35} {_short(price,18):<20} {has_contact}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        list_all()
    elif len(args) == 1 and args[0].isdigit():
        show_detail(int(args[0]))
    else:
        search(" ".join(args))
