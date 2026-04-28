import re
import os
import time
import random
import hashlib
from playwright.sync_api import sync_playwright
from config import FACEBOOK_GROUPS, KEYWORDS, SEEKING_KEYWORDS, IMAGES_DIR
from database import is_duplicate, save_post
from ocr import ocr_image, is_kos_flyer

MAX_POSTS_PER_GROUP  = 25
MAX_POSTS_PER_CYCLE  = 60
MAX_COMMENTS_PER_POST = 5   # max listing komentar yang diambil per post pencarian

os.makedirs(IMAGES_DIR, exist_ok=True)

# ─── Filter Functions ──────────────────────────────────

# Kata pendek yang harus match sebagai kata utuh (word-boundary)
# supaya "kosmetik" tidak ikut match "kos", "ready set" tidak match "ready"
_WHOLE_WORD_KW = {"kos", "kost", "kamar", "sewa", "room", "unit",
                  "ready", "kosong", "slot", "bulanan", "harian", "available"}

def contains_keyword(text: str) -> bool:
    """Postingan harus mengandung minimal 1 kata kunci kos."""
    t = text.lower()
    for kw in KEYWORDS:
        if kw in _WHOLE_WORD_KW:
            # Gunakan word-boundary supaya tidak false-positive di tengah kata
            if re.search(r'\b' + re.escape(kw) + r'\b', t):
                return True
        else:
            # Keyword panjang / nama lokasi — substring match cukup
            if kw in t:
                return True
    return False

# Offering signals: komentar/post yang MENAWARKAN kos harus punya minimal 1
# Sengaja TIDAK pakai bare "k" (185k bisa harga makanan) — harus ada Rp, /bulan, atau nomor HP
_OFFERING_SIGNALS = [
    r'rp[\s.]*[\d.,]+',                                            # Rp 500.000 / Rp 500rb
    r'\d[\d.,]*\s*(?:juta|jt)',                                    # 1.5 juta / 1jt
    r'\d[\d.,]*\s*(?:ribu|rb)',                                    # 500rb / 500 ribu
    r'/\s*(?:bulan|bln|bl|month)',                                  # /bulan
    r'(?:08|62|\+62)\d{7,}',                                       # nomor WA/HP
    r'(?:disewakan|tersedia|available|masih ada|masih kosong|'
    r'siap huni|info kos|kos tersedia|kamar kosong|kamar tersedia)',
]
_OFFERING_RE = re.compile('|'.join(_OFFERING_SIGNALS), re.IGNORECASE)

def has_offering_signal(text: str) -> bool:
    """Pastikan ada sinyal tawaran kos: harga (Rp/juta/rb/bulan), nomor HP, atau kata penawaran."""
    return bool(_OFFERING_RE.search(text))

def is_seeking_post(text: str) -> bool:
    """
    Deteksi postingan orang yang MENCARI kos — langsung skip.
    Hanya skip kalau ada frasa yang jelas menandakan pencarian.
    """
    t = text.lower()
    return any(kw in t for kw in SEEKING_KEYWORDS)

# ─── Extract Functions ─────────────────────────────────

def extract_price(text: str) -> str:
    patterns = [
        r'[Rr][Pp]\.?\s*[\d.,]+\s*(?:juta|jt|rb|ribu|k)?(?:\s*/\s*(?:bulan|bln|bl|month))?',
        r'[\d.,]+\s*(?:juta|jt)\s*(?:/\s*(?:bulan|bln))?',
        r'[\d.,]+\s*(?:ribu|rb|k)\s*(?:/\s*(?:bulan|bln))?',
    ]
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return "Hubungi pemilik"

def extract_contact(text: str) -> str:
    match = re.search(r'(?:08|62|\+62)\d{8,12}', text)
    return match.group(0) if match else ""

