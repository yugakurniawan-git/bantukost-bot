# Bantukos Bot — Arsitektur & Alur Sistem

## Komponen

| Komponen | Repo | Fungsi |
|---|---|---|
| `bantukos-bot` | bantukost-bot | Scraping FB/Mamikos, posting IG, outreach lead detection |
| `bantukos-wa-bot` | wa-bot | WA gateway: balas customer, terima notif dari bot |
| `SupportKos` | SupportKos | Website bantukos.com (Next.js) |

---

## Nomor WA

- **WA Bisnis** = nomor WhatsApp yang dipakai `bantukos-wa-bot` (balas customer, terima leads di Saved Messages)
- **WA Pribadi (owner)** = `OWNER_NUMBER` env var di WA bot = `6289506585454` via `OWNER_NOTIFY_NUMBER`

---

## Alur Notifikasi `/notify` (POST ke `http://bantukos-wa-bot:3001/notify`)

| Jenis | `system` field | Tujuan | Kenapa |
|---|---|---|---|
| **Outreach lead** (ada orang cari kos) | `false` / tidak ada | `selfJid` = Saved Messages **WA Bisnis** | Owner buka WA Bisnis, lihat lead, reply "kirim outreach `<id>`" untuk kirim draft ke calon client |
| **System alert** (token expired, disk full, dll) | `true` | `OWNER_NOTIFY_NUMBER` = WA Pribadi | Butuh respon segera, harus ada sound notif |

**JANGAN ubah routing ini.** selfJid untuk leads adalah by design.

---

## Alur Outreach Lead

```
FB Group post "cari kos" terdeteksi
  → _is_seeking() = True
  → notify_owner_wa() kirim ke /notify (system=false → selfJid WA Bisnis)
  → Lead tersimpan di data/outreach_pending.json
  → Owner lihat di Saved Messages WA Bisnis
  → Owner reply "kirim outreach <id>"
  → Bot kirim draft DM ke client via WA atau FB
```

---

## Jadwal Otomatis

| Job | Interval | Fungsi |
|---|---|---|
| Scraping FB | 30 menit | Kumpulkan listing baru dari grup FB |
| Posting IG | 1 jam | Upload 1 post ke Instagram |
| Outreach | 15 menit | Scan grup FB cari "cari kos" |
| Refresh IG Token | 7 hari | Auto-renew Instagram access token (extend 60 hari) |

---

## Environment Variables Penting (bantukos-bot)

| Var | Fungsi |
|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | Token IG, di-refresh otomatis tiap 7 hari |
| `INSTAGRAM_BUSINESS_ID` | ID akun IG bisnis |
| `WA_NOTIFY_URL` | Default: `http://bantukos-wa-bot:3001/notify` |
| `OPENAI_API_KEY` | Untuk generate caption |
| `GITHUB_TOKEN` | Push listings.json ke SupportKos repo |

---

## Instagram Token

- Expired setiap **60 hari**
- Auto-refresh via `_refresh_ig_token()` tiap 7 hari selama bot jalan
- Kalau expired (bot mati lama), generate manual via `python3 get_token.py` lalu update Coolify env
- Token tersimpan di `/app/.env` (override=True) agar overwrite Docker env vars lama

---

## Known Issues / History

- **2026-05-19**: Token IG expired → generate manual, tambah auto-refresh weekly
- **2026-05-19**: Foto portrait (ratio < 4:5) ditolak IG → tambah auto-crop di `image.py`
- **2026-05-19**: `load_dotenv()` tidak override container env → ganti ke `override=True`
- **2026-05-19**: Outreach 0 posts → fix klik tab Diskusi + sort Terbaru sebelum scroll
