"""
Export listing ke folder per-post, siap posting manual ke TikTok.

python3 export.py             → export semua listing (captioned + posted)
python3 export.py captioned   → hanya yang belum dipost ke IG
python3 export.py posted      → hanya yang sudah dipost ke IG
python3 export.py 34          → export 1 listing by ID
"""
import os
import sys
import shutil
import sqlite3
import re
from config import DB_PATH

OUTPUT_DIR = "data/export"

HASHTAGS = (
    "#kos #kosBali #sewakos #kontrakan #rumahsewa #properti "
    "#kosMurah #kamarkos #indekos #Bali #Denpasar #Seminyak #Canggu"
)


def _clean_folder_name(text: str) -> str:
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    return text[:40]


def _get_posts(filter_arg: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if filter_arg.isdigit():
        c.execute("""
            SELECT id, location, price, contact, image_paths, caption, status
            FROM posts WHERE id = ?
        """, (int(filter_arg),))
    elif filter_arg in ("captioned", "posted"):
        c.execute("""
            SELECT id, location, price, contact, image_paths, caption, status
            FROM posts WHERE status = ?
            ORDER BY id DESC
        """, (filter_arg,))
    else:
        c.execute("""
            SELECT id, location, price, contact, image_paths, caption, status
            FROM posts WHERE status IN ('captioned', 'posted')
            ORDER BY id DESC
        """)

    rows = c.fetchall()
    conn.close()
    return rows


def export_posts(filter_arg: str = "all"):
    posts = _get_posts(filter_arg)

    if not posts:
        print("Tidak ada listing ditemukan.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    exported = 0

    for post in posts:
        post_id, location, price, contact, image_paths_raw, caption, status = post

        loc_slug = _clean_folder_name(location or "tanpa-lokasi")
        folder_name = f"BK-{post_id}-{loc_slug}"
        folder_path = os.path.join(OUTPUT_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        # Salin foto
        paths = [p.strip() for p in (image_paths_raw or "").split(",") if p.strip()]
        foto_count = 0
        for i, src in enumerate(paths, 1):
            if os.path.exists(src):
                ext = os.path.splitext(src)[1] or ".jpg"
                dst = os.path.join(folder_path, f"foto_{i}{ext}")
                shutil.copy2(src, dst)
                foto_count += 1

        # Buat info.txt
        info_lines = [
            f"ID      : BK-{post_id}",
            f"Status  : {status}",
            f"Lokasi  : {location or '-'}",
            f"Harga   : {price or '-'}",
            f"No HP   : {contact or '-'}",
            f"Foto    : {foto_count} file",
            "",
            "=" * 50,
            "CAPTION (copy ke TikTok / IG):",
            "=" * 50,
            "",
            caption or "(belum ada caption)",
            "",
            HASHTAGS,
        ]

        info_path = os.path.join(folder_path, "info.txt")
        with open(info_path, "w", encoding="utf-8") as f:
            f.write("\n".join(info_lines))

        print(f"  ✅ {folder_name}/ — {foto_count} foto")
        exported += 1

    print(f"\n✨ {exported} listing diekspor ke folder '{OUTPUT_DIR}/'")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    export_posts(arg)
