"""Cinematic Marathi posters: sunset construction-site background + glass cards + phone mock-up with REAL app content.

The text is always drawn by us (AI image models misspell Marathi), so the background picture never contains words.
No Play Store badges, no invented numbers or win probabilities.
"""
from __future__ import annotations

import io
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1080, 1350
NAVY, BLUE, GOLD, WHITE = (11, 42, 74), (21, 96, 168), (255, 159, 28), (255, 255, 255)

BACKGROUND_PROMPT = (
    "Photorealistic cinematic golden-hour construction site in Maharashtra, India: a tower crane, an under-construction "
    "highway flyover with concrete pillars, a yellow excavator, a few workers in white helmets and high-visibility vests "
    "seen from behind, dramatic warm sunset sky with clouds, dust in the air. Vertical composition. "
    "Keep the middle of the image calmer and darker. No text, no letters, no logos, no signs, no watermark, no brand names."
)

TILES = ["शोध", "बिड रेट", "मंजुरी", "व्हॉल्ट", "GST", "AI सहाय्यक"]


class PosterUnavailable(RuntimeError):
    pass


def _fonts():
    from PIL import ImageFont, features
    bold, regular = FONT_DIR / "Poppins-Bold.ttf", FONT_DIR / "Poppins-Regular.ttf"
    if not (bold.exists() and regular.exists()):
        raise PosterUnavailable("fonts missing")
    if not features.check("raqm"):
        raise PosterUnavailable("raqm text layout not available (Marathi would render incorrectly)")
    return (lambda size: ImageFont.truetype(str(bold), size)), (lambda size: ImageFont.truetype(str(regular), size))


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while draw.textlength(word, font=font) > max_width and len(word) > 1:
            cut = len(word) - 1
            while cut > 1 and draw.textlength(word[:cut], font=font) > max_width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def _clip(draw, text, font, max_width, max_lines):
    lines = _wrap(draw, text, font, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" …") + "…"
    return lines


def fallback_background() -> "Image.Image":
    """Vector sunset with crane, flyover and building silhouettes (used when no AI picture is available)."""
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    stops = [(0.0, (12, 26, 58)), (0.40, (70, 58, 104)), (0.60, (232, 120, 60)), (0.68, (255, 170, 60)), (1.0, (28, 22, 36))]
    for y in range(H):
        t = y / (H - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                d.line([(0, y), (W, y)], fill=tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3)))
                break
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W // 2 - 330, int(H * 0.60) - 180, W // 2 + 330, int(H * 0.60) + 180), fill=(255, 150, 40))
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L").filter(ImageFilter.GaussianBlur(120))), 0.55)
    d = ImageDraw.Draw(img)
    dark, ground = (20, 20, 30), int(H * 0.80)
    for x, w, h in [(40, 90, 210), (150, 70, 150), (230, 110, 260), (360, 80, 170), (470, 100, 120)]:   # buildings
        d.rectangle((x, ground - h, x + w, ground), fill=dark)
    d.rectangle((560, ground - 150, W, ground - 118), fill=dark)                                          # flyover slab
    for x in range(600, W, 150):
        d.rectangle((x, ground - 118, x + 34, ground), fill=dark)
    cx = 820                                                                                              # tower crane
    d.rectangle((cx, ground - 560, cx + 20, ground), fill=dark)
    d.rectangle((cx - 230, ground - 560, cx + 210, ground - 544), fill=dark)
    d.polygon([(cx - 8, ground - 560), (cx + 10, ground - 620), (cx + 28, ground - 560)], fill=dark)
    d.line([(cx + 10, ground - 620), (cx - 230, ground - 548)], fill=dark, width=3)
    d.line([(cx + 10, ground - 620), (cx + 210, ground - 548)], fill=dark, width=3)
    d.line([(cx - 190, ground - 544), (cx - 190, ground - 400)], fill=dark, width=3)
    d.rectangle((cx - 215, ground - 400, cx - 165, ground - 372), fill=dark)
    d.rectangle((0, ground, W, H), fill=(18, 16, 24))
    d.polygon([(120, ground), (300, ground), (330, ground - 70), (240, ground - 70), (200, ground - 120), (150, ground - 70), (110, ground - 70)], fill=dark)  # excavator
    return img


