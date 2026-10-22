#!/usr/bin/env python3
# Licença: GNU AGPL-3.0, a mesma do RustDesk. © EDX Tecnologia em Informação Ltda.
"""Gera todos os ícones e logos do app a partir do logo EDX.

Uso (uma vez, ou sempre que o logo mudar):
    pip install pillow
    python3 edx/scripts/gen_icons.py

Lê   edx/assets/logo.png        (logo horizontal EDX INFO, fundo branco)
Grava edx/assets/generated/*     (arquivos prontos, copiados pelo rebrand.py)

Os arquivos gerados ficam versionados no repositório, então o build no CI
não precisa de Pillow.
"""
import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
import sys

# Console do Windows (cp1252) não tem ✔/✘; sem isso o print derruba o script.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

EDX = Path(__file__).resolve().parents[1]
SRC = EDX / "assets" / "logo.png"
OUT = EDX / "assets" / "generated"


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def knock_out_white(im, lo=200, hi=250):
    """Fundo branco -> transparente, com borda suave (anti-alias preservado)."""
    im = im.convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            m = min(r, g, b)
            if m >= hi:
                px[x, y] = (r, g, b, 0)
            elif m > lo:
                px[x, y] = (r, g, b, int(a * (hi - m) / (hi - lo)))
    return im


def split_mark(logo):
    """Separa 'EDX' do selo vertical 'INFO' procurando a coluna vazia entre eles."""
    rgb = logo.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    cols = [x for x in range(w) if any(min(px[x, y]) < 200 for y in range(h))]
    gaps = [(cols[i], cols[i + 1]) for i in range(len(cols) - 1)
            if cols[i + 1] - cols[i] > 2]
    rows = [y for y in range(h) if any(min(px[x, y]) < 200 for x in range(w))]
    top, bottom = rows[0], rows[-1] + 1
    if gaps:
        edx_right = gaps[-1][0] + 1
    else:
        edx_right = cols[-1] + 1
    return logo.crop((cols[0], top, edx_right, bottom)), logo.crop((cols[0], top, cols[-1] + 1, bottom))


