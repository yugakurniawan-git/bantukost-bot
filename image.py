from PIL import Image, ImageDraw, ImageFont
import os
import textwrap
from datetime import datetime
from config import WATERMARK_TEXT

def add_watermark(image_path: str, location: str = "", price: str = "") -> str:
    """
    Tambahkan location banner + watermark ke foto.
    Banner bawah: lokasi spesifik + CTA DM bantukos.
    """
    try:
        img    = Image.open(image_path).convert("RGBA")
        width, height = img.size

        # Resize ke format Instagram (max 1080px)
        max_size = 1080
        if width > max_size or height > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            width, height = img.size

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)

        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        font_paths_reg = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        def lf(size, bold=True):
            for fp in (font_paths if bold else font_paths_reg):
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
            return ImageFont.load_default()

        # ── Location banner bawah ───────────────────────────────────────────
        banner_h = max(70, height // 10)
        banner_y = height - banner_h

        # Background gelap semi-transparan
        draw.rectangle([0, banner_y, width, height], fill=(0, 0, 0, 195))

        f_loc  = lf(max(18, width // 35))
        f_cta  = lf(max(14, width // 50), bold=False)
        f_brand = lf(max(14, width // 55), bold=False)

        # Lokasi (kiri)
        loc_text = location[:55] if location and location.lower() not in ("bali", "") else ""
        if loc_text:
            draw.text((16, banner_y + 10), f"Lokasi: {loc_text}", font=f_loc, fill=(255, 255, 255, 240))
            draw.text((16, banner_y + banner_h - 24), "dm @bantukos untuk info & kontak pemilik",
                      font=f_cta, fill=(180, 210, 255, 220))
        else:
            draw.text((16, banner_y + 14), "dm @bantukos untuk info lokasi & kontak pemilik",
                      font=f_cta, fill=(255, 255, 255, 240))

        # Brand kanan bawah
        brand_text = "@bantukos"
        brand_bbox = draw.textbbox((0, 0), brand_text, font=f_brand)
        bw = brand_bbox[2] - brand_bbox[0]
        draw.text((width - bw - 14, banner_y + banner_h - 22),
                  brand_text, font=f_brand, fill=(56, 189, 248, 220))

        result = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        base, _ = os.path.splitext(image_path)
        output_path = f"{base}_wm.jpg"
        result.save(output_path, "JPEG", quality=90)
        return output_path

    except Exception as e:
        print(f"⚠️ Gagal watermark {image_path}: {e}")
        return image_path

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
    Buat listing card branded bantukos.com sebagai fallback kalau tidak ada foto dari FB.
    Desain: clean property card — tidak ada ilustrasi/gambar kartun.
    """
    try:
        W, H = 1080, 1080
        img  = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        ORANGE = (234, 88, 12)
        NAVY   = (15, 25, 50)
        WHITE  = (255, 255, 255)
        GRAY   = (110, 110, 120)
        LGRAY  = (230, 230, 235)

        # ── Fonts ─────────────────────────────────────────────────────────
        font_bold = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        font_reg = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        def lf(size, bold=True):
            for fp in (font_bold if bold else font_reg):
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    pass
            return ImageFont.load_default()

        # ── TOP: warm cream gradient background (0-620) ───────────────────
        for y in range(620):
            t = y / 620
            r = int(250 - 15 * t)
            g = int(246 - 22 * t)
            b = int(238 - 35 * t)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Subtle dot grid
        for gx in range(40, W, 60):
            for gy in range(40, 620, 60):
                draw.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=(215, 208, 195))

        # Soft warm glow circle in centre
        for rad in range(200, 0, -8):
            c = 248 - (200 - rad) // 12
            draw.ellipse([W//2 - rad, 170 - rad, W//2 + rad, 170 + rad],
                         fill=(min(255, c + 4), min(255, c - 2), max(0, c - 25)))

        # ── Header bar ────────────────────────────────────────────────────
        draw.rectangle([0, 0, W, 88], fill=NAVY)
        f_brand = lf(40)
        draw.text((54, 23), "bantukos", font=f_brand, fill=ORANGE)
        bx = 54 + int(draw.textlength("bantukos", font=f_brand))
        draw.text((bx, 23), ".com", font=f_brand, fill=WHITE)

        tag_w = 250
        tx = W - tag_w - 50
        draw.rounded_rectangle([tx, 25, tx + tag_w, 63], radius=6, fill=ORANGE)
        draw.text((tx + tag_w // 2, 44), "KAMAR TERSEDIA", font=lf(22), fill=WHITE, anchor="mm")

        # ── "foto belum tersedia" badge ───────────────────────────────────
        badge_txt = "foto belum tersedia"
        f_badge = lf(22, bold=False)
        bw = int(draw.textlength(badge_txt, font=f_badge)) + 32
        bx1 = (W - bw) // 2
        draw.rounded_rectangle([bx1, 108, bx1 + bw, 148], radius=6, fill=(240, 232, 218))
        draw.rectangle([bx1, 108, bx1 + bw, 148], outline=(200, 172, 130), width=0)
        draw.text((W // 2, 128), badge_txt, font=f_badge, fill=(155, 125, 85), anchor="mm")

        # ── Location as hero text ─────────────────────────────────────────
        loc_display = location.strip() if location and location.lower() not in ("bali", "") else "Bali"
        loc_lines = textwrap.wrap(loc_display, width=18)
        f_loc_big = lf(86)
        total_h = len(loc_lines[:2]) * 102
        loc_y = max(175, 290 - total_h // 2)
        for line in loc_lines[:2]:
            lw = int(draw.textlength(line, font=f_loc_big))
            draw.text(((W - lw) // 2, loc_y), line, font=f_loc_big, fill=NAVY)
            loc_y += 102

        # Tagline
        tag_txt = "kos di Bali  —  harga terjangkau"
        f_tag = lf(28, bold=False)
        tw = int(draw.textlength(tag_txt, font=f_tag))
        draw.text(((W - tw) // 2, loc_y + 16), tag_txt, font=f_tag, fill=(148, 125, 98))

        # ── Orange bar with price ─────────────────────────────────────────
        draw.rectangle([0, 572, W, 620], fill=ORANGE)
        price_display = price.strip() if price else "Hubungi pemilik"
        f_pbar = lf(30)
        draw.text((54, 583), "Harga sewa:", font=f_pbar, fill=WHITE)
        pw = int(draw.textlength("Harga sewa:", font=f_pbar))
        draw.text((54 + pw + 18, 583), price_display, font=f_pbar, fill=(255, 218, 175))

        # ── Bottom info card (620-1080) ───────────────────────────────────
        draw.rectangle([0, 620, W, H], fill=WHITE)
        for i in range(5):
            shadow_c = 195 + i * 8
            draw.line([(0, 620 + i), (W, 620 + i)], fill=(shadow_c, shadow_c - 5, shadow_c - 12))

        pad = 60

        # Price (large)
        draw.text((pad, 642), "Harga sewa", font=lf(26, bold=False), fill=GRAY)
        draw.text((pad, 680), price_display, font=lf(70), fill=ORANGE)

        # Divider
        draw.line([(pad, 778), (W - pad, 778)], fill=LGRAY, width=2)

        # CTA
        draw.text((pad, 802), "Info lengkap & nomor pemilik:", font=lf(30, bold=False), fill=GRAY)
        draw.text((pad, 845), "DM @bantukos", font=lf(54), fill=NAVY)
        draw.text((pad, 916), "di Instagram / bantukos.com", font=lf(30, bold=False), fill=GRAY)

        # Footer
        draw.rectangle([0, H - 72, W, H], fill=NAVY)
        draw.text((pad, H - 50), "bantukos.com", font=lf(28, bold=False), fill=ORANGE)
        draw.text((W - pad, H - 50), "kos di Bali, cek sebelum DP",
                  font=lf(26, bold=False), fill=(158, 173, 205), anchor="ra")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, "JPEG", quality=92)
        print(f"   🖼️ Fallback image dibuat: {output_path}")
        return output_path

    except Exception as e:
        print(f"   ⚠️ Gagal buat fallback image: {e}")
        return ""

def create_mamikos_info_card(
    name: str,
    price: str,
    location: str,
    facilities: list,
    rating: str = "",
    unit_type: str = "",
    post_id: str = "card",
) -> str:
    """
    Buat info card branded bantukos sebagai slide PERTAMA untuk post Mamikos.
    Ini yang bikin konten Instagram berbeda dari Mamikos — visual curated dari bantukos.
    Return path file gambar.
    """
    W, H = 1080, 1080
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # ── Background gradient gelap ──────────────────────────────────────────
    for y in range(H):
        r = int(10  + 8  * (y / H))
        g = int(10  + 15 * (y / H))
        b = int(25  + 30 * (y / H))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── Fonts ──────────────────────────────────────────────────────────────
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
    ]
    def load_font(size):
        for fp in font_paths:
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
        return ImageFont.load_default()

    f_brand  = load_font(34)
    f_tag    = load_font(24)
    f_name   = load_font(52)
    f_price  = load_font(62)
    f_loc    = load_font(28)
    f_fac    = load_font(26)
    f_small  = load_font(22)

    # ── Accent bar kiri ─────────────────────────────────────────────────
    draw.rectangle([0, 0, 6, H], fill=(56, 189, 248))

    # ── Header: logo bantukos ─────────────────────────────────────────────
    draw.text((60, 55), "bantukos", font=f_brand, fill=(56, 189, 248))
    draw.text((60, 93), ".id", font=f_tag, fill=(100, 180, 220))

    # Tag "LISTING VERIFIED"
    tag_x, tag_y = W - 240, 55
    draw.rounded_rectangle([tag_x, tag_y, tag_x + 175, tag_y + 38],
                            radius=8, fill=(56, 189, 248, 200))
    draw.text((tag_x + 88, tag_y + 19), "LISTING VERIFIED",
              font=f_small, fill=(10, 20, 40), anchor="mm")

    # Tanggal update
    today = datetime.now()
    month_names = ["Jan","Feb","Mar","Apr","Mei","Jun",
                   "Jul","Agu","Sep","Okt","Nov","Des"]
    date_str = f"Update {today.day} {month_names[today.month-1]} {today.year}"
    draw.text((W - 50, 100), date_str, font=f_small,
              fill=(120, 160, 190), anchor="ra")

    # ── Divider ────────────────────────────────────────────────────────────
    draw.line([(55, 145), (W - 55, 145)], fill=(40, 70, 100), width=1)

    # ── Nama kos ──────────────────────────────────────────────────────────
    name_clean = name[:45] + ("…" if len(name) > 45 else "")
    draw.text((60, 175), name_clean, font=f_name, fill=(240, 248, 255))

    # Unit type badge
    if unit_type:
        draw.rounded_rectangle([60, 240, 60 + len(unit_type)*14 + 24, 275],
                                radius=6, fill=(30, 60, 100))
        draw.text((72, 257), unit_type, font=f_small, fill=(180, 220, 255), anchor="lm")

    # ── Harga (focal point) ────────────────────────────────────────────────
    price_clean = price.replace("/bulan", "").replace("Rp ", "Rp").strip()
    draw.text((60, 295), price_clean, font=f_price, fill=(56, 189, 248))
    draw.text((60 + draw.textlength(price_clean, font=f_price) + 10, 340),
              "/ bulan", font=f_loc, fill=(120, 160, 190))

    # Rating (kalau ada)
    if rating and rating not in ("0", "0.0", ""):
        rating_x = W - 50
        draw.text((rating_x, 310), f"⭐ {rating}", font=f_loc,
                  fill=(255, 210, 80), anchor="ra")

    # ── Divider ────────────────────────────────────────────────────────────
    draw.line([(55, 390), (W - 55, 390)], fill=(40, 70, 100), width=1)

    # ── Lokasi ────────────────────────────────────────────────────────────
    loc_short = location[:55] + ("…" if len(location) > 55 else "")
    draw.text((60, 415), f"📍  {loc_short}", font=f_loc, fill=(180, 210, 240))

    # ── Fasilitas ─────────────────────────────────────────────────────────
    draw.text((60, 465), "Fasilitas unggulan:", font=f_small, fill=(100, 140, 180))

    fac_icons = {"WiFi": "📶", "AC": "❄️", "K. Mandi Dalam": "🚿",
                 "Kasur": "🛏️", "Kulkas": "🧊", "Dapur": "🍳",
                 "Parkir": "🚗", "Akses 24 Jam": "🔑"}
    fac_list  = facilities[:6] if facilities else []
    cols, rows_per = 2, 3
    fac_start_y = 500
    for i, fac in enumerate(fac_list):
        col = i % cols
        row = i // cols
        icon  = fac_icons.get(fac, "✓")
        label = f"{icon} {fac}"[:28]
        fx = 60  + col * 510
        fy = fac_start_y + row * 48
        draw.rounded_rectangle([fx - 4, fy - 8, fx + 480, fy + 32],
                                radius=6, fill=(20, 40, 70))
        draw.text((fx + 10, fy + 12), label, font=f_fac,
                  fill=(220, 235, 255), anchor="lm")

    # ── Divider ────────────────────────────────────────────────────────────
    div_y = fac_start_y + (((len(fac_list) - 1) // cols) + 1) * 48 + 20
    div_y = max(div_y, 680)
    draw.line([(55, div_y), (W - 55, div_y)], fill=(40, 70, 100), width=1)

    # ── Footer CTA ─────────────────────────────────────────────────────────
    cta_y = div_y + 35
    draw.text((60, cta_y),
              "Mau tahu kondisi aslinya sebelum DP?",
              font=f_fac, fill=(180, 210, 240))
    draw.text((60, cta_y + 45),
              "Slide foto →  atau  DM kita buat info lengkap",
              font=f_fac, fill=(120, 160, 190))

    # Brand bottom-right
    draw.text((W - 50, H - 45), "@bantukos", font=f_fac,
              fill=(56, 189, 248), anchor="ra")

    # ── Simpan ─────────────────────────────────────────────────────────────
    os.makedirs("data/images", exist_ok=True)
    out = f"data/images/card_{post_id}.jpg"
    img.save(out, "JPEG", quality=92)
    return out


if __name__ == "__main__":
    # Test watermark
    test_files = [f for f in os.listdir("data/images") if f.endswith(".jpg") and "_wm" not in f]
    if test_files:
        result = add_watermark(f"data/images/{test_files[0]}")
        print(f"✅ Test watermark berhasil: {result}")
    else:
        print("ℹ️ Tidak ada foto untuk di-test.")