def extract_location(text: str) -> str:
    """
    Ambil lokasi bersih dari teks — return area + sub-area kalau ada.
    Contoh: "Sesetan, Denpasar Selatan" bukan seluruh kalimat.
    """
    # Sub-area lebih spesifik — cek dulu sebelum area umum
    sub_areas = [
        "Sesetan", "Renon", "Panjer", "Kesiman", "Pemogan", "Padangsambian",
        "Monang Maning", "Imam Bonjol", "Tohpati", "Ketewel",
        "Berawa", "Pererenan", "Kerobokan", "Kedonganan",
        "Pecatu", "Uluwatu", "Bukit", "Bypass",
        "Tegallalang", "Sukawati", "Gianyar",
        "Mengwi", "Tabanan",
    ]
    main_areas = [
        "Denpasar Barat", "Denpasar Selatan", "Denpasar Utara", "Denpasar Timur",
        "Canggu", "Seminyak", "Kuta", "Legian",
        "Jimbaran", "Nusa Dua", "Ubud", "Sanur",
        "Denpasar", "Badung",
    ]

    t = text.lower()
    found_sub  = [a for a in sub_areas  if a.lower() in t]
    found_main = [a for a in main_areas if a.lower() in t]

    if found_sub and found_main:
        # Cek apakah sub dan main disebutkan berdekatan (dalam 50 char)
        sub  = found_sub[0]
        main = found_main[0]
        pos_sub  = t.find(sub.lower())
        pos_main = t.find(main.lower())
        if abs(pos_sub - pos_main) < 60:
            return f"{sub}, {main}"
        # Kalau berjauhan, pakai yang lebih spesifik (sub_area)
        return sub
    if found_sub:
        return found_sub[0]
    if found_main:
        return found_main[0]
    return "Bali"

# ─── Image Extraction ─────────────────────────────────

def download_image_via_playwright(page, url: str, filepath: str) -> bool:
    """Download satu gambar pakai session browser yang sudah login."""
    try:
        response = page.request.get(url, timeout=15000)
        if response.ok and len(response.body()) > 10000:  # skip < 10KB
            with open(filepath, "wb") as f:
                f.write(response.body())
            return True
        return False
    except Exception as e:
        print(f"   ⚠️ Gagal download: {e}")
        return False

def get_post_photo_urls(page, post_element) -> list:
    """
    Ambil URL foto konten dari postingan Facebook.
    Strategi: cari link yang mengarah ke halaman foto FB,
    lalu ambil src dari img di dalamnya.
    """
    # Cari semua link foto di dalam postingan
    photo_urls = page.evaluate("""
        (postEl) => {
            const results = [];

            // Strategi 1: cari <a> yang href-nya ke halaman foto
            const photoLinks = postEl.querySelectorAll(
                'a[href*="/photo/"], a[href*="photo_id="], a[href*="fbid="]'
            );

            for (const link of photoLinks) {
                // Ambil gambar di dalam link foto ini
                const img = link.querySelector('img[src*="fbcdn"]');
                if (img && img.src) {
                    // Upgrade ke resolusi lebih tinggi kalau bisa
                    let src = img.src;
                    src = src.replace(/\\/s[0-9]+x[0-9]+\\//, '/s960x960/');
                    src = src.replace(/\\/p[0-9]+x[0-9]+\\//, '/p960x960/');
                    if (!results.includes(src)) results.push(src);
                }
            }

            // Strategi 2: kalau tidak ketemu link foto, cari img langsung
            // tapi filter ketat berdasarkan ukuran & pola URL
            if (results.length === 0) {
                const imgs = postEl.querySelectorAll('img[src*="fbcdn"]');
                const skipPatterns = [
                    's32x32','s40x40','s50x50','s60x60','s75x75',
                    'p32x32','p40x40','p50x50','p60x60','p75x75',
                    'p100x100','s100x100','emoji','sticker','reaction',
                    'rsrc.php'
                ];

                for (const img of imgs) {
                    const src = img.src || '';
                    if (skipPatterns.some(p => src.includes(p))) continue;

                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    if (w > 0 && w < 300) continue;
                    if (h > 0 && h < 300) continue;

                    if (src && !results.includes(src)) results.push(src);
                }
            }

            return results.slice(0, 5);
        }
    """, post_element)

    return photo_urls if photo_urls else []

