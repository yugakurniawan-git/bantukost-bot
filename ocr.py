"""
OCR untuk extract teks dari gambar flyer/poster kos di Facebook.
Dipakai saat post body kosong tapi ada gambar dengan teks (harga, lokasi, no telp).
"""
import re

_reader = None
_ocr_available = False

def _get_reader():
    global _reader, _ocr_available
    if _reader is not None:
        return _reader
    try:
        import easyocr
        _reader = easyocr.Reader(['id', 'en'], gpu=False, verbose=False)
        _ocr_available = True
        print("   🔡 OCR (easyocr) siap")
    except ImportError:
        _ocr_available = False
    return _reader


def ocr_image(image_path: str) -> str:
    """
    Extract teks dari gambar. Return string kosong kalau OCR tidak tersedia atau gagal.
    """
    reader = _get_reader()
    if reader is None:
        return ""
    try:
        results = reader.readtext(image_path, detail=0, paragraph=True)
        return "\n".join(results)
    except Exception as e:
        print(f"   ⚠️ OCR gagal: {e}")
        return ""


def is_kos_flyer(text: str) -> bool:
    """
    Cek apakah teks hasil OCR kemungkinan adalah flyer kos:
    harus ada minimal (harga/bulan ATAU nomor HP) DAN kata kunci lokasi/kos.
    """
    if not text or len(text) < 15:
        return False

    has_price = bool(re.search(
        r'(?:\d[\d.,]*\s*(?:juta|jt|rb|ribu|k)\b|/\s*(?:bulan|bln)|rp[\s.]*\d)',
        text, re.IGNORECASE
    ))
    has_phone = bool(re.search(r'(?:08|62|\+62)\d{7,}', text))
    has_kos   = bool(re.search(
        r'\b(?:kos|kost|kamar|sewa|kontrakan|tersedia|available|disewakan|'
        r'sesetan|renon|gatsu|canggu|seminyak|kuta|denpasar|sanur|ubud|'
        r'jimbaran|kerobokan|berawa|mengwi|tabanan)\b',
        text, re.IGNORECASE
    ))

    return has_kos and (has_price or has_phone)
