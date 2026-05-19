"""
SupportKos Outreach Pipeline.

Scan grup FB untuk pencari kos, generate draft DM personal, kirim notif ke owner via WA.

Priority:
  1. Post utama yang ada nomor WA → notif owner: kirim via WA langsung
  2. Post utama tanpa nomor WA   → notif owner: kirim FB DM
  3. Komentar yang seeking       → notif owner: kirim FB DM ke komentator
"""
import re
import os
import time
import random
import hashlib
import sqlite3
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

from config import (
    FACEBOOK_GROUPS, SEEKING_KEYWORDS, OPENAI_API_KEY, DB_PATH,
    FB_SESSION_PATH, WA_NOTIFY_URL, BALI_AREAS,
)
from scraper import _discover_group_urls

OUTREACH_DB_PATH = os.getenv("OUTREACH_DB_PATH", "data/outreach.db")

# ── Inline helpers (tidak bergantung scraper autokomen) ──────────────────────

def _post_id_from_url(url: str) -> str:
    m = re.search(r'/posts/(\d+)', url)
    if m: return m.group(1)
    m = re.search(r'story_fbid=(\d+)', url)
    if m: return m.group(1)
    return hashlib.md5(url.encode()).hexdigest()[:16]


_OFFERING_SIGNALS = [
    "disewakan", "kami sewakan", "kami tawarkan", "kami punya kos",
    "tersedia kamar", "kamar tersedia", "masih ada kamar", "masih kosong",
    "per bulan", "perbulan", "/bulan", "/bln",
    "hubungi kami", "wa kami", "dm kami",
    "fasilitas:", "harga:", "tarif:", "biaya sewa",
]

# Topik non-kos yang sering trigger SEEKING_KEYWORDS secara tidak sengaja
_NOISE_TOPICS = [
    "motor", "mobil", "kendaraan", "sepeda", "helm",
    "penipuan", "penipu", "modus", "waspada", "hati-hati", "hati hati",
    "warninggg", "scam", "lapor", "polisi", "dpo", "buron",
    "jual beli", "dijual", "for sale", "lelang",
    "lowongan", "loker", "kerja", "gaji", "rekrut",
    "minuman", "makanan", "kuliner", "resto", "cafe",
    "hilang", "kehilangan", "ditemukan",
]

def _is_seeking(text: str) -> bool:
    t = text.lower()
    # Harus ada minimal 1 kata kunci pencari kos
    if not any(kw in t for kw in SEEKING_KEYWORDS):
        return False
    # Skip kalau topiknya bukan tentang kos sama sekali
    has_kos_context = any(kw in t for kw in [
        "kos", "kost", "kamar", "kontrakan", "ngekos", "tempat tinggal",
        "sewa", "ngontrak", "hunian",
    ])
    if not has_kos_context:
        return False
    # Skip kalau ada noise topic yang dominan
    if sum(1 for n in _NOISE_TOPICS if n in t) >= 2:
        return False
    # Skip kalau banyak sinyal offering (ini post penawaran, bukan pencarian)
    if sum(1 for s in _OFFERING_SIGNALS if s in t) >= 2:
        return False
    return True


def _get_post_text(page) -> str:
    return page.evaluate("""
        () => {
            const candidates = [...document.querySelectorAll(
                'div[dir="auto"], [data-ad-preview="message"], [data-ad-comet-preview="message"]'
            )];
            const texts = candidates
                .map(el => el.innerText.trim())
                .filter(t => t.length > 20 && t.length < 5000);
            return texts.sort((a, b) => b.length - a.length)[0] || '';
        }
    """)


# ── Database ──────────────────────────────────────────────────────────────────

def init_outreach_db():
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outreach_leads (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            fb_post_id   TEXT UNIQUE,
            post_url     TEXT,
            poster_name  TEXT,
            profile_url  TEXT,
            wa_number    TEXT,
            location     TEXT,
            post_text    TEXT,
            source_type  TEXT,
            dm_draft     TEXT,
            notified_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def already_notified(fb_post_id: str) -> bool:
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    row = conn.execute(
        "SELECT id FROM outreach_leads WHERE fb_post_id = ?", (fb_post_id,)
    ).fetchone()
    conn.close()
    return row is not None


def count_leads_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM outreach_leads WHERE notified_at >= ?",
        (today + " 00:00:00",)
    ).fetchone()[0]
    conn.close()
    return count


