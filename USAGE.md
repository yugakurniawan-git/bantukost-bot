# Bantukos Bot — Panduan Penggunaan

## Alur Kerja

```
Scraping → Generate Caption (otomatis) → Upload ke Instagram
```

---

## Facebook

| Command | Keterangan |
|---------|-----------|
| `python3 facebook.py` | Scraping listing dari grup Facebook |
| `python3 facebook.py post` | Upload semua listing Facebook yang siap ke Instagram |
| `python3 facebook.py post 3` | Upload maksimal 3 listing Facebook |
| `python3 facebook.py all` | Scraping + upload sekaligus |

### Menambah / Mengganti Grup Facebook

Edit file **`config.py`**, bagian `FACEBOOK_GROUPS`:

```python
FACEBOOK_GROUPS = [
    "https://www.facebook.com/groups/406723907186704",   # sudah ada
    "https://www.facebook.com/groups/ID_GRUP_BARU",      # tambahkan di sini
    "https://www.facebook.com/groups/ID_GRUP_LAIN",      # bisa lebih dari 2
]
```

**Cara dapat URL grup:**
1. Buka grup Facebook di browser
2. Salin URL dari address bar — pastikan formatnya `.../groups/ANGKA_ATAU_NAMA`
3. Bot harus sudah login ke Facebook (session tersimpan di `facebook_session.json`)

> ⚠️ Bot hanya bisa scrape grup yang **akunnya sudah jadi member**. Kalau belum bergabung, scraping akan gagal atau hasilnya kosong.

### Estimasi Waktu Scraping

| Jumlah Grup | Estimasi Waktu | Keterangan |
|-------------|---------------|------------|
| 1 grup | ~3–5 menit | Scroll + Pass 2 (visit tiap post) + page load |
| 3 grup | ~12–18 menit | Ditambah jeda 30–90 detik antar grup |
| 5 grup | ~22–35 menit | Default interval `SCRAPE_INTERVAL_MINUTES = 30` sudah pas |
| 10 grup | ~50–70 menit | Naikkan interval ke 60 menit di `config.py` |

**Komponen waktu per grup:**
- Scroll feed: ~40–90 detik (bot scroll otomatis, berhenti kalau sudah tidak ada post baru)
- Pass 2 (buka tiap post URL): ~2–5 menit (tergantung banyak post baru)
- Jeda antar grup: 30–90 detik (acak, agar tidak kelihatan seperti bot)

**Kalau 5 grup terlalu lama:** naikkan `MAX_POSTS_PER_GROUP` dari 25 ke angka lebih kecil (misal 10) di `config.py` untuk mempersingkat Pass 2.

---

## Mamikos

| Command | Keterangan |
|---------|-----------|
| `python3 mamikos.py` | Scraping listing dari Mamikos |
| `python3 mamikos.py post` | Upload semua listing Mamikos yang siap ke Instagram |
| `python3 mamikos.py post 3` | Upload maksimal 3 listing Mamikos |
| `python3 mamikos.py all` | Scraping + upload sekaligus |

---

## Lookup Database

Dipakai kalau ada client nanya info kos atau minta no telp pemilik.  
ID kos tertera di setiap caption Instagram dengan format `📋 ID: BK-34`.

| Command | Keterangan |
|---------|-----------|
| `python3 lookup.py` | Tampilkan semua post beserta no telp |
| `python3 lookup.py 34` | Detail lengkap post ID 34 (no telp, raw text, caption) |
| `python3 lookup.py kuta` | Cari listing berdasarkan kata kunci lokasi |

---

## Export Listing untuk TikTok (Manual Posting)

Buat folder per listing — tiap folder berisi foto + `info.txt` (caption, harga, no HP).

| Command | Keterangan |
|---------|-----------|
| `python3 export.py` | Export semua listing (captioned + posted) |
| `python3 export.py captioned` | Hanya listing yang belum dipost ke IG |
| `python3 export.py posted` | Hanya listing yang sudah dipost ke IG |
| `python3 export.py 34` | Export 1 listing by ID |

Hasil tersimpan di folder `data/export/` (masuk ke volume, aman dari restart):
```
data/export/
  BK-34-Sesetan/
    foto_1.jpg
    foto_2.jpg
    info.txt   ← lokasi, harga, no HP, caption siap paste
  BK-41-Kuta/
    foto_1.jpg
    info.txt
```

