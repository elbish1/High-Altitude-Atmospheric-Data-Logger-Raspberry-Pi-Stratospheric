# =============================================================================
# camera.py — Simulated camera (Windows)
#
# On a real Pi this calls picamera2 to capture a JPEG.
# On Windows it creates a small PNG image using only the stdlib (no Pillow
# needed) so you can see files appearing in the photos/ folder just like
# a real flight would produce.
# =============================================================================

import os
import struct
import zlib
from datetime import datetime

from config import PHOTO_DIR


def init_camera() -> bool:
    os.makedirs(PHOTO_DIR, exist_ok=True)
    # Avoid non-ASCII glyphs to keep Windows console encodings happy.
    print(f"[Camera SIM] Ready - fake images -> {PHOTO_DIR}")
    return True


def capture_image(altitude_m=None, timeout_sec=5) -> str | None:
    """
    Write a minimal valid PNG file to photos/.
    The image is a solid colour that shifts with altitude —
    dark blue at ground, lighter/white as altitude increases.
    This lets you verify the photo pipeline without a real camera.
    """
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    alt_tag = f"_{int(altitude_m)}m" if altitude_m is not None else ""
    path    = os.path.join(PHOTO_DIR, f"img_{ts}{alt_tag}.png")

    # Colour: dark blue (ground) → cyan → white (stratosphere)
    alt = min(altitude_m or 0, 32000)
    frac = alt / 32000.0
    r = int(frac * 200)
    g = int(frac * 230)
    b = int(100 + frac * 155)

    _write_png(path, width=64, height=64, r=r, g=g, b=b,
               label_alt=int(alt))
    return path


def close_camera():
    print("[Camera SIM] Closed.")


# ── Minimal PNG writer (no external libraries) ────────────────────────────────

def _write_png(path: str, width: int, height: int,
               r: int, g: int, b: int, label_alt: int):
    """
    Write a plain-colour PNG using only Python stdlib (struct + zlib).
    Each pixel is the (r, g, b) colour supplied.
    """
    def _u32(n):
        return struct.pack(">I", n)

    def _chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return _u32(len(data)) + c + _u32(zlib.crc32(c) & 0xFFFFFFFF)

    # IHDR: width, height, bit depth=8, colour type=2 (RGB), rest 0
    ihdr = _chunk(b"IHDR",
                  struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    # Raw image data: each row starts with filter byte 0
    raw_rows = b""
    for _ in range(height):
        raw_rows += b"\x00" + bytes([r, g, b] * width)

    idat = _chunk(b"IDAT", zlib.compress(raw_rows))
    iend = _chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend)
