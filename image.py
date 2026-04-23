from PIL import Image, ImageDraw, ImageFont
import os
from config import WATERMARK_TEXT

def add_watermark(image_path: str) -> str:
    """
    Tambahkan watermark 'bantukos.id' ke foto.
    Return path file hasil watermark.
    """
    try:
        img    = Image.open(image_path).convert("RGBA")
        width, height = img.size

        # Resize ke format Instagram (max 1080px)
        max_size = 1080
        if width > max_size or height > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            width, height = img.size

        # Buat layer untuk watermark
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)

        # Coba load font, fallback ke default kalau tidak ada
        font_size = max(20, width // 25)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except:
            font = ImageFont.load_default()

        text = f"📍 {WATERMARK_TEXT}"

        # Ukuran teks
        bbox    = draw.textbbox((0, 0), text, font=font)
        tw, th  = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Posisi: pojok kanan bawah
        margin = 15
        x = width - tw - margin
        y = height - th - margin

        # Background semi-transparan di belakang teks
        padding = 8
        draw.rectangle(
            [x - padding, y - padding, x + tw + padding, y + th + padding],
            fill=(0, 0, 0, 160)
        )

        # Tulis teks
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 230))

        # Gabungkan
        result = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        # Simpan dengan suffix _wm
        base, ext  = os.path.splitext(image_path)
        output_path = f"{base}_wm.jpg"
        result.save(output_path, "JPEG", quality=90)

        return output_path

    except Exception as e:
        print(f"⚠️ Gagal watermark {image_path}: {e}")
        return image_path  # return original kalau gagal

def process_images(image_paths: list) -> list:
    """Proses semua foto: watermark dan resize."""
    processed = []
    for path in image_paths:
        if os.path.exists(path):
            wm_path = add_watermark(path)
            processed.append(wm_path)
            print(f"   🖼️ Watermark: {os.path.basename(wm_path)}")
    return processed

def create_fallback_image(location: str, price: str, output_path: str = "data/images/fallback.jpg") -> str:
    """
    Buat gambar branded Bantu Kos sebagai fallback kalau tidak ada foto dari FB.
    """
    try:
        W, H = 1080, 1080
        img  = Image.new("RGB", (W, H), color=(8, 12, 20))  # dark background
        draw = ImageDraw.Draw(img)

        # Gradient overlay (simulate)
        for y in range(H):
            alpha = int(30 * (y / H))
            draw.line([(0, y), (W, y)], fill=(alpha, alpha + 10, alpha + 30))

        # Load font (fallback ke default)
        try:
            font_big   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 72)
            font_med   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        except:
            font_big = font_med = font_small = ImageFont.load_default()

        # Logo / Brand
        draw.text((W//2, 200), "🔍", font=font_big, anchor="mm", fill=(56, 189, 248))
        draw.text((W//2, 300), "Bantu Kos", font=font_big, anchor="mm", fill=(255, 255, 255))
        draw.text((W//2, 390), "bantukos.id", font=font_med, anchor="mm", fill=(56, 189, 248))

        # Divider
        draw.line([(140, 450), (W-140, 450)], fill=(255, 255, 255, 30), width=1)

        # Info kos
        draw.text((W//2, 530), f"📍 {location}", font=font_med, anchor="mm", fill=(200, 220, 240))
        draw.text((W//2, 610), f"💰 {price}", font=font_med, anchor="mm", fill=(200, 220, 240))

        # Divider
        draw.line([(140, 680), (W-140, 680)], fill=(255, 255, 255, 30), width=1)

        # CTA
        draw.text((W//2, 760), "Cek kondisi aslinya sebelum DP!", font=font_small, anchor="mm", fill=(148, 163, 184))
        draw.text((W//2, 820), "DM kami untuk info inspeksi 🏠", font=font_small, anchor="mm", fill=(148, 163, 184))

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, "JPEG", quality=90)
        print(f"   🖼️ Fallback image dibuat: {output_path}")
        return output_path

    except Exception as e:
        print(f"   ⚠️ Gagal buat fallback image: {e}")
        return ""

if __name__ == "__main__":
    # Test watermark
    test_files = [f for f in os.listdir("data/images") if f.endswith(".jpg") and "_wm" not in f]
    if test_files:
        result = add_watermark(f"data/images/{test_files[0]}")
        print(f"✅ Test watermark berhasil: {result}")
    else:
        print("ℹ️ Tidak ada foto untuk di-test.")
