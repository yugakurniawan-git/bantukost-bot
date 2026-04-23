"""
Test upload foto ke Instagram.
Jalankan: python3 test_post.py
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("INSTAGRAM_ACCESS_TOKEN")
IG_ID   = os.getenv("INSTAGRAM_BUSINESS_ID")
API_URL = f"https://graph.instagram.com/v21.0/{IG_ID}"

# Foto test — gambar publik sederhana
TEST_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/640px-Camponotus_flavomarginatus_ant.jpg"

TEST_CAPTION = """🔍 Sebelum DP kos, pastikan kondisinya sesuai ekspektasi!

Banyak yang menyesal setelah bayar — kamar gelap, WiFi lemot, air mati.

Kami hadir untuk cek kondisi aslinya sebelum kamu memutuskan. 📋

📍 Area Bali (Canggu, Seminyak, Kuta, Denpasar & sekitarnya)
⚡ Laporan dalam 24 jam
📹 Video real tanpa edit

DM kami atau kunjungi bantukos.id untuk info lebih lanjut! 🙌

#bantukos #koskosan #sewakamar #kosanbali #infokos #baliliving
#canggu #seminyak #denpasar #perantaubali #pindahkebali #digitalnomad"""

def test_upload():
    print("="*50)
    print("  Test Upload Instagram — Bantu Kos")
    print("="*50)

    # Step 1: Buat container
    print("\n📦 Step 1: Membuat media container...")
    res1 = requests.post(
        f"{API_URL}/media",
        data={
            "image_url":    TEST_IMAGE_URL,
            "caption":      TEST_CAPTION,
            "access_token": TOKEN,
        }
    )
    data1 = res1.json()

    if "id" not in data1:
        print(f"❌ Gagal buat container: {data1}")
        return

    container_id = data1["id"]
    print(f"✅ Container ID: {container_id}")

    # Step 2: Tunggu Meta proses gambar
    print("\n⏳ Step 2: Tunggu 8 detik (Meta proses gambar)...")
    time.sleep(8)

    # Step 3: Publish
    print("\n📤 Step 3: Publishing ke Instagram...")
    res2 = requests.post(
        f"{API_URL}/media_publish",
        data={
            "creation_id":  container_id,
            "access_token": TOKEN,
        }
    )
    data2 = res2.json()

    if "id" in data2:
        print(f"\n✅ BERHASIL! Post ID: {data2['id']}")
        print(f"   Cek Instagram @bantukos sekarang!")
    else:
        print(f"\n❌ Gagal publish: {data2}")

if __name__ == "__main__":
    test_upload()