def save_lead(fb_post_id, post_url, poster_name, profile_url, wa_number,
              location, post_text, source_type, dm_draft):
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    try:
        conn.execute("""
            INSERT INTO outreach_leads
                (fb_post_id, post_url, poster_name, profile_url, wa_number,
                 location, post_text, source_type, dm_draft)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fb_post_id, post_url, poster_name, profile_url, wa_number,
              location, post_text, source_type, dm_draft))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


# ── Phone / WA number extraction ─────────────────────────────────────────────

def _normalize_phone(num: str) -> str:
    num = re.sub(r'[^\d]', '', num)
    if num.startswith('0'):
        num = '62' + num[1:]
    return num


def _extract_wa_number(text: str) -> str:
    wa_ctx = re.search(
        r'(?:wa|whatsapp|wp|hubungi|kontak|contact|chat|ping|dm)[\s:.\-]*'
        r'(\+?(?:62|0)[0-9][\d\s\-\.]{7,14})',
        text, re.IGNORECASE
    )
    if wa_ctx:
        return _normalize_phone(wa_ctx.group(1))
    m = re.search(r'(\+?62[\s\-]?\d{3}[\s\-]?\d{3,5}[\s\-]?\d{3,5}|0\d{2,3}[\s\-]?\d{3,5}[\s\-]?\d{3,5})', text)
    if m:
        num = _normalize_phone(m.group(1))
        if 10 <= len(num) <= 15:
            return num
    return ''


# ── FB DOM helpers ────────────────────────────────────────────────────────────

def _extract_poster_info(page) -> tuple[str, str]:
    result = page.evaluate("""
        () => {
            const selectors = [
                'h2 a[href*="facebook.com"]', 'h3 a[href*="facebook.com"]',
                'strong a[href*="facebook.com"]',
                '[data-ad-rendering-role="profile_name"] a',
                'a[role="link"][href*="/user/"]', 'a[role="link"][href*="profile.php"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const name = (el.innerText || el.textContent || '').trim();
                    let href = el.href || '';
                    try {
                        const u = new URL(href);
                        if (u.searchParams.has('id')) {
                            href = u.origin + u.pathname + '?id=' + u.searchParams.get('id');
                        } else {
                            href = u.origin + u.pathname.replace(/\\/posts.*/, '').replace(/\\?.*/, '');
                        }
                    } catch(e) {}
                    if (name && href.includes('facebook.com')) return [name, href];
                }
            }
            return ['', ''];
        }
    """)
    return (result[0] or '', result[1] or '') if result else ('', '')


def _extract_comments_info(page) -> list[dict]:
    return page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('[aria-label*="comment" i][role="button"]').forEach(b => {
                try { b.click(); } catch(e) {}
            });
            document.querySelectorAll('[data-commentid], [aria-label*="Comment by"]').forEach(el => {
                const textEl = el.querySelector('div[dir="auto"]');
                const text = textEl ? textEl.innerText.trim() : '';
                if (!text || text.length < 15 || text.length > 600) return;

                const nameEl = el.querySelector('a[href*="facebook.com"] span, strong a');
                const name = nameEl ? (nameEl.innerText || nameEl.textContent || '').trim() : '';
                const profileEl = el.querySelector('a[href*="facebook.com"]:not([href*="/posts/"])');
                let profileUrl = profileEl ? profileEl.href : '';
                try {
                    const u = new URL(profileUrl);
                    profileUrl = u.searchParams.has('id')
                        ? u.origin + u.pathname + '?id=' + u.searchParams.get('id')
                        : u.origin + u.pathname.replace(/\\/posts.*/, '').replace(/\\?.*/, '');
                } catch(e) {}

                const permalinkEl = el.querySelector('a[href*="/permalink/"], a[href*="comment_id="]');
                const commentUrl = permalinkEl ? permalinkEl.href : '';
                if (text) results.push({ text, name, profileUrl, commentUrl });
            });
            return results.slice(0, 25);
        }
    """)