def _cover(img, width, height):
    from PIL import Image
    scale = max(width / img.width, height / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    return img.crop((left, top, left + width, top + height))


def _vertical_shade(top_alpha, bottom_alpha, top_end, bottom_start):
    from PIL import Image, ImageDraw
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(H):
        if y < top_end:
            a = int(top_alpha * (1 - y / top_end))
        elif y > bottom_start:
            a = int(bottom_alpha * ((y - bottom_start) / (H - bottom_start)))
        else:
            a = 40
        d.line([(0, y), (W, y)], fill=(6, 14, 30, a))
    return layer


def _glass(canvas, box, radius, fill, outline=None, width=2):
    """Translucent rounded rectangle composited on the canvas."""
    from PIL import Image, ImageDraw
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(layer)


def _phone(canvas, bold, regular, rows, x, y, w=410, h=600):
    from PIL import Image, ImageDraw, ImageFilter
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x + 10, y + 24, x + w + 10, y + h + 24), radius=58, fill=(0, 0, 0, 150))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(canvas, "RGBA")
    d.rounded_rectangle((x, y, x + w, y + h), radius=58, fill=(8, 10, 18, 255), outline=(90, 110, 150, 255), width=3)
    sx, sy, sw, sh = x + 14, y + 14, w - 28, h - 28
    d.rounded_rectangle((sx, sy, sx + sw, sy + sh), radius=46, fill=(13, 35, 68, 255))
    d.rounded_rectangle((x + w // 2 - 46, y + 24, x + w // 2 + 46, y + 44), radius=10, fill=(8, 10, 18, 255))
    d.rounded_rectangle((sx + 22, sy + 66, sx + 62, sy + 106), radius=11, fill=WHITE)
    d.text((sx + 33, sy + 70), "T", font=bold(32), fill=NAVY)
    d.text((sx + 74, sy + 68), "TenderBot AI", font=bold(28), fill=WHITE)
    if rows:
        d.text((sx + 24, sy + 124), "ताजे टेंडर", font=bold(26), fill=GOLD)
        yy = sy + 168
        for row in rows[:3]:
            _glass(canvas, (sx + 18, yy, sx + sw - 18, yy + 112), 20, (255, 255, 255, 34), (255, 255, 255, 70), 1)
            d = ImageDraw.Draw(canvas)
            f = regular(22)
            ty = yy + 10
            for line in _clip(d, row["title"], f, sw - 70, 2):
                d.text((sx + 32, ty), line, font=f, fill=WHITE)
                ty += 29
            if row.get("date"):
                d.text((sx + 32, yy + 112 - 33), f"शेवट: {row['date']}", font=regular(20), fill=GOLD)
            yy += 124
    else:
        d.text((sx + 24, sy + 124), "आज काय करायचे?", font=bold(26), fill=GOLD)
        colors = [(56, 189, 248), (74, 222, 128), (251, 191, 36), (244, 114, 182), (167, 139, 250), (148, 163, 184)]
        for i, label in enumerate(TILES):
            cx, cy = sx + 18 + (i % 2) * ((sw - 36) // 2 + 4), sy + 168 + (i // 2) * 124
            _glass(canvas, (cx, cy, cx + (sw - 36) // 2 - 4, cy + 112), 20, (255, 255, 255, 34), (255, 255, 255, 70), 1)
            d = ImageDraw.Draw(canvas)
            d.ellipse((cx + 16, cy + 14, cx + 54, cy + 52), fill=colors[i] + (255,))
            d.text((cx + 16, cy + 64), label, font=regular(24), fill=WHITE)


def render_poster_pro(headline: str, card_points: list[str], note: str | None, link: str,
                      rows: list[dict] | None = None, background: bytes | None = None) -> bytes:
    from PIL import Image, ImageDraw
    bold, regular = _fonts()
    if background:
        try:
            base = _cover(Image.open(io.BytesIO(background)).convert("RGB"), W, H)
        except Exception:
            base = fallback_background()
    else:
        base = fallback_background()
    canvas = base.convert("RGBA")
    canvas.alpha_composite(_vertical_shade(215, 230, 560, 880))
    d = ImageDraw.Draw(canvas, "RGBA")

    # brand
    d.rounded_rectangle((60, 54, 156, 150), radius=24, fill=BLUE + (255,), outline=WHITE + (255,), width=3)
    d.rectangle((84, 78, 132, 92), fill=WHITE)
    d.rectangle((102, 92, 114, 130), fill=WHITE)
    d.rectangle((84, 136, 132, 142), fill=GOLD)
    d.text((176, 56), "TenderBot AI", font=bold(60), fill=WHITE)
    d.text((178, 126), "कंत्राटदारांसाठी AI सहाय्यक", font=regular(30), fill=(255, 205, 120))

    # headline: first line white, the rest gold
    size = 90
    while True:
        hf = bold(size)
        lines = _wrap(d, headline, hf, W - 120)
        if len(lines) <= 3 or size <= 56:
            break
        size -= 6
    y = 210
    for i, line in enumerate(lines[:3]):
        d.text((60, y), line, font=hf, fill=WHITE if i == 0 else GOLD)
        y += int(size * 1.42)

    # glass cards (left)
    top = max(y + 30, 520)
    card_font, cy = regular(32), top
    for point in card_points[:3]:
        text_lines = _clip(d, point, card_font, 380, 3)
        ch = len(text_lines) * 44 + 40
        _glass(canvas, (60, cy, 560, cy + ch), 26, (255, 255, 255, 40), (255, 255, 255, 110), 2)
        d = ImageDraw.Draw(canvas)
        d.ellipse((82, cy + 22, 112, cy + 52), fill=GOLD + (255,))
        d.line([(89, cy + 37), (94, cy + 44), (104, cy + 30)], fill=NAVY + (255,), width=5)
        for j, line in enumerate(text_lines):
            d.text((128, cy + 16 + j * 44), line, font=card_font, fill=WHITE)
        cy += ch + 20

    _phone(canvas, bold, regular, rows, x=610, y=455)
    d = ImageDraw.Draw(canvas, "RGBA")

    # call to action
    if note:
        nf = regular(26)
        d.text((60, H - 262), _clip(d, note, nf, W - 120, 1)[0], font=nf, fill=(205, 220, 240))
    d.rounded_rectangle((60, H - 214, W - 60, H - 100), radius=40, fill=GOLD + (255,))
    cta, cf = "१५ दिवस मोफत ट्रायल", bold(58)
    d.text(((W - d.textlength(cta, font=cf)) / 2, H - 196), cta, font=cf, fill=NAVY)
    if link:
        lf = regular(34)
        d.text(((W - d.textlength(link, font=lf)) / 2, H - 76), link, font=lf, fill=WHITE)
    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


# ====================================================================== video scenes (9:16)
VW, VH = 1080, 1920


_BASE_CACHE: dict = {}


def _scene_base(background: bytes | None):
    """The 1080x1920 background is built once per video and reused by every scene (saves a lot of CPU)."""
    from PIL import Image
    key = hash(background) if background else None
    if key not in _BASE_CACHE:
        _BASE_CACHE.clear()
        try:
            base = _cover(Image.open(io.BytesIO(background)).convert("RGB"), VW, VH) if background else _cover(fallback_background(), VW, VH)
        except Exception:
            base = _cover(fallback_background(), VW, VH)
        _BASE_CACHE[key] = base
    return _BASE_CACHE[key].copy()


def _scene_canvas(background: bytes | None, darkness: float):
    from PIL import Image
    canvas = _scene_base(background).convert("RGBA")
    canvas.alpha_composite(Image.new("RGBA", (VW, VH), (6, 14, 30, int(255 * darkness))))
    return canvas


def _scene_logo(canvas, bold, regular):
    from PIL import ImageDraw
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((60, 70, 156, 166), radius=24, fill=BLUE + (255,), outline=WHITE + (255,), width=3)
    d.rectangle((84, 94, 132, 108), fill=WHITE)
    d.rectangle((102, 108, 114, 146), fill=WHITE)
    d.rectangle((84, 152, 132, 158), fill=GOLD)
    d.text((176, 70), "TenderBot AI", font=bold(60), fill=WHITE)
    d.text((178, 140), "कंत्राटदारांसाठी AI सहाय्यक", font=regular(30), fill=(255, 205, 120))


def render_scene(kind: str, text: str, index: int, total: int, link: str = "", date: str | None = None,
                 background: bytes | None = None) -> bytes:
    """One 1080x1920 frame. kind: hook | point | cta."""
    from PIL import ImageDraw
    bold, regular = _fonts()
    canvas = _scene_canvas(background, {"hook": 0.48, "point": 0.60, "cta": 0.72}[kind])
    _scene_logo(canvas, bold, regular)
    d = ImageDraw.Draw(canvas)

    if kind == "hook":
        size = 112
        while True:
            hf = bold(size)
            lines = _wrap(d, text, hf, 940)
            if len(lines) <= 4 or size <= 64:
                break
            size -= 6
        step = int(size * 1.4)
        y = (VH - len(lines[:4]) * step) // 2 - 40
        for i, line in enumerate(lines[:4]):
            d.text((70, y), line, font=hf, fill=WHITE if i == 0 else GOLD)
            y += step
        d.rounded_rectangle((70, y + 30, 330, y + 40), radius=5, fill=GOLD)

    elif kind == "point":
        pill = f"{index} / {total}"
        pf = bold(46)
        d.rounded_rectangle((60, 330, 60 + int(d.textlength(pill, font=pf)) + 70, 424), radius=47, fill=GOLD + (255,))
        d.text((95, 342), pill, font=pf, fill=NAVY)
        _glass(canvas, (60, 500, 1020, 1300), 44, (255, 255, 255, 42), (255, 255, 255, 120), 3)
        d = ImageDraw.Draw(canvas)
        d.ellipse((110, 560, 190, 640), fill=GOLD + (255,))
        d.line([(127, 600), (142, 618), (172, 582)], fill=NAVY + (255,), width=9)
        tf = bold(62) if len(text) < 60 else regular(54)
        y = 690
        for line in _clip(d, text, tf, 830, 7):
            d.text((110, y), line, font=tf, fill=WHITE)
            y += int(tf.size * 1.42)
        if date:
            d.text((110, 1190), f"शेवटची तारीख: {date}", font=bold(50), fill=GOLD)
        for i in range(total):
            cx = VW // 2 - (total - 1) * 36 + i * 72
            d.ellipse((cx - 14, VH - 300, cx + 14, VH - 272), fill=(GOLD if i + 1 == index else (255, 255, 255, 110)))

    else:  # cta
        lf = regular(44)
        d.text(((VW - d.textlength("आजच सुरू करा", font=lf)) / 2, 620), "आजच सुरू करा", font=lf, fill=(255, 205, 120))
        d.rounded_rectangle((60, 720, VW - 60, 960), radius=60, fill=GOLD + (255,))
        cta, cf = "१५ दिवस\nमोफत ट्रायल", bold(80)
        for i, line in enumerate(cta.split("\n")):
            d.text(((VW - d.textlength(line, font=cf)) / 2, 745 + i * 100), line, font=cf, fill=NAVY)
        if link:
            kf = bold(48)
            d.text(((VW - d.textlength(link, font=kf)) / 2, 1060), link, font=kf, fill=WHITE)
        d.text(((VW - d.textlength("TenderBot AI", font=bold(60))) / 2, 1240), "TenderBot AI", font=bold(60), fill=WHITE)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG")
    return out.getvalue()
