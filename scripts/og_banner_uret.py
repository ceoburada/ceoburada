# -*- coding: utf-8 -*-
"""
CEOBurada OG (1200x630) + X banner (1500x500) üretici.
Referans tasarim: koyu lacivert zemin, kirmizi noktadan yayilan
disa dogru sönümlenen halkalar, marka adina yakin sicak glow.

Metni degistirmek icin sadece TITLE / SUB degiskenlerini duzenle,
sonra bu scripti calistir.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, math, os

# ---------- degistirilebilir metin ----------
TITLE = "CEOBurada"
SUB   = "Halka açık şirket yöneticilerinin TV ve dergi demeçleri"

# ---------- renkler ----------
BG_TL   = (20, 25, 39)     # sol-ust zemin (biraz aydinlik lacivert)
BG_BR   = (7, 10, 16)      # sag-alt zemin (neredeyse siyah)
RED     = (255, 77, 79)    # --live nokta
GLOW    = (255, 70, 72)    # sicak halo
RING    = (206, 74, 78)    # halka rengi (muted kirmizi)
TX      = (240, 243, 249)  # marka adi beyaz
TX2     = (150, 166, 192)  # alt yazi

FONTDIR = r"C:\Windows\Fonts"
F_BOLD  = os.path.join(FONTDIR, "segoeuib.ttf")
F_REG   = os.path.join(FONTDIR, "segoeui.ttf")

S = 3  # supersampling


def _bg_field(W, H, cx, cy):
    """numpy ile diagonal gradyan + dottan yayilan glow + kose vinyet."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    # diagonal gradyan
    t = ((xs / W) + (ys / H)) / 2.0
    base = np.empty((H, W, 3), np.float32)
    for i in range(3):
        base[..., i] = BG_TL[i] * (1 - t) + BG_BR[i] * t
    # sicak radyal glow (dotta parlak, disa dogru söner)
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    Rg = 0.42 * math.hypot(W, H)
    g = np.clip(1 - d / Rg, 0, 1) ** 2.6 * 0.22
    for i in range(3):
        base[..., i] = base[..., i] * (1 - g) + GLOW[i] * g
    # hafif kose vinyet (merkez disina koyulasir)
    dc = np.sqrt((xs - W / 2) ** 2 + (ys - H / 2) ** 2) / (0.5 * math.hypot(W, H))
    vig = 1 - np.clip(dc, 0, 1) ** 2.2 * 0.35
    base *= vig[..., None]
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def render(W, H, out):
    w, h = W * S, H * S
    dot_r = 21 * S
    gap   = 30 * S
    word_sz = 90 * S
    sub_sz  = 32 * S

    f_word = ImageFont.truetype(F_BOLD, word_sz)
    f_sub  = ImageFont.truetype(F_REG, sub_sz)

    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    word_w = tmp.textlength(TITLE, font=f_word)
    wb = f_word.getbbox(TITLE)          # gorsel yukseklik icin
    word_h = wb[3] - wb[1]

    # yatayda dot+yazi grubunu ortala
    row_w = 2 * dot_r + gap + word_w
    row_left = (w - row_w) / 2
    cx = row_left + dot_r
    text_x = row_left + 2 * dot_r + gap
    cy = h * 0.455                       # marka adi dikey merkezi (biraz ust)

    # --- zemin + glow + vinyet ---
    img = _bg_field(w, h, cx, cy).convert("RGBA")

    # --- halkalar: disa dogru sönümlenen ---
    ring = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    spacing = 92 * S
    r0 = dot_r + 46 * S
    alphas = [120, 82, 54, 34, 20, 12]
    lw = max(1, round(1.6 * S))
    for i, a in enumerate(alphas):
        r = r0 + i * spacing
        rd.ellipse([cx - r, cy - r, cx + r, cy + r],
                   outline=RING + (a,), width=lw)
    img = Image.alpha_composite(img, ring)

    d = ImageDraw.Draw(img)

    # --- kirmizi nokta (hafif glow ile) ---
    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hr = dot_r * 2.3
    hd.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=RED + (44,))
    halo = halo.filter(ImageFilter.GaussianBlur(dot_r * 1.1))
    img = Image.alpha_composite(img, halo)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=RED)

    # --- marka adi ---
    d.text((text_x, cy), TITLE, font=f_word, fill=TX, anchor="lm")

    # --- alt yazi (marka adinin soluna hizali, altinda) ---
    sub_y = cy + word_h * 0.5 + 30 * S
    d.text((text_x, sub_y), SUB, font=f_sub, fill=TX2, anchor="lm")

    img = img.convert("RGB").resize((W, H), Image.LANCZOS)
    img.save(out)
    print("yazildi:", out, f"{W}x{H}")


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.environ.get("OUT_DIR", base)
    render(1200, 630, os.path.join(out_dir, "og.png"))
    render(1500, 500, os.path.join(out_dir, "banner.png"))
