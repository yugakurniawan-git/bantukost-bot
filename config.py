import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── OpenAI ───────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = "gpt-4o-mini"  # murah & cukup untuk caption

# ─── Facebook ─────────────────────────────────────────
# Daftar URL grup Facebook yang mau di-monitor
FACEBOOK_GROUPS = [
    # ── Sudah lama di config ──────────────────────────────
    "https://www.facebook.com/groups/406723907186704/",   # INFO KOS - BALI
    "https://www.facebook.com/groups/861393030619800/",   # Kost Denpasar
    "https://www.facebook.com/groups/1063633451232483/",  # INFO KOST DENPASAR Sesetan, Sidakarya, Panjer
    "https://www.facebook.com/groups/1380894039527782/",  # INFO KOS SESETAN / Denpasar
    "https://www.facebook.com/groups/1474790899487041/",  # Kos dan Kontrakan Bali
    "https://www.facebook.com/groups/infokossesetan/",    # Info kos-kosan di Bali Denpasar
    "https://www.facebook.com/groups/2910563342557517/",  # Info Kost Denpasar Dan Sekitarnya
    # ── Ditambahkan dari daftar grup owner ───────────────
    "https://www.facebook.com/groups/168852986863089/",   # Info Kost dan Sewa Property Bali Denpasar
    "https://www.facebook.com/groups/291302024580274/",   # Info Kost & Kontrakan Denpasar & Sekitar
    "https://www.facebook.com/groups/1232953460580607/",  # kost/kontrakan pemogan denpasar selatan
    "https://www.facebook.com/groups/1527108684038785/",  # info kost denpasar bali
    "https://www.facebook.com/groups/1214402049300335/",  # INFO KOST BALI DENPASAR SELATAN
    "https://www.facebook.com/groups/507372294884599/",   # INFO KOST CANGGU - BALI
    "https://www.facebook.com/groups/313255506400361/",   # info kost denpasar
    "https://www.facebook.com/groups/info-kos-sewa-kontrakan-rumah-apartment-di-jimbaran-nusadua-bali-1768380166810959/",  # Jimbaran & Nusadua
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
    # Niat eksplisit cari kos
    "cari kos", "nyari kos", "butuh kos", "cari kost", "nyari kost", "butuh kost",
    "mencari kos", "mencari kost", "mencari kamar", "cari kamar", "nyari kamar",
    "mau cari", "mau nyari", "lagi cari", "lagi nyari",
    "mau ngekos", "mau nge-kos", "mau ngekost", "mau kos", "mau kost",
    "belum dapat kos", "belum dapat kost", "susah cari kos",
    # Pertanyaan / info
    "ada yang tau", "ada yang tahu", "ada rekomendasi", "ada recommend",
    "tolong info", "mohon info", "mohon bantu", "bantu cari",
    "recommend dong", "rekomen dong", "rekomendasiin", "saranin",
    "info kost", "info kos", "info kamar",
    "numpang tanya", "minta info", "mau nanya",
    # Pertanyaan dengan harga (pola umum "800rb?", "1jt?")
    "dapet ga", "dapet gak", "ada ga", "ada gak", "ada tidak",
    "ada yang kosong", "masih kosong",
    # Bergabung / share kamar
    "join kost", "join kos", "cari teman kos", "cari roommate", "share kos",
    # Budget / anggaran
    "bajed", "budget kos", "budget kost", "anggaran kos",
    # Bahasa Inggris
    "help me find", "looking for", "need a room", "need room",
    # Ukuran preferensi
    "butuh kamar",
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

# ─── SupportKos Outreach ──────────────────────────────
FB_SESSION_PATH  = os.getenv("FB_SESSION_PATH", "data/fb_session.json")
WA_NOTIFY_URL    = os.getenv("WA_NOTIFY_URL", "http://bantukos-wa-bot:3001/notify")

BALI_AREAS = [
    "canggu", "seminyak", "kuta", "legian", "kerobokan", "berawa", "pererenan",
    "denpasar", "sesetan", "renon", "gatsu", "panjer", "kesiman", "sanur",
    "padangsambian", "pemogan", "monang maning", "imam bonjol", "bypass",
    "jimbaran", "nusa dua", "ubud", "mengwi", "tabanan", "gianyar",
    "sukawati", "ketewel", "tohpati",
]

# ─── Filter Harga (opsional, 0 = tidak difilter) ──────
MIN_PRICE = 0
MAX_PRICE = 0

# ─── ImgBB ────────────────────────────────────────────
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")
