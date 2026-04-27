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

**1. Login Facebook di laptop lokal terlebih dulu:**
```bash
python3 facebook.py   # biarkan browser terbuka, login manual kalau diminta
```
Setelah login berhasil, session tersimpan di `data/browser_session/`. Folder ini yang nanti di-upload ke server.

**2. Buat file `.env` dari template:**
```bash
cp .env.example .env
# isi semua API key di .env
```

**3. Upload ke Coolify:**
- Push repo ke GitHub
- Di Coolify: New Resource → Docker Compose → pilih repo
- Tambahkan semua isi `.env` sebagai Environment Variables di Coolify
- Set volume mount: `/app/data` → persistent storage agar database & foto tidak hilang saat redeploy

**4. Deploy** — Coolify otomatis build dan jalankan. Bot langsung scrape + posting sesuai jadwal.

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
