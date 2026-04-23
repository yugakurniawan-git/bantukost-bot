from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL
from database import update_caption, DB_PATH
import sqlite3

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Kamu adalah social media manager untuk akun Instagram @bantukos yang menjual jasa inspeksi kos di Bali.

Tugasmu: buat caption Instagram yang menarik dari data listing kos yang ditemukan di Facebook.

Aturan caption:
- Bahasa Indonesia yang santai dan relatable (gaya anak muda)
- Mulai dengan hook yang bikin orang berhenti scroll (pakai emoji)
- Tampilkan info penting: lokasi, harga (kalau ada), fasilitas
- Selalu tambahkan angle: "tapi kondisi aslinya seperti apa?" untuk tease jasa inspeksi
- CTA di akhir: ajak DM untuk cek kondisi real sebelum DP
- Hashtag: 15-20 hashtag relevan di bawah
- Maksimal 300 kata
- JANGAN sebut nama pemilik kos atau nomor kontak mereka
"""

def generate_caption(post_id: int, raw_text: str, location: str, price: str) -> str:
    """Generate caption Instagram dari data kos menggunakan OpenAI."""
    user_message = f"""
Data listing kos dari Facebook:
- Lokasi: {location}
- Harga: {price}
- Deskripsi asli: {raw_text[:800]}

Buat caption Instagram yang menarik untuk postingan ini.
"""
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message}
            ],
            max_tokens=600,
            temperature=0.8,  # sedikit kreatif
        )
        caption = response.choices[0].message.content.strip()
        update_caption(post_id, caption)
        print(f"✍️ Caption berhasil dibuat untuk post ID {post_id}")
        return caption

    except Exception as e:
        print(f"❌ Gagal generate caption: {e}")
        return ""

def process_new_posts():
    """Generate caption untuk semua postingan yang belum punya caption."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, raw_text, location, price FROM posts WHERE status = 'new'")
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("ℹ️ Tidak ada postingan baru untuk di-generate.")
        return

    print(f"\n✍️ Generate caption untuk {len(rows)} postingan...")
    for row in rows:
        post_id, raw_text, location, price = row
        generate_caption(post_id, raw_text, location, price)

if __name__ == "__main__":
    process_new_posts()
