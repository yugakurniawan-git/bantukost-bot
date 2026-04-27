from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL
from database import update_caption, DB_PATH
import sqlite3
import random
from datetime import datetime

client = OpenAI(api_key=OPENAI_API_KEY)

# ─── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Lo admin @bantukos. Nulis caption buat Instagram, santai banget, kayak nge-chat temen.

Aturan singkat:
- Pendek. Maks 5-6 kalimat total (di luar hashtag).
- Gak lebay, gak terlalu semangat, gak pakai tanda seru banyak-banyak.
- Tulis harga pakai format "2,5jt/bulan" bukan "Rp 2.500.000/bulan".
- LOKASI: jangan cuman "Sanur" saja — kasih detail seperti "Sanur belakang" atau "dekat area X". Ada di detail jangan lupa.
- Sisipkan tanggal update yang dikasih, tapi jangan dijadiin headline — taruh natural di tengah atau akhir.
- Emoji max 2, taruh yang relevan doang.
- Jangan pakai kata: "impian", "eksklusif", "terjangkau", "mewah", "segera", "jangan sampai ketinggalan".

CTA WAJIB DI AKHIR — selalu tawarin jasa bantukos:
Kalimat terakhir caption HARUS mengajak orang DM @bantukos untuk:
1. Minta no kontak pemilik (karena data sumber tidak selalu tampilkan)
2. Request survei/cek kondisi kos sebelum DP
3. Minta foto lebih lengkap (kalau foto masih update)

Variasikan kalimatnya, contoh:
- "mau kontak pemilik atau mau kita cekkan dulu kondisinya? dm aja 👋"
- "butuh no telp pemilik atau minta kita survey dulu sebelum DP? dm @bantukos"
- "kalau mau no pemilik atau cek kondisi langsung, dm aja ya"
- "dm kita untuk dapet kontak pemilik atau request survei gratis"

KHUSUS kalau foto kurang/belum lengkap:
- Tambahkan: "foto masih update, dm @bantukos untuk info foto terbaru"
- Jangan pakai "foto tidak tersedia" — terdengar negatif, gunakan "foto update segera"

CONTOH CAPTION LENGKAP:
---
kos di area Sanur belakang (dekat RSUD), 2,3jt/bulan. AC, kamar mandi dalem, WiFi.
baru masuk 26 Apr, kondisinya oke banget.
mau kontak pemilik atau minta kita cekkan dulu? dm aja 👋
---
ada kos campur di Denpasar Barat — 2,1jt. dapet AC + akses 24 jam.
update hari ini, worth it buat harganya.
dm kita buat dapet no pemilik atau request survei gratis.
---
kos di area Kuta (belakang mall), 1,8jt/bulan. foto masih update.
AC, WiFi, kamar bagus. data terbaru per 27 Apr.
dm @bantukos untuk info foto terbaru atau cek kondisi langsung 👋
---

HASHTAG: 12–15 tag, taruh setelah caption dengan baris kosong.
Wajib ada: #kosbali #kostbali #sewakamarbali #carikosanbali #bantukos #infokos #baliliving
Tambah 5–8 hashtag spesifik area dan fasilitas.
"""


def _get_freshness_phrase() -> str:
    """Buat kalimat freshness dengan tanggal dinamis."""
    today = datetime.now()
    day_names = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    month_names = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
                   "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    day   = day_names[today.weekday()]
    date  = today.day
    month = month_names[today.month - 1]
    year  = today.year

    phrases = [
        f"📅 Update {day}, {date} {month} {year}",
        f"🆕 Listing baru masuk {date} {month} {year}",
        f"✅ Diverifikasi tim bantukos — {day} {date} {month} {year}",
        f"📍 Survei lapangan {date} {month} {year}",
        f"🔄 Data terbaru per {date} {month} {year}",
    ]
    return random.choice(phrases)


SYSTEM_PROMPT_FACEBOOK = SYSTEM_PROMPT + """
Sumber: listing ini dari grup Facebook, langsung dari pemiliknya. Tone lebih casual, kayak "nemu ini di grup".
"""

SYSTEM_PROMPT_MAMIKOS = SYSTEM_PROMPT + """
Sumber: listing ini sudah difilter dan dicek tim bantukos. Jangan sebut Mamikos. Tone: "udah kita cek, ini yang rekomen".
"""


def generate_caption(post_id: int, raw_text: str, location: str, price: str,
                     source: str = "facebook", has_photos: bool = True) -> str:
    """Generate caption Instagram dari data kos. source: 'facebook' atau 'mamikos'."""

    freshness = _get_freshness_phrase()
    system = SYSTEM_PROMPT_MAMIKOS if source == "mamikos" else SYSTEM_PROMPT_FACEBOOK

    photo_note = "" if has_photos else "\n- Foto belum tersedia (data baru masuk). Sisipkan 1 kalimat natural bahwa foto masih update dan minta DM @bantukos untuk foto terbaru atau no kontak pemilik."

    user_message = f"""
Data kos:
- Lokasi: {location}
- Harga: {price}
- Detail: {raw_text[:800]}

Tanggal update (sisipkan natural di caption): {freshness}
{photo_note}
Penting: gunakan info lokasi selengkap mungkin dari data di atas (jalan, landmark, area spesifik). Jangan cuma tulis nama kecamatan/area saja.

Tulis caption-nya. Santai, pendek, gak lebay.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=700,
            temperature=0.9,
        )
        caption = response.choices[0].message.content.strip()
        update_caption(post_id, caption)
        print(f"✍️ Caption OK [{source}] post ID {post_id}")
        return caption

    except Exception as e:
        print(f"❌ Gagal generate caption: {e}")
        return ""


def process_new_posts():
    """Generate caption untuk semua postingan yang belum punya caption."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, raw_text, location, price, COALESCE(source, 'facebook'), image_paths
        FROM posts WHERE status = 'new'
    """)
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("ℹ️ Tidak ada postingan baru untuk di-generate.")
        return

    print(f"\n✍️ Generate caption untuk {len(rows)} postingan...")
    for row in rows:
        post_id, raw_text, location, price, source, image_paths = row
        has_photos = bool(image_paths and image_paths.strip())
        generate_caption(post_id, raw_text, location, price, source=source, has_photos=has_photos)


if __name__ == "__main__":
    process_new_posts()