def _extract_location(text: str) -> str:
    t = text.lower()
    for area in BALI_AREAS:
        if area in t:
            return area.title()
    return "Bali"


# ── Listing lookup ────────────────────────────────────────────────────────────

def _clean_price(price: str) -> str:
    p = (price or '').strip()
    if not p or p in ('N/A', 'Hubungi pemilik', '-'):
        return ''
    if p.startswith('Rp ') and ('/bln' in p or '/bulan' in p):
        return p.replace('/bulan', '/bln')
    m = re.search(r'([\d][.,\d]*)\s*(jt|juta|rb|ribu|k)?', p.lower().replace(' ', ''))
    if not m:
        return ''
    try:
        num = float(m.group(1).replace(',', '.'))
        suffix = (m.group(2) or '').lower()
        if 'jt' in suffix or 'juta' in suffix:
            amt = int(num * 1_000_000)
        elif suffix in ('rb', 'ribu', 'k'):
            amt = int(num * 1_000)
        else:
            amt = int(num * 1_000_000) if num < 10 else int(num * 1_000) if num < 10_000 else int(num)
        if not (400_000 <= amt <= 8_000_000):
            return ''
        if amt >= 1_000_000:
            label = f"{amt/1_000_000:.1f}".rstrip('0').rstrip('.')
            return f"Rp {label}jt/bln"
        return f"Rp {amt // 1000}rb/bln"
    except (ValueError, TypeError):
        return ''


_ADMIN_SUFFIXES = re.compile(
    r',?\s*(Bali|Badung|Gianyar|Tabanan|Denpasar\s*(Barat|Selatan|Utara|Timur)?|'
    r'Denbar|Densel|Denut|Kabupaten|Kota|Indonesia)\s*$',
    re.IGNORECASE,
)
_STREET_RE = re.compile(
    r'((?:jl\.?|jalan|gg\.?|gang|perumahan|komplek|dkt\.?|dekat|belakang|depan|sebelah)'
    r'[\w\s\.,/-]{3,40})',
    re.IGNORECASE,
)


def _extract_street_detail(location: str, raw_text: str, base_area: str) -> str:
    loc_clean = _ADMIN_SUFFIXES.sub('', location).strip().strip(',').strip()
    if _STREET_RE.search(loc_clean):
        return loc_clean[:60]
    if raw_text:
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or len(line) > 120 or base_area.lower() not in line.lower():
                continue
            m = _STREET_RE.search(line)
            if m:
                detail = m.group(1).strip().rstrip('.,').strip()
                return f"{base_area} ({detail[:40]})"
    if base_area.lower() in loc_clean.lower():
        return base_area
    return loc_clean or base_area


def _get_listings_for_area(location: str, limit: int = 3) -> list[dict]:
    try:
        conn = sqlite3.connect(DB_PATH)
        area_kw = location.lower().split()[0] if location else ''
        rows = conn.execute("""
            SELECT location, price, COALESCE(contact,'') as contact,
                   COALESCE(substr(raw_text,1,600),'') as raw_text
            FROM posts
            WHERE status IN ('captioned', 'posted')
              AND LOWER(location) LIKE ?
              AND price IS NOT NULL AND price != ''
              AND price NOT LIKE '%Hubungi%'
              AND price NOT LIKE '%N/A%'
              AND location NOT LIKE '%Bali%'
            ORDER BY RANDOM() LIMIT 30
        """, (f'%{area_kw}%',)).fetchall()
        conn.close()

        results, seen_locs = [], set()
        for loc_raw, price_raw, contact_raw, raw_text in rows:
            if not loc_raw: continue
            clean_p = _clean_price(price_raw)
            if not clean_p: continue
            loc_display = _extract_street_detail(loc_raw, raw_text, location)
            loc_key = loc_display.lower().strip()
            if loc_key in seen_locs: continue
            seen_locs.add(loc_key)
            wa = ''
            if contact_raw:
                wa_m = re.search(r'(\+?62[\d\s-]{8,14}|0[\d\s-]{9,13})', contact_raw)
                if wa_m:
                    wa = re.sub(r'[\s-]', '', wa_m.group(1))
                    if wa.startswith('0'): wa = '62' + wa[1:]
            results.append({'location': loc_display, 'price': clean_p, 'wa': wa})
            if len(results) >= limit: break
        return results
    except Exception as e:
        print(f"⚠️ Gagal ambil listing: {e}")
        return []


