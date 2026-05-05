import requests
import time
import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID
from database import mark_posted

load_dotenv()

cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure     = True
)

GRAPH_URL = "https://graph.instagram.com/v21.0"

def _is_rate_limited(response: dict) -> bool:
    err = response.get("error", {})
    return err.get("code") == 4 or err.get("error_subcode") == 2207051


def upload_single_photo(image_url: str, caption: str):
    """
    Upload 1 foto ke Instagram via Meta Graph API.
    Return: True = sukses, False = error, None = rate limited (stop batch).
    """
    # Step 1: Buat media container
    res = requests.post(
        f"{GRAPH_URL}/{INSTAGRAM_BUSINESS_ID}/media",
        data={
            "image_url": image_url,
            "caption":   caption,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
    )
    data = res.json()
    if "id" not in data:
        if _is_rate_limited(data):
            print(f"⏳ Rate limit Instagram — akan dicoba di siklus berikutnya.")
            return None
        print(f"❌ Gagal buat container: {data}")
        return False

    container_id = data["id"]
    print(f"   📦 Container ID: {container_id}")

    time.sleep(5)

    # Step 2: Publish
    res2 = requests.post(
        f"{GRAPH_URL}/{INSTAGRAM_BUSINESS_ID}/media_publish",
        data={
            "creation_id":  container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
    )
    result = res2.json()
    if "id" in result:
        print(f"   ✅ Berhasil publish! Post ID: {result['id']}")
        return True
    if _is_rate_limited(result):
        # Container sudah dibuat & dikirim ke IG — kemungkinan besar sudah dipublish.
        # Return True agar mark_posted dipanggil dan post tidak diulang di siklus berikutnya.
        print(f"⏳ Rate limit saat publish — dianggap berhasil untuk cegah duplikat.")
        return True
    print(f"   ❌ Gagal publish: {result}")
    return False

def upload_carousel(image_urls: list, caption: str):
    """
    Upload carousel (banyak foto) ke Instagram.
    Return: True = sukses, False = error, None = rate limited (stop batch).
    """
    # Step 1: Buat container untuk tiap foto
    item_ids = []
    for url in image_urls[:10]:  # Instagram max 10
        res = requests.post(
            f"{GRAPH_URL}/{INSTAGRAM_BUSINESS_ID}/media",
            data={
                "image_url":    url,
                "is_carousel_item": True,
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            }
        )
        data = res.json()
        if "id" in data:
            item_ids.append(data["id"])
            print(f"   📷 Item container: {data['id']}")
        elif _is_rate_limited(data):
            print(f"⏳ Rate limit Instagram — akan dicoba di siklus berikutnya.")
            return None
        time.sleep(2)

    if not item_ids:
        print("❌ Tidak ada item yang berhasil dibuat.")
        return False

    # Step 2: Buat carousel container
    res2 = requests.post(
        f"{GRAPH_URL}/{INSTAGRAM_BUSINESS_ID}/media",
        data={
            "media_type":   "CAROUSEL",
            "children":     ",".join(item_ids),
            "caption":      caption,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
    )
    carousel_data = res2.json()
    if "id" not in carousel_data:
        if _is_rate_limited(carousel_data):
            print(f"⏳ Rate limit Instagram — akan dicoba di siklus berikutnya.")
            return None
        print(f"❌ Gagal buat carousel: {carousel_data}")
        return False

    carousel_id = carousel_data["id"]
    time.sleep(5)

    # Step 3: Publish carousel
    res3 = requests.post(
        f"{GRAPH_URL}/{INSTAGRAM_BUSINESS_ID}/media_publish",
        data={
            "creation_id":  carousel_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
    )
    result = res3.json()
    if "id" in result:
        print(f"   ✅ Carousel berhasil! Post ID: {result['id']}")
        return True
    if _is_rate_limited(result):
        # Carousel container sudah dibuat & dikirim — kemungkinan besar sudah dipublish.
        # Return True agar mark_posted dipanggil dan post tidak diulang di siklus berikutnya.
        print(f"⏳ Rate limit saat publish carousel — dianggap berhasil untuk cegah duplikat.")
        return True
    print(f"   ❌ Gagal publish carousel: {result}")
    return False

def post_to_instagram(post_id: int, image_urls: list, caption: str) -> bool:
    """
    Entry point upload ke Instagram.
    Otomatis pilih single atau carousel.

    CATATAN: image_urls harus URL publik (bukan path lokal).
    Untuk sekarang kita perlu hosting foto dulu.
    Solusi sementara: pakai imgbb.com API (gratis).
    """
    print(f"\n📤 Upload ke Instagram (post DB ID: {post_id})...")

    if not image_urls:
        print("⚠️ Tidak ada foto, skip upload.")
        return False

    if len(image_urls) == 1:
        result = upload_single_photo(image_urls[0], caption)
    else:
        result = upload_carousel(image_urls, caption)

    if result is True:
        mark_posted(post_id)

    return result  # True | False | None

def upload_to_cloudinary(image_path: str) -> str:
    """
    Upload foto ke Cloudinary — URL-nya diterima oleh Instagram API.
    Daftar gratis di: cloudinary.com (25GB/bulan gratis)
    """
    try:
        result = cloudinary.uploader.upload(
            image_path,
            folder="bantukos",
            resource_type="image"
        )
        url = result.get("secure_url", "")
        if url:
            print(f"   ☁️ Cloudinary: {url[:60]}...")
        return url
    except Exception as e:
        print(f"   ⚠️ Cloudinary gagal: {e}")
        return ""
