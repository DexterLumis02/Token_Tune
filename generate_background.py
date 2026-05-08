#!/usr/bin/env python3
"""
Generate a polished dark UI background image for the RFID Music Player.

Writes: ui_generated.png
Does not overwrite existing assets.
"""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


W, H = 720, 900
OUT = Path(__file__).resolve().parent / "ui_generated.png"


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp3(c1, c2, t: float):
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
    )


def main() -> int:
    random.seed(7)

    # Base vertical gradient (deep navy -> blue-black)
    top = (10, 18, 35)
    bot = (6, 10, 18)
    base = Image.new("RGB", (W, H), top)
    px = base.load()
    for y in range(H):
        t = y / (H - 1)
        col = _lerp3(top, bot, t)
        for x in range(W):
            px[x, y] = col

    # Soft diagonal light sweep
    sweep = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(sweep)
    for i in range(6):
        pad = 220 + i * 45
        sd.ellipse((-pad, int(H * 0.05) - pad, int(W * 0.75) + pad, int(H * 0.65) + pad), fill=20 + i * 10)
    sweep = sweep.filter(ImageFilter.GaussianBlur(70))

    sweep_rgb = Image.merge("RGB", (sweep, sweep, sweep))
    base = Image.blend(base, sweep_rgb, 0.18)

    # Subtle noise texture (kept low to avoid banding)
    noise = Image.effect_noise((W, H), 18).convert("L")
    noise = noise.filter(ImageFilter.GaussianBlur(0.6))
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    base = Image.blend(base, noise_rgb, 0.06)

    # Accent bokeh/glows
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)

    accents = [
        ((90, 160), 210, (79, 163, 255, 110)),
        ((610, 220), 180, (49, 215, 163, 95)),
        ((560, 720), 240, (44, 107, 255, 80)),
        ((140, 760), 260, (255, 90, 120, 60)),
    ]
    for (cx, cy), r, col in accents:
        gd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)

    glow = glow.filter(ImageFilter.GaussianBlur(55))
    base_rgba = base.convert("RGBA")
    base_rgba = Image.alpha_composite(base_rgba, glow)

    # Very subtle grid lines for depth
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gr = ImageDraw.Draw(grid)
    for x in range(0, W, 48):
        gr.line((x, 0, x, H), fill=(255, 255, 255, 10), width=1)
    for y in range(0, H, 48):
        gr.line((0, y, W, y), fill=(255, 255, 255, 10), width=1)
    grid = grid.filter(ImageFilter.GaussianBlur(0.3))
    base_rgba = Image.alpha_composite(base_rgba, grid)

    # Vignette
    vign = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vign)
    vd.ellipse((-int(W * 0.15), -int(H * 0.10), int(W * 1.15), int(H * 1.10)), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(90))
    vign = Image.eval(vign, lambda p: int(p * 0.85))
    vign_rgba = Image.merge("RGBA", (Image.new("L", (W, H), 0),) * 3 + (Image.eval(vign, lambda p: 255 - p),))
    base_rgba = Image.alpha_composite(base_rgba, vign_rgba)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    base_rgba.convert("RGB").save(OUT, format="PNG", optimize=True)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