# ── DM Draft Generator ────────────────────────────────────────────────────────

_CLOSING = (
    "kalo mau lihat area lain, bisa cek aja di bantukos.com/listings\n\n"
    "btw, saya bukan calo ya kak, harga yang saya infokan real dari owner kost, "
    "saya disini cuman bantu nawarin aja, atau kalo kakak butuh bantuan — "
    "mungkin kayak gak ada waktu buat cek kost sebelum DP, atau lagi diluar kota — aku bisa bantu 🙏"
)


def _format_listings_block(listings: list[dict]) -> str:
    lines = []
    for l in listings:
        line = f"• {l['location']} — {l['price']}"
        if l.get('wa'):
            line += f" (WA owner: {l['wa']})"
        lines.append(line)
    return '\n'.join(lines)


def generate_dm_draft(poster_name: str, post_text: str, location: str, via_wa: bool = False) -> str:
    first_name = poster_name.split()[0] if poster_name else ""
    name_part  = f"Kak {first_name}" if first_name else "Kak"
    loc        = location or "Bali"
    listings   = _get_listings_for_area(loc)
    listing_intro = (
        f"Ada beberapa yang lagi kosong di {loc}:\n{_format_listings_block(listings)}"
        if listings else f"Bisa cek listing kos di {loc} di bantukos.com/listings ya."
    )

    if not OPENAI_API_KEY:
        return f"Halo {name_part}, kebetulan tau ada kos di {loc} nih 👋\n\n{listing_intro}\n\n{_CLOSING}"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = f"""Kamu seorang teman yang genuinely mau bantu orang cari kos.

Seseorang bernama "{name_part}" lagi cari kos di {loc}.
Post mereka: "{post_text[:200]}"

Tulis HANYA bagian pembuka pesannya saja (2-3 kalimat): sapaan natural + sebutkan listing di bawah ini secara apa adanya:

{listing_intro}

Aturan:
- Santai, kayak teman, bukan agen
- Sebutkan listing di atas apa adanya (lokasi + harga + WA owner kalau ada)
- Bahasa gaul/sehari-hari
- JANGAN tambahkan penutup atau ajakan — sudah ditulis terpisah
- Tulis isi pesan saja, tanpa tanda kutip"""

        response = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=1.0,
        )
        opener = response.choices[0].message.content.strip().strip('"').strip("'")
        return f"{opener}\n\n{_CLOSING}"
    except Exception as e:
        print(f"⚠️ OpenAI gagal, pakai template: {e}")
        return f"Halo {name_part}, kebetulan tau ada kos di {loc} nih 👋\n\n{listing_intro}\n\n{_CLOSING}"


# ── WA Notify ─────────────────────────────────────────────────────────────────

def _short_lead_id(wa_number: str, post_url: str) -> str:
    return hashlib.md5(f"{wa_number}{post_url}".encode()).hexdigest()[:6]


