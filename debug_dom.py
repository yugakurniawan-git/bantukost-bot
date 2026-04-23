"""
Debug script: cari selector yang bisa ambil teks post Facebook Groups.
Jalankan: python3 debug_dom.py
"""
import time
import random
from playwright.sync_api import sync_playwright
from config import FACEBOOK_GROUPS

GROUP_URL = FACEBOOK_GROUPS[0]

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir="data/browser_session",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
    )
    page = browser.new_page()

    print(f"🌐 Buka: {GROUP_URL}")
    page.goto(GROUP_URL.rstrip("/"), wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    if "login" in page.url or "checkpoint" in page.url:
        print("⚠️ Perlu login. Login dulu lalu tekan Enter...")
        input()
        page.goto(GROUP_URL.rstrip("/"), wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

    # Klik Diskusi + sort Terbaru
    for tab_text in ["Diskusi", "Discussion", "Posts"]:
        try:
            tab = page.get_by_role("tab", name=tab_text)
            if tab.count() > 0:
                tab.first.click()
                print(f"✅ Tab: {tab_text}")
                time.sleep(3)
                break
        except:
            pass

    for sort_text in ["Postingan Terbaru", "Newest Posts", "Terbaru"]:
        try:
            btn = page.get_by_text(sort_text, exact=False).first
            if btn.is_visible():
                btn.click()
                print(f"✅ Sort: {sort_text}")
                time.sleep(2)
                break
        except:
            pass

    # Scroll lebih banyak
    print("📜 Scrolling 20x...")
    for i in range(20):
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(random.uniform(0.8, 1.5))
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(3)

    # ── Debug 1: role="article" ────────────────────────────────────────────────
    print("\n" + "="*60)
    print("DEBUG 1: div[role='article']")
    articles = page.query_selector_all('div[role="article"]')
    print(f"  Ditemukan: {len(articles)}")
    for i, art in enumerate(articles[:5]):
        txt = page.evaluate("(el) => el.innerText || ''", art).strip()
        html_len = page.evaluate("(el) => el.innerHTML.length", art)
        bbox = art.bounding_box()
        print(f"  [{i}] text={len(txt)}chars | html={html_len}chars | bbox={bbox}")
        if txt:
            print(f"       TEKS: {txt[:100]!r}")

    # ── Debug 2: Semua elemen dengan teks panjang ─────────────────────────────
    print("\n" + "="*60)
    print("DEBUG 2: Elemen dengan innerText > 50 char (max 10)")
    result = page.evaluate("""
        () => {
            const out = [];
            const all = document.querySelectorAll('*');
            for (const el of all) {
                // skip body/html, hanya leaf-ish containers
                const children = el.children.length;
                if (children > 30) continue;
                const txt = (el.innerText || '').trim();
                if (txt.length > 80 && txt.length < 2000 && children < 10) {
                    const role = el.getAttribute('role') || '';
                    const tag = el.tagName;
                    const id = el.id || '';
                    const cls = (el.className || '').toString().slice(0, 60);
                    const dataKeys = Array.from(el.attributes)
                        .filter(a => a.name.startsWith('data-'))
                        .map(a => a.name)
                        .join(',');
                    out.push({ role, tag, id, cls, dataKeys, txtLen: txt.length, txt: txt.slice(0, 100) });
                    if (out.length >= 10) break;
                }
            }
            return out;
        }
    """)
    for item in result:
        print(f"  <{item['tag']} role={item['role']!r} data=[{item['dataKeys'][:40]}]>")
        print(f"       {item['txtLen']}chars: {item['txt']!r}")

    # ── Debug 3: Cari teks "kos" di DOM ───────────────────────────────────────
    print("\n" + "="*60)
    print("DEBUG 3: Elemen yang mengandung kata 'kos'")
    kos_result = page.evaluate("""
        () => {
            const out = [];
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null
            );
            let node;
            while (node = walker.nextNode()) {
                const txt = node.textContent.trim();
                if (txt.toLowerCase().includes('kos') && txt.length > 20) {
                    let el = node.parentElement;
                    // naik sampai elemen yang cukup besar
                    while (el && (el.innerText || '').length < 50) {
                        el = el.parentElement;
                    }
                    if (!el) continue;
                    const role = el.getAttribute('role') || '';
                    const tag = el.tagName;
                    const dataKeys = Array.from(el.attributes)
                        .filter(a => a.name.startsWith('data-'))
                        .map(a => a.name)
                        .slice(0, 5)
                        .join(',');
                    const innerTxt = (el.innerText || '').slice(0, 150);
                    out.push({ tag, role, dataKeys, innerTxt });
                    if (out.length >= 5) break;
                }
            }
            return out;
        }
    """)
    print(f"  Ditemukan: {len(kos_result)} elemen")
    for item in kos_result:
        print(f"  <{item['tag']} role={item['role']!r} data=[{item['dataKeys']}]>")
        print(f"       {item['innerTxt']!r}")

    # ── Debug 4: aria-posinset & data-pagelet ─────────────────────────────────
    print("\n" + "="*60)
    print("DEBUG 4: Selector alternatif")
    for sel in ['[aria-posinset]', '[data-pagelet*="Feed"]', '[data-ad-comet-preview]',
                '[data-testid*="post"]', 'div[data-fte-impdep]']:
        els = page.query_selector_all(sel)
        print(f"  {sel!r}: {len(els)} elemen")
        if els:
            txt = page.evaluate("(el) => (el.innerText || '').slice(0, 80)", els[0]).strip()
            print(f"       pertama: {txt!r}")

    print("\n✅ Debug selesai. Periksa output di atas.")
    input("Tekan Enter untuk tutup browser...")
    browser.close()
