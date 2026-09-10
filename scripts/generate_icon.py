#!/usr/bin/env python3
"""Generate the Morning Brief app icon (a sunrise, matching the menu-bar glyph)
and compile it into mac/MorningBrief/Resources/AppIcon.icns.

Requires Pillow (`pip install pillow`) and the macOS `sips`/`iconutil` tools.
Run from anywhere; paths are resolved relative to this script.

    python3 scripts/generate_icon.py
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ICNS_OUT = ROOT / "mac" / "MorningBrief" / "Resources" / "AppIcon.icns"
SIZE = 1024


def build_master() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Vertical sky gradient: deep indigo night -> warm dawn orange/gold.
    top, mid, bot_hi = (30, 26, 74), (120, 60, 90), (255, 176, 59)
    grad = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        t = y / (SIZE - 1)
        if t < 0.55:
            tt = t / 0.55
            c = [top[i] + (mid[i] - top[i]) * tt for i in range(3)]
        else:
            tt = (t - 0.55) / 0.45
            c = [mid[i] + (bot_hi[i] - mid[i]) * tt for i in range(3)]
        grad.putpixel((0, y), tuple(int(v) for v in c))
    img.paste(grad.resize((SIZE, SIZE)), (0, 0))

    cx, cy = SIZE * 0.5, SIZE * 0.62  # sun center, near the horizon

    # Soft glow behind the sun.
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for rad, alpha in [(430, 40), (360, 55), (300, 70)]:
        gdraw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(255, 214, 120, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img, "RGBA")

    # Sun rays (alternating long/short).
    n_rays, r_inner, r_outer = 12, 205, 330
    for i in range(n_rays):
        ang = (2 * math.pi / n_rays) * i
        w = 20 if i % 2 == 0 else 13
        length = r_outer if i % 2 == 0 else r_outer - 40
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        p1 = (cx + dx * r_inner + px * w, cy + dy * r_inner + py * w)
        p2 = (cx + dx * r_inner - px * w, cy + dy * r_inner - py * w)
        p3 = (cx + dx * length, cy + dy * length)
        draw.polygon([p1, p3, p2], fill=(255, 226, 150, 235))

    # Sun disc: vertical-gradient band masked to a circle.
    r_sun = 200
    band = Image.new("RGB", (1, r_sun * 2))
    for y in range(r_sun * 2):
        t = y / (r_sun * 2 - 1)
        band.putpixel((0, y), (255, int(240 - 70 * t), int(150 - 100 * t)))
    band_full = band.resize((r_sun * 2, r_sun * 2))
    mask = Image.new("L", (r_sun * 2, r_sun * 2), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, r_sun * 2, r_sun * 2], fill=255)
    disc = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    disc.paste(band_full, (int(cx - r_sun), int(cy - r_sun)), mask)
    img = Image.alpha_composite(img, disc)

    draw = ImageDraw.Draw(img, "RGBA")
    draw.ellipse([cx - r_sun, cy - r_sun, cx + r_sun, cy + r_sun], outline=(255, 250, 220, 160), width=6)

    # macOS-style rounded-square mask (~22.5% corner radius).
    radius = int(SIZE * 0.225)
    mask_full = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask_full).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=radius, fill=255)
    final = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    final.paste(img, (0, 0), mask_full)
    return final


def build_icns(master_png: Path, out_icns: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "MorningBrief.iconset"
        iconset.mkdir()
        sizes = [16, 32, 64, 128, 256, 512]
        for s in sizes:
            subprocess.run(["sips", "-z", str(s), str(s), str(master_png), "--out", str(iconset / f"icon_{s}x{s}.png")],
                           check=True, capture_output=True)
        # @2x variants (256 doubles 128, etc.) plus the 1024 @2x of 512.
        mapping = {"icon_16x16@2x.png": 32, "icon_32x32@2x.png": 64, "icon_128x128@2x.png": 256, "icon_256x256@2x.png": 512}
        for name, s in mapping.items():
            subprocess.run(["sips", "-z", str(s), str(s), str(master_png), "--out", str(iconset / name)],
                           check=True, capture_output=True)
        shutil.copy(master_png, iconset / "icon_512x512@2x.png")
        out_icns.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out_icns)], check=True)


def main() -> None:
    master = build_master()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        master.save(f.name)
        master_path = Path(f.name)
    try:
        build_icns(master_path, ICNS_OUT)
    finally:
        master_path.unlink(missing_ok=True)
    print(f"Wrote {ICNS_OUT}")


if __name__ == "__main__":
    main()