def notify_owner_wa(poster_name, profile_url, post_url, post_text,
                    dm_draft, location, wa_number='', source_type='post') -> bool:
    short_post = post_text[:180].replace('\n', ' ')

    outreach_lead = None
    if wa_number:
        lead_id = _short_lead_id(wa_number, post_url)
        outreach_lead = {"id": lead_id, "wa_number": wa_number, "draft": dm_draft}
        wa_link = f"https://wa.me/{wa_number}"
        message = (
            f"🎯 *Lead SupportKos — Via WA Langsung!*\n\n"
            f"👤 Nama  : {poster_name or '?'}\n"
            f"📍 Lokasi: {location}\n"
            f"📱 WA    : {wa_link}\n\n"
            f"📝 *Post asli:*\n_{short_post}_\n\n"
            f"🔗 Lihat post: {post_url}\n\n"
            f"✍️ *Draft pesan WA:*\n---\n{dm_draft}\n---\n\n"
            f"👉 Balas *lead kirim {lead_id}* untuk langsung kirim\n"
            f"   atau klik {wa_link} → paste draft manual"
        )
    elif source_type == 'comment':
        message = (
            f"💬 *Lead SupportKos — Komentar FB*\n\n"
            f"👤 Nama  : {poster_name or '?'}\n"
            f"📍 Lokasi: {location}\n"
            f"🔗 Profil FB: {profile_url or '(tidak terdeteksi)'}\n\n"
            f"💬 *Komentar:*\n_{short_post}_\n\n"
            f"🔗 Lihat komentar: {post_url}\n\n"
            f"✍️ *Draft DM FB:*\n---\n{dm_draft}\n---\n\n"
            f"👉 Buka profil FB di atas → kirim DM"
        )
    else:
        message = (
            f"🎯 *Lead SupportKos — FB DM*\n\n"
            f"👤 Nama  : {poster_name or '?'}\n"
            f"📍 Lokasi: {location}\n"
            f"🔗 Profil FB: {profile_url or '(tidak terdeteksi)'}\n\n"
            f"📝 *Post asli:*\n_{short_post}_\n\n"
            f"🔗 Lihat post: {post_url}\n\n"
            f"✍️ *Draft DM FB:*\n---\n{dm_draft}\n---\n\n"
            f"👉 Buka profil FB di atas → kirim DM"
        )

    payload = {"message": message}
    if outreach_lead:
        payload["outreach_lead"] = outreach_lead

    try:
        resp = requests.post(WA_NOTIFY_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"   ✅ Notif terkirim [{source_type}] {poster_name} → {'WA ' + wa_number if wa_number else 'FB DM'}")
            return True
        print(f"   ⚠️ WA notify gagal: {resp.status_code} {resp.text[:100]}")
        return False
    except Exception as e:
        print(f"   ⚠️ WA notify error: {e}")
        return False


# ── Scan logic ────────────────────────────────────────────────────────────────

def _handle_lead(page, post_url, text, poster_name, profile_url, lead_key, source_type) -> bool:
    location  = _extract_location(text)
    wa_number = _extract_wa_number(text) if source_type == 'post' else ''
    print(f"\n   🎯 Lead [{source_type}]: {poster_name or '?'} | {location}" +
          (f" | 📱 {wa_number}" if wa_number else ""))
    print(f"   📝 {text[:80]}...")
    dm_draft = generate_dm_draft(poster_name, text, location, via_wa=bool(wa_number))
    ok = notify_owner_wa(poster_name, profile_url, post_url, text,
                         dm_draft, location, wa_number, source_type)
    if ok:
        save_lead(lead_key, post_url, poster_name, profile_url, wa_number,
                  location, text[:500], source_type, dm_draft)
    return ok


def _process_post_main(page, post_url: str) -> int:
    post_key = f"outreach_post_{_post_id_from_url(post_url)}"
    if already_notified(post_key):
        return 0
    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=35000)
        time.sleep(random.randint(2, 4))
        post_text = _get_post_text(page)
        if not post_text or not _is_seeking(post_text):
            return 0
        poster_name, profile_url = _extract_poster_info(page)
        return 1 if _handle_lead(page, post_url, post_text, poster_name,
                                 profile_url, post_key, 'post') else 0
    except Exception as e:
        print(f"   ⚠️ Error post utama {post_url}: {e}")
        return 0


def _process_post_comments(page, post_url: str) -> int:
    post_id, leads = _post_id_from_url(post_url), 0
    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=35000)
        time.sleep(random.randint(2, 4))
        for c in _extract_comments_info(page):
            c_text = c.get('text', '')
            if not c_text or not _is_seeking(c_text): continue
            c_key = f"outreach_cmt_{post_id}_{hashlib.md5(c_text.encode()).hexdigest()[:12]}"
            if already_notified(c_key): continue
            if _handle_lead(page, c.get('commentUrl') or post_url, c_text,
                            c.get('name', ''), c.get('profileUrl', ''), c_key, 'comment'):
                leads += 1
            time.sleep(random.randint(1, 3))
    except Exception as e:
        print(f"   ⚠️ Error komentar {post_url}: {e}")
    return leads


