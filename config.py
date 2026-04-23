import os
from dotenv import load_dotenv

load_dotenv()

# ─── OpenAI ───────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = "gpt-4o-mini"  # murah & cukup untuk caption

# ─── Facebook ─────────────────────────────────────────
# Daftar URL grup Facebook yang mau di-monitor
FACEBOOK_GROUPS = [
    # Ganti dengan URL grup kamu
     "https://www.facebook.com/groups/406723907186704",
    # "https://www.facebook.com/groups/NAMA_GRUP_2",
]

# Kata kunci WAJIB ada — postingan harus mengandung salah satu ini
KEYWORDS = [
    # Tipe hunian
    "kos", "kost", "kontrakan", "kamar", "sewa", "ngekos",
    "room", "bulanan", "harian", "per bulan", "disewakan",
    # Kata ketersediaan
    "ready", "tersedia", "available", "kosong", "slot", "unit",
    "siap huni", "siap ditempati",
    # Lokasi Bali
    "canggu", "seminyak", "kuta", "denpasar", "jimbaran",
    "ubud", "sanur", "nusa dua", "legian",
]

# Kata kunci yang menandakan postingan MENAWARKAN kos (harus ada minimal 1)
OFFER_KEYWORDS = [
    "disewakan", "tersedia", "available", "ditawarkan", "dikontrakkan",
    "masih ada", "masih kosong", "masih tersedia", "info kos", "kos tersedia",
    "kamar tersedia", "kamar kosong", "kami menyewakan", "kami sediakan",
    "hubungi", "contact", "wa kami", "dm kami", "per bulan", "perbulan",
    "/bulan", "/bln", "rp ", "harga", "biaya", "tarif", "free wifi",
    "ac", "fasilitas", "furnished", "include", "termasuk"
]

# Kata kunci yang menandakan orang MENCARI kos atau post non-listing — langsung skip
SEEKING_KEYWORDS = [
    # Pencari kos
    "cari kos", "nyari kos", "butuh kos", "mau cari", "mau nyari",
    "ada yang tau", "ada yang tahu", "ada rekomendasi", "ada recommend",
    "tolong info", "mohon info", "mohon bantu", "bantu cari",
    "recommend dong", "rekomen dong", "rekomendasiin", "saranin",
    "ada yang punya", "ada yang jual", "ada yang sewa",
    "lagi cari", "lagi nyari", "help me find", "looking for",
    "need a room", "need room", "mencari kos", "mencari kamar",
    "butuh kamar", "mau nge-kos", "mau ngekos di",
    # Post warning / penipuan / non-listing
    "modus penipuan", "hati hati kawan", "hati-hati", "waspada",
    "warninggg", "scam", "penipu", "tipu", "tertipu",
    "jangan percaya", "lapor polisi",
]

# ─── Instagram (Meta Graph API) ───────────────────────
INSTAGRAM_ACCESS_TOKEN  = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_BUSINESS_ID   = os.getenv("INSTAGRAM_BUSINESS_ID", "")

# ─── Database ─────────────────────────────────────────
DB_PATH = "data/bantukos.db"

# ─── Gambar ───────────────────────────────────────────
IMAGES_DIR        = "data/images"
WATERMARK_TEXT    = "bantukos.id"
MAX_IMAGES_PER_POST = 5  # Instagram max 10, tapi kita batasi 5

# ─── Jadwal ───────────────────────────────────────────
SCRAPE_INTERVAL_MINUTES  = 30   # scraping tiap 30 menit
POST_INTERVAL_HOURS      = 3    # posting tiap 3 jam

# ─── Filter Harga (opsional, 0 = tidak difilter) ──────
MIN_PRICE = 0
MAX_PRICE = 0

# ─── ImgBB ────────────────────────────────────────────
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")