def process_post_images(page, post_element, post_id: str) -> tuple:
    """
    Ambil dan download foto konten dari satu postingan.
    Return (saved_paths, ocr_text) — ocr_text diisi kalau foto ada teks (flyer).
    """
    img_urls = get_post_photo_urls(page, post_element)

    if not img_urls:
        print("   📷 Tidak ada foto konten ditemukan.")
        return [], ""

    saved = []
    ocr_texts = []
    for i, url in enumerate(img_urls):
        name = f"{hashlib.md5(post_id.encode()).hexdigest()[:8]}_{i}.jpg"
        path = os.path.join(IMAGES_DIR, name)
        ok = download_image_via_playwright(page, url, path)
        if not ok:
            ok = download_image_via_playwright(page, url, path)
        if ok:
            saved.append(path)
            print(f"   📷 Foto {i+1} OK ({os.path.getsize(path)//1024}KB): {name}")
            # OCR hanya pada foto pertama (biasanya yang paling relevan)
            if i == 0:
                ocr_text = ocr_image(path)
                if ocr_text and is_kos_flyer(ocr_text):
                    print(f"   🔡 OCR flyer: {ocr_text[:80].strip()!r}")
                    ocr_texts.append(ocr_text)

    return saved, "\n".join(ocr_texts)

# ─── Script Tag Fallback ──────────────────────────────

def _unescape_fb_json_string(raw: str) -> str:
    """Unescape escaped string dari dalam JSON Facebook."""
    return (raw
            .replace('\\n', '\n')
            .replace('\\"', '"')
            .replace('\\\\', '\\')
            .replace('\\u00a0', '\u00a0')
            .replace('\\/', '/'))