def _scan_group_outreach(page, group_url: str) -> int:
    try:
        page.goto(group_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.randint(3, 6))
    except Exception as e:
        print(f"   ⚠️ Gagal buka grup: {e}")
        return 0

    if "groups" not in page.url:
        print("   ⚠️ Tidak bisa masuk grup, skip.")
        return 0

    # Klik tab Diskusi agar feed post tampil
    clicked_tab = False
    for tab_text in ["Diskusi", "Discussion", "Posts"]:
        try:
            tab = page.get_by_role("tab", name=tab_text)
            if tab.count() > 0:
                tab.first.click()
                clicked_tab = True
                print(f"   ✅ Tab: {tab_text}")
                time.sleep(3)
                break
        except Exception:
            pass
    if not clicked_tab:
        for label in ["Diskusi", "Discussion"]:
            try:
                page.get_by_text(label, exact=True).first.click()
                time.sleep(3)
                break
            except Exception:
                pass

    # Sort by Terbaru
    for sort_text in ["Postingan Terbaru", "Newest Posts", "Terbaru"]:
        try:
            btn = page.get_by_text(sort_text, exact=False).first
            if btn.is_visible():
                btn.click()
                time.sleep(2)
                break
        except Exception:
            pass

    # Progressive scroll sambil kumpulkan URL post
    post_links_set = set()
    for step in range(20):
        time.sleep(random.uniform(1.5, 2.5))
        new_urls = page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href || '';
                    if (href.includes('facebook.com') && /\\/posts\\/\\d+|story_fbid=\\d+/.test(href))
                        links.push(href.split('?')[0]);
                });
                return links;
            }
        """)
        before = len(post_links_set)
        post_links_set.update(new_urls)
        if step >= 10 and len(post_links_set) == before:
            break
        page.evaluate("window.scrollBy(0, 2000)")

    post_links = list(post_links_set)[:30]
    print(f"   🔎 {len(post_links)} post ditemukan")
    total = 0

    print("   📌 Pass 1: cek post utama...")
    for post_url in post_links:
        total += _process_post_main(page, post_url)
        time.sleep(random.randint(2, 5))

    print("   💬 Pass 2: scan komentar...")
    for post_url in post_links:
        total += _process_post_comments(page, post_url)
        time.sleep(random.randint(2, 5))

    return total


def run_outreach():
    if not os.path.exists(FB_SESSION_PATH):
        print(f"❌ Session FB tidak ditemukan: {FB_SESSION_PATH}")
        return

    init_outreach_db()
    print(f"\n🎯 Outreach Scan — {count_leads_today()} leads hari ini")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            storage_state=FB_SESSION_PATH,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        for _attempt in range(2):
            try:
                page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)
                break
            except Exception as _e:
                if _attempt == 1:
                    print(f"❌ Gagal buka Facebook setelah 2x coba: {_e}")
                    ctx.close(); browser.close()
                    return
                print(f"⚠️ Timeout buka FB, retry...")
                time.sleep(5)
        time.sleep(3)
        if "login" in page.url or "checkpoint" in page.url:
            print("❌ Session FB expired. Perlu re-export session.")
            ctx.close(); browser.close()
            return

        targets = FACEBOOK_GROUPS if FACEBOOK_GROUPS else _discover_group_urls(page)
        if not targets:
            print("⚠️ Tidak ada grup ditemukan.")
            ctx.close(); browser.close()
            return

        total_leads = 0
        for group_url in targets:
            print(f"\n📋 Outreach scan: {group_url}")
            total_leads += _scan_group_outreach(page, group_url)
            time.sleep(random.randint(10, 20))

        ctx.close()
        browser.close()

    print(f"\n✅ Outreach selesai. Total leads hari ini: {count_leads_today()}")
