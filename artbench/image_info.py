"""Texture size and format from the first bytes of the file, standard library only: PNG, JPEG, TGA, PSD and BMP.
Anything else, or a file that does not parse, is None."""
import os
import struct

JPEG_SCAN = 1 << 20                   # bytes read looking for a JPEG's frame header (it follows the metadata blocks)


def read(path):
    """{"width", "height", "format"} or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
                w, h = struct.unpack(">II", head[16:24])
                return _info(w, h, "PNG")
            if head[:2] == b"\xff\xd8":
                f.seek(0)
                return _jpeg(f.read(JPEG_SCAN))
            if head[:4] == b"8BPS":
                h, w = struct.unpack(">II", head[14:22])
                return _info(w, h, "PSD")
            if head[:2] == b"BM" and len(head) >= 26:
                w, h = struct.unpack("<ii", head[18:26])
                return _info(w, abs(h), "BMP")
            if os.path.splitext(path)[1].lower() == ".tga" and len(head) >= 18 and head[2] in (1, 2, 3, 9, 10, 11):
                w, h = struct.unpack("<HH", head[12:16])
                return _info(w, h, "TGA")
    except (OSError, struct.error):
        return None
    return None


def _info(w, h, fmt):
    return {"width": w, "height": h, "format": fmt} if w > 0 and h > 0 else None


def _jpeg(data):
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:      # markers without a length
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return _info(w, h, "JPEG")
        i += 2 + length
    return None
