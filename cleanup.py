"""
Bersih-bersih posting Instagram lama.

Cara pakai:
  python3 cleanup.py                    → list semua post IG + preview caption
  python3 cleanup.py delete             → hapus semua, minta konfirmasi dulu
  python3 cleanup.py delete --before 2025-03-01   → hapus yang sebelum tanggal ini
  python3 cleanup.py delete --dry-run   → simulasi (tidak benar-benar hapus)
"""
import sys
import requests
import time
from datetime import datetime, timezone
from typing import Optional
from config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID

GRAPH_URL = "https://graph.instagram.com/v21.0"


def fetch_all_posts() -> list[dict]:
    """Ambil semua post dari IG account (support pagination)."""
    posts = []
    url = (
        f"{GRAPH_URL}/{INSTAGRAM_BUSINESS_ID}/media"
        f"?fields=id,caption,timestamp,media_type,permalink"
        f"&limit=50&access_token={INSTAGRAM_ACCESS_TOKEN}"
    )
    while url:
        res = requests.get(url, timeout=15)
        data = res.json()
        if "error" in data:
            print(f"❌ Error API: {data['error'].get('message')}")
            break
        posts.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        if url:
            time.sleep(0.5)
    return posts


def delete_post(media_id: str) -> bool:
    res = requests.delete(
        f"{GRAPH_URL}/{media_id}",
        params={"access_token": INSTAGRAM_ACCESS_TOKEN},
        timeout=15,
    )
    data = res.json()
    return data.get("success") is True or data.get("success") == "true"


def _short_caption(caption: str, n: int = 55) -> str:
    if not caption:
        return "(no caption)"
    clean = caption.replace("\n", " ")
    return clean[:n] + ("…" if len(clean) > n else "")


def _parse_ts(ts: str) -> datetime:
    # Meta returns "+0000" (no colon) which Python 3.9 fromisoformat doesn't support
    from email.utils import parsedate_to_datetime
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S+%f").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def list_posts(posts: list[dict]):
    print(f"\n{'No':<4} {'ID':<20} {'Tanggal':<22} {'Tipe':<12} {'Caption'}")
    print("-" * 105)
    for i, p in enumerate(posts, 1):
        ts   = _parse_ts(p["timestamp"]).strftime("%d %b %Y %H:%M")
        cap  = _short_caption(p.get("caption", ""))
        mtype = p.get("media_type", "?")
        print(f"{i:<4} {p['id']:<20} {ts:<22} {mtype:<12} {cap}")
    print(f"\nTotal: {len(posts)} post\n")


def run_delete(before_date: Optional[datetime], dry_run: bool):
    print("\n⏳ Mengambil semua post dari Instagram...")
    posts = fetch_all_posts()

    if not posts:
        print("ℹ️ Tidak ada post ditemukan.")
        return

    # Filter kalau ada --before
    if before_date:
        targets = [p for p in posts if _parse_ts(p["timestamp"]) < before_date]
        print(f"📅 Filter: sebelum {before_date.strftime('%d %b %Y')} — {len(targets)} dari {len(posts)} post")
    else:
        targets = posts

    if not targets:
        print("ℹ️ Tidak ada post yang cocok dengan filter.")
        return

    list_posts(targets)

    if dry_run:
        print(f"🔍 DRY RUN — {len(targets)} post akan dihapus (tidak benar-benar dihapus).")
        return

    # Konfirmasi
    print(f"⚠️  Ini akan menghapus {len(targets)} post secara PERMANEN dari Instagram.")
    confirm = input("Ketik 'hapus' untuk lanjut, apapun selain itu untuk batal: ").strip().lower()
    if confirm != "hapus":
        print("❎ Dibatalkan.")
        return

    print(f"\n🗑️  Mulai hapus {len(targets)} post...\n")
    deleted = 0
    failed  = 0
    for i, p in enumerate(targets, 1):
        ts  = _parse_ts(p["timestamp"]).strftime("%d %b %Y")
        cap = _short_caption(p.get("caption", ""), 40)
        ok  = delete_post(p["id"])
        if ok:
            deleted += 1
            print(f"  [{i}/{len(targets)}] ✅ Dihapus — {ts} — {cap}")
        else:
            failed += 1
            print(f"  [{i}/{len(targets)}] ❌ Gagal   — {ts} — {cap} (ID: {p['id']})")
        time.sleep(1.2)  # jangan terlalu cepat, hindari rate limit

    print(f"\n✅ Selesai: {deleted} dihapus, {failed} gagal.\n")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("\n⏳ Mengambil semua post dari Instagram...")
        posts = fetch_all_posts()
        if posts:
            list_posts(posts)
        else:
            print("ℹ️ Tidak ada post.")

    elif args[0] == "delete":
        dry_run     = "--dry-run" in args
        before_date = None

        if "--before" in args:
            idx = args.index("--before")
            try:
                before_date = datetime.fromisoformat(args[idx + 1]).replace(tzinfo=timezone.utc)
            except (IndexError, ValueError):
                print("❌ Format tanggal salah. Contoh: --before 2025-03-01")
                sys.exit(1)

        run_delete(before_date=before_date, dry_run=dry_run)

    else:
        print(__doc__)