def _extract_images_near(content: str, pos: int, window: int = 8000) -> list:
    """
    Cari URL gambar fbcdn.net dalam window karakter sekitar posisi `pos`.
    Hanya ambil gambar resolusi tinggi (bukan thumbnail kecil).
    """
    import re as _re

    chunk = content[max(0, pos - window // 2): pos + window // 2]
    # URI fbcdn.net — hanya yang ada dimensi besar atau tanpa dimensi kecil
    skip = {'s32x32','s40x40','s50x50','s60x60','s75x75','s100x100',
            'p32x32','p40x40','p50x50','p60x60','p75x75','p100x100',
            'emoji','sticker','reaction','rsrc.php'}
    found = []
    for m in _re.finditer(r'"uri":"(https?:\\/\\/[^"]*scontent[^"]*fbcdn\.net[^"]*)"', chunk):
        url = m.group(1).replace('\\/', '/')
        if any(s in url for s in skip):
            continue
        if url not in found:
            found.append(url)
        if len(found) >= 5:
            break
    return found


def _extract_from_scripts(page) -> list:
    """
    Fallback: parse teks + gambar postingan langsung dari JSON di <script data-sjs>.
    Facebook Comet SSR menyimpan semua data dalam:
      {"message":{"text":"isi post"},...,"uri":"https://...fbcdn.net/..."}
    Returns list of (None, text, img_urls) — elemen DOM = None.
    """
    import re as _re

    scripts = page.evaluate("""
        () => Array.from(document.querySelectorAll('script[data-sjs]'))
                   .map(s => s.textContent || '')
    """)

    seen_texts = set()
    posts = []  # tuples: (None, text, [img_url, ...])

    for content in scripts:
        for m in _re.finditer(r'"message":\{"text":"((?:[^"\\]|\\.){10,1500})"', content):
            raw = m.group(1)
            text = _unescape_fb_json_string(raw)
            if not text or len(text) < 15 or text in seen_texts:
                continue
            seen_texts.add(text)

            img_urls = _extract_images_near(content, m.start())
            if img_urls:
                print(f"      🖼 {len(img_urls)} gambar ditemukan untuk: {text[:50]!r}")
            posts.append((None, text, img_urls))

    return posts


# ─── Comment Scraper ──────────────────────────────────

def get_post_urls_from_feed(page) -> list:
    """
    Ambil URL postingan dari halaman grup saat ini.
    Trick: <a href="/groups/.../posts/..."> selalu ada di DOM bahkan
    sebelum React hydration selesai — href adalah static attribute.
    """
    urls = page.evaluate("""
        () => {
            const seen  = new Set();
            const result = [];
            // Cari semua link ke halaman post
            const links = document.querySelectorAll(
                'a[href*="/groups/"][href*="/posts/"],' +
                'a[href*="story_fbid="]'
            );
            for (const a of links) {
                let href = a.href || '';
                // Normalkan: hapus query string kecuali story_fbid
                if (href.includes('story_fbid=')) {
                    // sudah ada ID di query — biarkan
                } else {
                    href = href.split('?')[0];  // buang ?comment_id= dll
                }
                if (href && !seen.has(href)) {
                    seen.add(href);
                    result.push(href);
                }
                if (result.length >= 50) break;
            }
            return result;
        }
    """)
    return urls or []


def scrape_comments_for_listings(page, post_url: str) -> list:
    """
    Buka satu post Facebook, extract:
    1. Isi post UTAMA (kalau itu listing kos langsung)
    2. Komentar yang merupakan penawaran kos
    Returns list of (None, text, img_urls).
    """
    print(f"      💬 Buka post: {post_url[-40:]}")
    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(3)
    except Exception as e:
        print(f"         ⚠️ Gagal buka: {e}")
        return []

    # Klik "Lihat semua komentar" kalau ada
    for btn_text in ["Lihat semua komentar", "View all comments",
                     "Lihat lebih banyak komentar", "View more comments"]:
        try:
            btn = page.get_by_text(btn_text, exact=False).first
            if btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(2)
        except Exception:
            pass

    # Scroll supaya semua konten ter-load
    for _ in range(8):
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(1.2)

    results = []
    main_post_saved = False

    # ── Coba ambil post utama via DOM dulu (lebih reliable untuk video post) ──
    try:
        articles = page.query_selector_all('div[role="article"]')
        for art in articles:
            txt = page.evaluate("(el) => el.innerText || ''", art).strip()
            if not txt or len(txt) < 30:
                continue
            # Artikel pertama yang cukup panjang di halaman post = post utama
            if not main_post_saved and len(txt) > 50:
                # Cek apakah ini relevan (keyword atau harga)
                if contains_keyword(txt) or has_offering_signal(txt):
                    if not is_seeking_post(txt):
                        img_urls = get_post_photo_urls(page, art)
                        print(f"         📄 Post utama (DOM): {txt[:60].strip()!r}")
                        results.append((None, txt[:2000], img_urls))
                        main_post_saved = True
                        break
    except Exception as e:
        print(f"         ⚠️ DOM extract gagal: {e}")

    # ── Fallback + komentar via script tags ───────────────────────────────────
    all_entries = _extract_from_scripts(page)

    for entry in all_entries:
        _, text, img_urls = entry
        if not text or len(text) < 20:
            continue
        if is_seeking_post(text):
            continue
        if not contains_keyword(text):
            continue

        if not main_post_saved:
            print(f"         📄 Post utama (JSON): {text[:60].strip()!r}")
            results.append((None, text, img_urls))
            main_post_saved = True
        else:
            if has_offering_signal(text) and len(text) >= 30:
                results.append((None, text, img_urls))

        if len(results) >= MAX_COMMENTS_PER_POST + 1:
            break

    print(f"         📋 {len(results)} entry (post+komentar) ditemukan")
    return results


# ─── Main Scraper ──────────────────────────────────────

def scrape_groups():
    print("\n🚀 Mulai scraping Facebook Groups...")

    with sync_playwright() as p:
        import sys as _sys
        session_json  = "data/fb_session.json"
        has_local_dir = os.path.exists("data/browser_session/Default")
        # Headless kalau tidak ada display (server/Docker) — macOS tidak butuh DISPLAY
        is_headless   = not bool(os.environ.get("DISPLAY")) and _sys.platform != "darwin"

        if os.path.exists(session_json):
            # Mode server: pakai storage_state JSON (2KB, hasil export dari lokal)
            print(f"   🔑 Muat session dari {session_json}")
            _browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            browser = _browser.new_context(
                storage_state=session_json,
                viewport={"width": 1280, "height": 800},
            )
        elif has_local_dir:
            # Mode lokal: pakai persistent user_data_dir (bisa login manual)
            print("   🖥️ Pakai browser_session lokal")
            browser = p.chromium.launch_persistent_context(
                user_data_dir="data/browser_session",
                headless=is_headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 800},
            )
        else:
            print("❌ Session Facebook tidak ditemukan!")
            print("   Jalankan dulu di lokal: python3 facebook.py")
            print("   Lalu upload: scp data/fb_session.json root@server:/data/bantukos/fb_session.json")
            return

        page = browser.new_page()
        total_new = 0

        for idx, group_url in enumerate(FACEBOOK_GROUPS):
            if total_new >= MAX_POSTS_PER_CYCLE:
                print(f"\n⏹️ Batas {MAX_POSTS_PER_CYCLE} post tercapai.")
                break

            group_name = group_url.rstrip("/").split("/")[-1]
            print(f"\n📂 [{idx+1}/{len(FACEBOOK_GROUPS)}] Grup: {group_name}")

            try:
                # Buka grup dulu
                page.goto(group_url.rstrip("/"), wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(3, 5))

                # Handle login
                if "login" in page.url or "checkpoint" in page.url:
                    if is_headless:
                        print("❌ Session Facebook expired atau ditolak (IP server berbeda).")
                        print("   Di lokal: python3 facebook.py --export-session")
                        print("   Lalu: scp data/fb_session.json root@server:/data/bantukos/fb_session.json")
                        return
                    print("⚠️ Facebook minta login manual...")
                    print("   Login di browser yang terbuka, lalu tekan Enter.")
                    input()
                    page.goto(group_url.rstrip("/"), wait_until="domcontentloaded", timeout=30000)
                    time.sleep(4)
                    # Simpan session ke JSON kecil — untuk deploy berikutnya
                    try:
                        browser.storage_state(path="data/fb_session.json")
                        print("   💾 Session disimpan ke data/fb_session.json")
                    except Exception:
                        pass

                if "groups" not in page.url:
                    print("   ⚠️ Tidak bisa masuk grup, skip.")
                    continue

                # Klik tab Diskusi untuk masuk ke feed postingan
                print("   🔍 Mencari tab Diskusi...")
                clicked_tab = False
                for tab_text in ["Diskusi", "Discussion", "Posts"]:
                    try:
                        tab = page.get_by_role("tab", name=tab_text)
                        if tab.count() > 0:
                            tab.first.click()
                            clicked_tab = True
                            print(f"   ✅ Klik tab: {tab_text}")
                            time.sleep(3)
                            break
                    except:
                        pass

                if not clicked_tab:
                    # Coba link teks langsung
                    for label in ["Diskusi", "Discussion"]:
                        try:
                            link = page.get_by_text(label, exact=True).first
                            link.click()
                            clicked_tab = True
                            time.sleep(3)
                            break
                        except:
                            pass

                # Ubah sorting ke Postingan Terbaru
                print("   🔃 Ubah ke postingan terbaru...")
                for sort_text in ["Postingan Terbaru", "Newest Posts", "Terbaru"]:
                    try:
                        sort_btn = page.get_by_text(sort_text, exact=False).first
                        if sort_btn.is_visible():
                            sort_btn.click()
                            time.sleep(2)
                            print(f"   ✅ Sort by: {sort_text}")
                            break
                    except:
                        pass

                # ── Progressive scroll & collect ──────────────────────────────
                # Facebook pakai virtual scroll: artikel hanya ada di DOM
                # saat sedang terlihat di viewport. Jadi kita harus collect
                # sambil scroll, bukan setelah balik ke atas.
                print("   📜 Progressive scroll & collect (40 langkah)...")
                time.sleep(4)

                comment_patterns = ["Suka Balas Bagikan", "Like · Reply", "Balas Bagikan",
                                     "Like\nReply", "Suka\nBalas"]
                seen_keys  = set()   # dedup artikel
                seen_urls  = set()   # dedup URL post
                collected  = {}      # key -> (element, text)
                feed_urls_live = []  # kumpulkan URL post sepanjang scroll
                no_new_streak  = 0
                MIN_SCROLLS = 12     # minimal scroll sebelum boleh early-stop

                for step in range(40):
                    time.sleep(random.uniform(1.8, 2.8))

                    # Kumpulkan URL post selama scroll (lebih banyak = lebih banyak Pass 2)
                    new_urls = page.evaluate("""
                        () => {
                            const seen = new Set();
                            const out  = [];
                            for (const a of document.querySelectorAll(
                                    'a[href*="/groups/"][href*="/posts/"], a[href*="story_fbid="]')) {
                                let h = a.href || '';
                                if (!h.includes('story_fbid=')) h = h.split('?')[0];
                                if (h && !seen.has(h)) { seen.add(h); out.push(h); }
                                if (out.length >= 80) break;
                            }
                            return out;
                        }
                    """)
                    for u in (new_urls or []):
                        if u not in seen_urls:
                            seen_urls.add(u)
                            feed_urls_live.append(u)

                    arts = page.query_selector_all('div[role="article"]')
                    new_this_step = 0
                    for art in arts:
                        try:
                            txt = page.evaluate("(el) => el.innerText || ''", art).strip()
                            if not txt or len(txt) < 15:
                                continue
                            if any(cp in txt for cp in comment_patterns) and len(txt) < 400:
                                continue
                            key = txt[:120]
                            if key not in seen_keys:
                                seen_keys.add(key)
                                collected[key] = (art, txt)
                                new_this_step += 1
                                print(f"      📌 [{step}] {txt[:60].strip()!r}")
                        except Exception:
                            continue

                    if new_this_step == 0:
                        no_new_streak += 1
                    else:
                        no_new_streak = 0

                    print(f"      [scroll {step+1}] articles={len(collected)} urls={len(feed_urls_live)}")

                    if len(collected) >= MAX_POSTS_PER_GROUP:
                        print(f"   ✅ Sudah {len(collected)} postingan, stop scroll.")
                        break

                    # Early-stop hanya setelah minimum scroll DAN ada artikel sebelumnya
                    if step >= MIN_SCROLLS and no_new_streak >= 8 and len(collected) > 0:
                        print(f"   ⏹️ Tidak ada artikel baru setelah 8 langkah, stop.")
                        break

                    page.evaluate("window.scrollBy(0, 900)")

                posts = list(collected.values())

                # ── Gabungkan URL dari scroll live + scan akhir ────────────────
                extra_urls = get_post_urls_from_feed(page)
                for u in extra_urls:
                    if u not in seen_urls:
                        seen_urls.add(u)
                        feed_urls_live.append(u)
                feed_post_urls = feed_urls_live
                print(f"   🔗 URL post ditemukan di feed: {len(feed_post_urls)}")

                # ── Fallback: parse script tag JSON ───────────────────────────
                if not posts:
                    print("   🔄 Fallback: extract teks dari script tag JSON...")
                    posts = _extract_from_scripts(page)
                    print(f"      Script parsing: {len(posts)} postingan ditemukan")

                if not posts and not feed_post_urls:
                    print("   ⚠️ Tidak ada postingan ditemukan.")
                    page.screenshot(path=f"data/debug_{group_name}.png")
                    print(f"      Screenshot: data/debug_{group_name}.png")
                    continue

                print(f"   📋 {len(posts)} postingan ditemukan, proses max {MAX_POSTS_PER_GROUP}")

                # ── Helper: proses satu entry post/komentar ────────────────────
                def process_entry(entry, require_offering: bool = False) -> bool:
                    """
                    Proses satu entry, simpan ke DB jika valid.
                    require_offering=True: wajib ada sinyal harga/kontak/penawaran
                    (dipakai untuk komentar agar tidak ikut ambil teks non-listing).
                    """
                    nonlocal total_new, group_new
                    if len(entry) == 3:
                        post_el, text, extra_img_urls = entry
                    else:
                        post_el, text = entry
                        extra_img_urls = []

                    if len(text) < 15:
                        return False
                    if not contains_keyword(text):
                        return False
                    if is_seeking_post(text):
                        return False
                    # Komentar/post via Pass 2: wajib punya sinyal penawaran
                    if require_offering:
                        if not has_offering_signal(text):
                            return False
                        # Min length: 30 char cukup (listing singkat seperti "Sesetan. 1jt.")
                        if len(text) < 30:
                            return False
                        # Kalau contains_keyword sudah lolos (kos/lokasi/dll),
                        # kos_re tidak wajib lagi — hindari false negative
                        kos_re = re.compile(r'\b(?:kos|kost|kontrakan|kamar|sewa|ngekos|'
                                            r'disewakan|tersedia|available|kosong|siap huni)\b',
                                            re.IGNORECASE)
                        # Wajib kos_re HANYA kalau tidak ada keyword lokasi spesifik
                        loc_re = re.compile(
                            r'\b(?:sesetan|renon|gatsu|sanur|kuta|canggu|seminyak|denpasar|'
                            r'ubud|jimbaran|kerobokan|berawa|mengwi|tabanan|bypass|panjer|'
                            r'kesiman|pemogan|padangsambian|monang|imam bonjol|tohpati)\b',
                            re.IGNORECASE)
                        if not kos_re.search(text) and not loc_re.search(text):
                            return False

                    post_id = hashlib.md5(text[:200].encode()).hexdigest()
                    if is_duplicate(post_id):
                        return False

                    price    = extract_price(text)
                    contact  = extract_contact(text)
                    location = extract_location(text)

                    img_paths = []
                    ocr_text  = ""
                    if post_el is not None:
                        img_paths, ocr_text = process_post_images(page, post_el, post_id)
                    elif extra_img_urls:
                        for i, url in enumerate(extra_img_urls[:5]):
                            name = f"{hashlib.md5(post_id.encode()).hexdigest()[:8]}_{i}.jpg"
                            path = os.path.join(IMAGES_DIR, name)
                            if download_image_via_playwright(page, url, path):
                                img_paths.append(path)
                                print(f"   📷 Foto {i+1} OK ({os.path.getsize(path)//1024}KB): {name}")
                                # OCR pada foto pertama kalau teks post pendek (flyer)
                                if i == 0 and len(text) < 80:
                                    ot = ocr_image(path)
                                    if ot and is_kos_flyer(ot):
                                        ocr_text = ot
                                        print(f"   🔡 OCR flyer: {ot[:80].strip()!r}")

                    # Gabungkan teks post + OCR kalau ada
                    final_text = text
                    if ocr_text and len(ocr_text) > len(text):
                        final_text = text + "\n\n[dari gambar]\n" + ocr_text

                    saved_id = save_post(post_id, final_text[:2000], location, price, contact, img_paths)
                    if saved_id:
                        total_new += 1
                        group_new += 1
                        print(f"   ✅ [{location}] {price} | {len(img_paths)} foto | {text[:60].strip()}...")
                        return True
                    return False

                # ── Pass 1: proses post utama dari feed ─────────────────────
                group_new = 0
                seeking_urls = []   # URL seeking posts untuk dicek komentarnya

                for entry in posts:
                    if group_new >= MAX_POSTS_PER_GROUP or total_new >= MAX_POSTS_PER_CYCLE:
                        break
                    try:
                        # Unpack text untuk cek apakah seeking
                        text_check = entry[1] if len(entry) >= 2 else ""
                        if is_seeking_post(text_check) or not contains_keyword(text_check):
                            # Skip tapi catat: seeking post mungkin punya komentar listing
                            # Kita tidak tahu URL-nya dari text saja — gunakan feed_post_urls
                            pass
                        else:
                            process_entry(entry)
                    except Exception as e:
                        print(f"   ❌ Error pass 1: {e}")

                # ── Pass 2: scrape komentar dari URL post (seeking post → reply) ─
                if feed_post_urls and total_new < MAX_POSTS_PER_CYCLE:
                    print(f"\n   💬 Pass 2: cek komentar dari {min(len(feed_post_urls), 40)} post...")
                    checked = 0
                    for post_url in feed_post_urls[:40]:
                        if group_new >= MAX_POSTS_PER_GROUP or total_new >= MAX_POSTS_PER_CYCLE:
                            break
                        try:
                            comment_entries = scrape_comments_for_listings(page, post_url)
                            for entry in comment_entries:
                                if group_new >= MAX_POSTS_PER_GROUP:
                                    break
                                # require_offering=True: komentar harus punya harga/kontak/penawaran
                                process_entry(entry, require_offering=True)
                            checked += 1
                            # Jeda singkat antar post
                            time.sleep(random.uniform(2, 4))
                        except Exception as e:
                            print(f"   ❌ Error komentar {post_url[-30:]}: {e}")
                        # Balik ke halaman grup setelah cek komentar
                        if checked < len(feed_post_urls[:15]):
                            try:
                                page.go_back(wait_until="domcontentloaded", timeout=15000)
                                time.sleep(2)
                            except Exception:
                                pass

                print(f"   📊 Grup ini: {group_new} postingan baru")

                if idx < len(FACEBOOK_GROUPS) - 1:
                    wait = random.randint(30, 90)
                    print(f"   ⏳ Jeda {wait}s sebelum grup berikutnya...")
                    time.sleep(wait)

            except Exception as e:
                print(f"❌ Error buka grup {group_url}: {e}")
                continue

        browser.close()
        print(f"\n✅ Scraping selesai. Total baru: {total_new} postingan")
        return total_new

if __name__ == "__main__":
    scrape_groups()