def rounded_tile(size, radius_ratio=0.22, fill=(255, 255, 255, 255),
                 border=None, shadow=True):
    scale = 4
    S = size * scale
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    inset = int(S * (0.04 if shadow else 0.0))
    box = (inset, inset, S - inset - 1, S - inset - 1)
    r = int((S - 2 * inset) * radius_ratio)
    if shadow:
        sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            (box[0], box[1] + int(S * 0.015), box[2], box[3] + int(S * 0.015)),
            r, fill=(0, 0, 0, 70))
        tile.alpha_composite(sh.filter(ImageFilter.GaussianBlur(S * 0.012)))
    d.rounded_rectangle(box, r, fill=fill,
                        outline=border, width=max(1, S // 128) if border else 0)
    return tile.resize((size, size), Image.LANCZOS), (inset / scale)


def app_icon(mark, size, pad_ratio, accent):
    tile, inset = rounded_tile(size, border=None, shadow=size >= 64)
    inner = size - 2 * inset
    # faixa de destaque na base (azul EDX), discreta
    if size >= 48:
        band = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        bh = max(2, int(inner * 0.07))
        ImageDraw.Draw(band).rectangle(
            (0, int(size - inset - bh - inner * 0.06), size, int(size - inset - inner * 0.06)),
            fill=accent + (255,))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (inset, inset, size - inset - 1, size - inset - 1), int(inner * 0.22), fill=255)
        band.putalpha(Image.composite(band.getchannel("A"), Image.new("L", (size, size), 0), mask))
        tile.alpha_composite(band)
    avail = inner * (1 - 2 * pad_ratio)
    k = min(avail / mark.width, avail / mark.height)
    m = mark.resize((max(1, round(mark.width * k)), max(1, round(mark.height * k))), Image.LANCZOS)
    x = round((size - m.width) / 2)
    y = round((size - m.height) / 2 - (inner * 0.03 if size >= 48 else 0))
    tile.alpha_composite(m, (x, y))
    return tile


def template_silhouette(mark, size, pad=0.08):
    """Ícone 'template' da barra de menus do macOS: preto + alpha."""
    a = mark.getchannel("A")
    avail = size * (1 - 2 * pad)
    k = min(avail / mark.width, avail / mark.height)
    a = a.resize((max(1, round(mark.width * k)), max(1, round(mark.height * k))), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sil = Image.new("RGBA", a.size, (0, 0, 0, 255))
    sil.putalpha(a)
    out.alpha_composite(sil, ((size - a.width) // 2, (size - a.height) // 2))
    return out


def png_svg(png_img, view=32):
    buf = io.BytesIO()
    png_img.save(buf, "PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {view} {view}" width="{view}" height="{view}">'
            f'<image width="{view}" height="{view}" '
            f'href="data:image/png;base64,{b64}" xlink:href="data:image/png;base64,{b64}"/></svg>\n')


def main():
    brand = json.loads((EDX / "brand.json").read_text(encoding="utf-8"))
    accent = hex_rgb(brand["colors"]["primary"])
    OUT.mkdir(parents=True, exist_ok=True)

    logo = Image.open(SRC).convert("RGBA")
    edx_mark_white, full_white = split_mark(logo)
    edx_mark = knock_out_white(edx_mark_white)
    full_logo = knock_out_white(full_white)

    # ícone mestre e tamanhos (padding menor em tamanhos pequenos = marca maior)
    def icon(sz):
        pad = 0.02 if sz <= 32 else 0.12
        return app_icon(edx_mark, sz, pad, accent)

    master = icon(1024)
    master.save(OUT / "icon.png")                       # res/icon.png (1024)
    master.save(OUT / "mac-icon.png")                   # res/mac-icon.png
    for sz, name in [(32, "32x32.png"), (64, "64x64.png"),
                     (128, "128x128.png"), (256, "128x128@2x.png")]:
        icon(sz).save(OUT / name)
    icon(256).save(OUT / "flutter-icon.png")            # flutter/assets/icon.png

    # Windows .ico (cada tamanho renderizado separadamente, não reamostrado)
    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = {s: icon(s) for s in ico_sizes}
    frames[256].save(OUT / "icon.ico", format="ICO",
                     sizes=[(s, s) for s in ico_sizes],
                     append_images=[frames[s] for s in ico_sizes if s != 256])
    frames[256].save(OUT / "app_icon.ico", format="ICO",
                     sizes=[(s, s) for s in ico_sizes],
                     append_images=[frames[s] for s in ico_sizes if s != 256])
    tray_sizes = [16, 20, 24, 32, 48]
    frames[48].save(OUT / "tray-icon.ico", format="ICO",
                    sizes=[(s, s) for s in tray_sizes],
                    append_images=[frames[s] for s in tray_sizes if s != 48])

    # macOS .icns
    master.save(OUT / "AppIcon.icns", format="ICNS")

    # bandeja do macOS (template monocromático, tamanhos do upstream)
    template_silhouette(edx_mark, 60).save(OUT / "mac-tray-dark-x2.png")
    template_silhouette(edx_mark, 48).save(OUT / "mac-tray-light-x2.png")

    # SVGs (o upstream usa vetor; aqui embutimos o PNG em alta resolução)
    (OUT / "scalable.svg").write_text(png_svg(icon(512)), encoding="utf-8")
    (OUT / "icon.svg").write_text(png_svg(icon(256)), encoding="utf-8")

    # logos da tela inicial (Flutter limita a 300x60; geramos em 2x)
    def fit(im, max_w, max_h):
        k = min(max_w / im.width, max_h / im.height)
        return im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)

    fit(full_logo, 600, 120).save(OUT / "logo.png")
    fit(full_logo, 600, 120).save(OUT / "logo_light.png")
    fit(full_logo, 600, 120).save(OUT / "logo_dark.png")

    # prévia para conferência humana
    prev = Image.new("RGBA", (900, 420), (245, 247, 250, 255))
    dark = Image.new("RGBA", (450, 120), (32, 34, 38, 255))
    prev.alpha_composite(dark, (450, 300))
    x = 20
    for s in [256, 128, 64, 48, 32, 24, 16]:
        prev.alpha_composite(icon(s), (x, 20 + (256 - s) // 2 if s < 256 else 20))
        x += s + 16
    lg = fit(full_logo, 400, 90)
    prev.alpha_composite(lg, (20, 310))
    prev.alpha_composite(lg, (475, 315))
    prev.save(OUT / "_preview.png")

    for f in sorted(OUT.iterdir()):
        print(f"  {f.name:24s} {f.stat().st_size:>9,d} bytes")


if __name__ == "__main__":
    main()
