"""
Script untuk dapat Instagram Access Token.
Jalankan SEKALI untuk setup, token disimpan ke .env

Cara pakai:
1. Isi APP_ID dan APP_SECRET di bawah
2. Jalankan: python3 get_token.py
3. Buka URL yang muncul di browser
4. Login Instagram, izinkan akses
5. Copy token yang muncul, paste ke .env
"""

import http.server
import threading
import webbrowser
import urllib.parse
import requests

# ─── ISI INI DULU ─────────────────────────────────────
APP_ID     = "1694193314945915"
APP_SECRET = "93c6099e88d356f04b7a2a49da764b1d"
# ──────────────────────────────────────────────────────

REDIRECT_URI  = "http://localhost:8000/callback"
SCOPES        = "instagram_business_basic,instagram_business_content_publish"
AUTH_URL      = (
    f"https://api.instagram.com/oauth/authorize"
    f"?client_id={APP_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&scope={SCOPES}"
    f"&response_type=code"
)

auth_code = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Berhasil! Kamu bisa tutup tab ini.</h2>")
            print(f"\n✅ Authorization code didapat!")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>Gagal. Coba lagi.</h2>")

    def log_message(self, format, *args):
        pass  # suppress log

def get_short_lived_token(code):
    res = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id":     APP_ID,
            "client_secret": APP_SECRET,
            "grant_type":    "authorization_code",
            "redirect_uri":  REDIRECT_URI,
            "code":          code,
        }
    )
    data = res.json()
    if "access_token" in data:
        return data["access_token"], data.get("user_id")
    print(f"❌ Gagal dapat short token: {data}")
    return None, None

def get_long_lived_token(short_token):
    res = requests.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type":        "ig_exchange_token",
            "client_secret":     APP_SECRET,
            "access_token":      short_token,
        }
    )
    data = res.json()
    if "access_token" in data:
        return data["access_token"]
    print(f"❌ Gagal dapat long token: {data}")
    return None

def main():
    print("=" * 55)
    print("  Bantu Kos — Instagram Token Setup")
    print("=" * 55)

    if APP_ID == "INSTAGRAM_APP_ID_KAMU":
        print("\n⚠️  Isi dulu APP_ID dan APP_SECRET di file ini!")
        return

    # Jalankan local server di background
    server = http.server.HTTPServer(("localhost", 8000), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    # Buka browser otomatis
    print(f"\n🌐 Membuka browser untuk login Instagram...")
    print(f"   Kalau tidak terbuka otomatis, buka URL ini:\n   {AUTH_URL}\n")
    webbrowser.open(AUTH_URL)

    # Tunggu callback
    thread.join(timeout=120)

    if not auth_code:
        print("❌ Timeout. Coba jalankan ulang script ini.")
        return

    # Tukar code → short token
    print("🔄 Menukar code dengan access token...")
    short_token, user_id = get_short_lived_token(auth_code)
    if not short_token:
        return

    # Tukar short → long lived token (60 hari)
    print("🔄 Menukar ke long-lived token (60 hari)...")
    long_token = get_long_lived_token(short_token)
    if not long_token:
        return

    print("\n" + "=" * 55)
    print("✅ BERHASIL! Simpan info berikut ke file .env kamu:")
    print("=" * 55)
    print(f"\nINSTAGRAM_ACCESS_TOKEN={long_token}")
    print(f"INSTAGRAM_BUSINESS_ID={user_id}")
    print("\n⚠️  Token berlaku 60 hari. Jalankan script ini lagi")
    print("   sebelum expired untuk refresh.\n")

if __name__ == "__main__":
    main()
