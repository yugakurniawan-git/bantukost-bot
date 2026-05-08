"""
Sync data dari SQLite ke Google Sheets.

python3 sync_sheets.py           → sync listings bantukos-bot
python3 sync_sheets.py autokomen → sync komentar autokomen-bot
python3 sync_sheets.py all       → sync keduanya
"""
import sys
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_PATH  = os.getenv("GOOGLE_CREDENTIALS_PATH", "data/google_credentials.json")
SPREADSHEET_ID    = os.getenv("GOOGLE_SPREADSHEET_ID", "")
BANTUKOS_DB_PATH  = os.getenv("BANTUKOS_DB_PATH", "data/bantukos.db")
AUTOKOMEN_DB_PATH = os.getenv("AUTOKOMEN_DB_PATH", "../bantukos-autokomen-bot/data/autokomen.db")


def _get_client():
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"❌ File credentials tidak ditemukan: {CREDENTIALS_PATH}")
        print("   Download dari Google Cloud Console → Service Accounts → Keys → JSON")
        sys.exit(1)
    if not SPREADSHEET_ID:
        print("❌ GOOGLE_SPREADSHEET_ID belum diisi di .env")
        sys.exit(1)
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_sheet(spreadsheet, title: str):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=2000, cols=20)


def sync_listings():
    """Sync tabel posts bantukos-bot ke sheet 'Listings'."""
    print("📊 Sync listings bantukos-bot ke Google Sheets...")

    if not os.path.exists(BANTUKOS_DB_PATH):
        print(f"   ⚠️ DB tidak ditemukan: {BANTUKOS_DB_PATH}")
        return

    conn = sqlite3.connect(BANTUKOS_DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, source, location, price, contact, status,
               image_paths, caption, created_at, posted_at,
               COALESCE(verified, 0) as verified,
               COALESCE(verified_at, '') as verified_at
        FROM posts
        ORDER BY id DESC
    """)
    rows = c.fetchall()
    conn.close()

    client = _get_client()
    ss = client.open_by_key(SPREADSHEET_ID)
    sheet = _get_or_create_sheet(ss, "Listings")

    # Header
    headers = [
        "ID", "Sumber", "Lokasi", "Harga", "No WA / Kontak",
        "Status", "Terverifikasi", "Tgl Verifikasi",
        "Jumlah Foto", "Caption (preview)", "Tanggal Masuk", "Tanggal Post IG"
    ]

    data = [headers]
    for r in rows:
        post_id, source, location, price, contact, status, img_paths, caption, created_at, posted_at, verified, verified_at = r
        foto_count = len([p for p in (img_paths or "").split(",") if p.strip()])
        caption_preview = (caption or "")[:100].replace("\n", " ")
        data.append([
            f"BK-{post_id}",
            source or "facebook",
            location or "-",
            price or "-",
            contact or "-",
            status or "-",
            "✅ Ya" if verified else "—",
            (verified_at or "-")[:16],
            foto_count,
            caption_preview,
            (created_at or "-")[:16],
            (posted_at or "-")[:16] if posted_at else "-",
        ])

    sheet.clear()
    sheet.update(data, "A1")

    # Format header — bold + freeze
    sheet.format("A1:L1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.2, "green": 0.5, "blue": 0.8}, "horizontalAlignment": "CENTER"})
    # Highlight kolom Terverifikasi (G) hijau untuk yang terverifikasi
    sheet.freeze(rows=1)

    print(f"   ✅ {len(rows)} listing di-sync ke sheet 'Listings'")


def sync_autokomen():
    """Sync tabel commented_posts autokomen-bot ke sheet 'AutoKomen'."""
    print("📊 Sync komentar autokomen ke Google Sheets...")

    if not os.path.exists(AUTOKOMEN_DB_PATH):
        print(f"   ⚠️ DB tidak ditemukan: {AUTOKOMEN_DB_PATH}")
        return

    conn = sqlite3.connect(AUTOKOMEN_DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, fb_post_id, post_url, sought_location,
               listing_id, comment_text, commented_at
        FROM commented_posts
        ORDER BY commented_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    client = _get_client()
    ss = client.open_by_key(SPREADSHEET_ID)
    sheet = _get_or_create_sheet(ss, "AutoKomen")

    headers = [
        "No", "Tanggal", "Link Post FB", "Lokasi Dicari",
        "Listing Ditawarkan", "Komentar yang Dipost"
    ]

    data = [headers]
    for r in rows:
        rid, fb_post_id, post_url, sought_location, listing_id, comment_text, commented_at = r
        data.append([
            rid,
            (commented_at or "-")[:16],
            post_url or fb_post_id or "-",
            sought_location or "-",
            f"BK-{listing_id}" if listing_id else "-",
            (comment_text or "-")[:150].replace("\n", " "),
        ])

    sheet.clear()
    sheet.update(data, "A1")
    sheet.format("A1:F1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.1, "green": 0.65, "blue": 0.3}, "horizontalAlignment": "CENTER"})
    sheet.freeze(rows=1)

    print(f"   ✅ {len(rows)} komentar di-sync ke sheet 'AutoKomen'")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "listings"

    if mode == "all":
        sync_listings()
        sync_autokomen()
    elif mode == "autokomen":
        sync_autokomen()
    else:
        sync_listings()

    print("\n✅ Sync selesai!")
    if SPREADSHEET_ID:
        print(f"   Buka: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