**Cara jalankan dari server:**
```bash
# Jalankan export di dalam container
docker exec -it 1771 python3 export.py captioned

# Download hasil export ke laptop
scp -r root@SERVER_IP:/data/bantukos/export/ ~/Desktop/bantukos-tiktok/
```

**Cara post ke TikTok:**
1. Buka folder `BK-XX-.../` di laptop
2. Di TikTok → **+** → **Upload** → pilih tab **Image**
3. Pilih semua foto dari folder itu
4. Copy caption dari `info.txt` → paste ke TikTok
5. Post

---

## Sync Database ke Google Sheets

Lihat semua listing dan history komentar autokomen langsung dari Google Sheets — mudah dicari, bisa filter, bisa share ke klien.

### Setup awal (sekali saja)

**1. Buat Service Account di Google Cloud:**
1. Buka [console.cloud.google.com](https://console.cloud.google.com) → pilih project kamu
2. **IAM & Admin** → **Service Accounts** → **+ CREATE SERVICE ACCOUNT**
3. Name: `bantukos-sheets` → **CREATE AND CONTINUE** → **DONE**
4. Klik service account yang baru dibuat → tab **Keys** → **ADD KEY** → **Create new key** → **JSON** → **CREATE**
5. File JSON akan ter-download otomatis

**2. Taruh credentials di server:**
```bash
# Upload dari laptop ke server
scp google-credentials.json root@SERVER_IP:/data/bantukos/google_credentials.json
```

**3. Buat Google Sheet:**
1. Buka [sheets.google.com](https://sheets.google.com) → buat spreadsheet baru
2. Dari URL ambil ID-nya: `docs.google.com/spreadsheets/d/**ID_INI**/edit`
3. Klik **Share** → masukkan email service account (ada di file JSON, field `client_email`) → **Editor** → **Send**

**4. Isi `.env` di server:**
```bash
GOOGLE_CREDENTIALS_PATH=data/google_credentials.json
GOOGLE_SPREADSHEET_ID=ID_DARI_URL_TADI
```

### Jalankan sync

```bash
# Sync listing saja
docker exec -it CONTAINER_ID python3 sync_sheets.py

# Sync komentar autokomen saja
docker exec -it CONTAINER_ID python3 sync_sheets.py autokomen

# Sync keduanya sekaligus
docker exec -it CONTAINER_ID python3 sync_sheets.py all
```

Sync juga otomatis dijalankan setiap kali bot selesai posting ke Instagram.

### Isi sheet

**Sheet "Listings"** — satu baris per listing kos:

| Kolom | Isi |
|-------|-----|
| ID | BK-58, BK-59, dst |
| Sumber | facebook / mamikos |
| Lokasi | Sesetan, Denpasar Selatan |
| Harga | 800rb/bln |
| No WA / Kontak | 081234567890 |
| Status | posted / captioned / new |
| Jumlah Foto | 3 |
| Caption (preview) | 100 karakter pertama |
| Tanggal Masuk | 2026-05-01 10:30 |
| Tanggal Post IG | 2026-05-01 12:00 |

**Sheet "AutoKomen"** — satu baris per komentar yang diposting bot:

| Kolom | Isi |
|-------|-----|
| No | nomor urut |
| Tanggal | 2026-05-01 14:30 |
| Link Post FB | link post yang dikomen |
| Lokasi Dicari | Sesetan |
| Listing Ditawarkan | BK-58 |
| Komentar yang Dipost | teks komentar (150 char) |

---

## Generate Caption Manual

Kalau ada post `new` yang captionnya belum di-generate:

```bash
python3 caption.py
```

---

## Bersih-bersih Post Instagram

| Command | Keterangan |
|---------|-----------|
| `python3 cleanup.py` | Tampilkan semua post IG beserta tanggal + preview caption |
| `python3 cleanup.py delete` | Hapus semua post IG (minta konfirmasi dulu) |
| `python3 cleanup.py delete --before 2025-03-01` | Hapus semua post sebelum tanggal tertentu |
| `python3 cleanup.py delete --dry-run` | Simulasi — lihat apa yang akan dihapus tanpa benar-benar hapus |

> ⚠️ Hapus IG post tidak bisa di-undo. Selalu cek dulu pakai `python3 cleanup.py` atau `--dry-run`.

---

## Deploy ke Coolify (Auto Scrape + Post)

### Persiapan pertama (sekali saja)

**1. Export session Facebook dari laptop:**
```bash
python3 facebook.py --export-session
```
Browser Chromium terbuka → login Facebook di sana → balik ke terminal → tekan Enter.
Session tersimpan di `data/fb_session.json` (~2KB).

**2. Upload session ke server:**
```bash
scp data/fb_session.json root@SERVER_IP:/data/bantukos/fb_session.json
```

**3. Buat file `.env` dari template:**
```bash
cp .env.example .env
# isi semua API key di .env
```

**4. Upload ke Coolify:**
- Push repo ke GitHub
- Di Coolify: New Resource → Docker Compose → pilih repo
- Tambahkan semua isi `.env` sebagai Environment Variables di Coolify (termasuk `PYTHONUNBUFFERED=1`)
- Set volume mount: source `/data/bantukos` → destination `/app/data`

**5. Deploy** — Coolify build dan jalankan. Bot langsung scrape + posting sesuai jadwal.

### Memantau Proses Scraping di Server

**1. Lihat log real-time di Coolify:**
- Buka Coolify → pilih service `bantukos-bot` → tab **Logs**
- Log muncul langsung saat bot scraping/posting

**2. Lihat log via SSH:**
```bash
# Sambung ke server
ssh root@SERVER_IP

# Cari nama container dulu
docker ps
# Lihat kolom NAMES paling kanan — yang ada "python main.py" itu botnya
# Bisa pakai 4 huruf pertama CONTAINER ID, contoh: 1771

# Stream log real-time (keluar dengan Ctrl+C)
docker logs -f --tail=100 1771
```

**3. Cek status database (berapa post terkumpul):**
```bash
docker exec -it 1771 python3 -c "
from database import get_stats
get_stats()
"
```

**4. Trigger scraping manual (tanpa tunggu jadwal):**
```bash
docker exec -it 1771 python3 facebook.py
```

**5. Trigger upload manual:**
```bash
docker exec -it 1771 python3 facebook.py post
```

**Yang muncul di log saat scraping berjalan:**
```
🔵 FACEBOOK — Scraping
Grup 1/2: https://www.facebook.com/groups/...
  ✅ 14 post baru ditemukan
Grup 2/2: https://www.facebook.com/groups/...
  ✅ 8 post baru ditemukan
✨ Total: 22 post baru | 0 duplikat dilewati
```

---

### Session Facebook expired

Kalau di log muncul `Session Facebook expired`:
```bash
# Di laptop lokal
python3 facebook.py --export-session
scp data/fb_session.json root@202.155.18.49:/data/bantukos/fb_session.json
P:/data/bantukos/fb_session.json
# Restart container di Coolify (tidak perlu rebuild)
```

### Jadwal default (bisa diubah di `config.py`)

| Setting | Nilai | Keterangan |
|---------|-------|-----------|
| `SCRAPE_INTERVAL_MINUTES` | 30 | Scraping Facebook tiap 30 menit |
| `POST_INTERVAL_HOURS` | 6 | Upload ke IG tiap 6 jam |
| `MAX_POSTS_PER_RUN` | 2 | Max 2 post per siklus (~8 post/hari) |

> IG aman sampai ~20 post/hari. Dengan setting default = ~8 post/hari, jauh dari limit.

### Cara bot memilih post terbaik

Setiap siklus posting, bot tidak asal pilih — tapi skor tiap post dulu:

| Kriteria | Poin |
|----------|------|
| Ada foto | +60 (base) + 5 per foto tambahan |
| Lokasi lengkap (ada jalan/gang/no rumah) | +30 |
| Lokasi sub-area + area (misal "Sesetan, Denpasar Selatan") | +20 |
| Ada nomor HP | +25 |
| Harga disebutkan dengan jelas | +15 |
| Teks detail (>300 karakter) | +10 |

Post dengan skor tertinggi diupload duluan. Post tanpa foto dan tanpa nomor HP akan tunggu giliran paling akhir.

---

## Reset Database

> ⚠️ Hapus semua data — tidak bisa di-undo.

```bash
rm data/bantukos.db
rm data/images/*.jpg
```

---

## Struktur Status Post

```
new → captioned → posted
```

- **new**: baru masuk dari scraping, belum ada caption
- **captioned**: caption sudah di-generate, siap upload
- **posted**: sudah diupload ke Instagram
