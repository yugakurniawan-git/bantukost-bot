"""
Debug Mamikos: intercept API calls — tampilkan SEMUA XHR/fetch ke mamikos.com/garuda
"""
import json, time
from playwright.sync_api import sync_playwright

api_calls = []
api_responses = {}

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="id-ID",
    )
    page = ctx.new_page()

    # Intercept hanya request ke garuda API
    def on_response(resp):
        url = resp.url
        if 'garuda' in url and resp.status == 200:
            api_calls.append(url)
            print(f"  ✅ garuda API: {url[:120]}")
            try:
                body = resp.json()
                api_responses[url] = body
            except Exception:
                pass

    page.on("response", on_response)

    # Buka homepage dulu
    print("🌐 Buka mamikos.com...")
    page.goto("https://mamikos.com", wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # Coba navigate ke halaman Denpasar Bali
    print("\n🔍 Navigate ke halaman kos Bali...")
    # Coba beberapa format URL
    for test_url in [
        "https://mamikos.com/kost-denpasar-bali-murah",
        "https://mamikos.com/kost/denpasar-bali",
        "https://mamikos.com/cari?q=denpasar+bali",
    ]:
        print(f"   Mencoba: {test_url}")
        try:
            page.goto(test_url, wait_until="networkidle", timeout=20000)
            time.sleep(4)
            title = page.title()
            print(f"   Title: {title}")
            if "Tidak Ditemukan" not in title and "404" not in title:
                print(f"   ✅ URL valid!")
                break
        except Exception as e:
            print(f"   ❌ {e}")

    page.screenshot(path="data/debug_mamikos_landing.png")

    # Scroll untuk load lebih banyak
    for _ in range(8):
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(0.8)
    time.sleep(3)

    # Lihat link kos di halaman
    kos_links = page.evaluate("""
        () => {
            const all = document.querySelectorAll('a[href]');
            return [...new Set(Array.from(all)
                .map(a => a.href)
                .filter(h => h.includes('mamikos.com/kos/') || h.includes('mamikos.com/kost/'))
            )].slice(0, 10);
        }
    """)
    print(f"\n🏠 Link kos ditemukan: {kos_links}")

    # Lihat API responses
    print(f"\n📊 Garuda API calls ({len(api_calls)}):")
    for url in api_calls[:10]:
        data = api_responses.get(url, {})
        keys = list(data.keys())[:8] if isinstance(data, dict) else type(data).__name__
        print(f"  • {url[-60:]}")
        print(f"    keys: {keys}")

    # Simpan responses untuk analisa
    with open("data/mamikos_garuda_responses.json", "w") as f:
        # Simpan versi terpotong
        trimmed = {url: str(data)[:500] for url, data in api_responses.items()}
        json.dump(trimmed, f, indent=2)
    print("\n💾 data/mamikos_garuda_responses.json")

    ctx.close()
    browser.close()
    print("\n✅ Selesai")
