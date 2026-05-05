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
    # Lokasi Bali — area utama
    "canggu", "seminyak", "kuta", "denpasar", "jimbaran",
    "ubud", "sanur", "nusa dua", "legian",
    # Sub-area Denpasar & sekitarnya
    "sesetan", "renon", "gatsu", "panjer", "kesiman",
    "padangsambian", "pemogan", "monang maning", "imam bonjol",
    "bypass", "kerobokan", "berawa", "pererenan", "mengwi",
    "tabanan", "gianyar", "sukawati", "ketewel", "tohpati",
    "denbar", "densel", "denut", "denbarat", "denpasar barat",
    "denpasar selatan", "denpasar utara", "denpasar timur",
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
    # Pencari kos / kost
    "cari kos", "nyari kos", "butuh kos", "cari kost", "nyari kost", "butuh kost",
    "mau cari", "mau nyari", "lagi cari", "lagi nyari",
    "ada yang tau", "ada yang tahu", "ada rekomendasi", "ada recommend",
    "tolong info", "mohon info", "mohon bantu", "bantu cari",
    "recommend dong", "rekomen dong", "rekomendasiin", "saranin",
    "ada yang punya", "ada yang jual", "ada yang sewa",
    "help me find", "looking for",
    "need a room", "need room", "mencari kos", "mencari kost", "mencari kamar",
    "butuh kamar", "mau nge-kos", "mau ngekos di", "mau ngekost",
    "belum dapat kos", "belum dapat kost", "susah cari kos", "susah cari kost",
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
POST_INTERVAL_HOURS      = 6    # posting tiap 6 jam (~4 post/hari — aman dari spam IG)

# ─── Batas posting per siklus ──────────────────────────
# Makin kecil = lebih aman. 2 per 6 jam = ~8 post/hari (batas aman IG ~20/hari)
MAX_POSTS_PER_RUN        = 2

# ─── Filter Harga (opsional, 0 = tidak difilter) ──────
MIN_PRICE = 0
MAX_PRICE = 0

# ─── ImgBB ────────────────────────────────────────────
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")
