#!/usr/bin/env python3
"""Build every Apex Qubits logo file the site uses, from Valentin's generator (apex_logo.py).

Run with the generator's own Python (it has shapely, pymupdf and pillow):

  "$GEN/.venv/bin/python" tools/logo/build_logo.py "$GEN"

where GEN is the generator folder, e.g. "~/Documents/Apex Qubits Logo builder Valentin/generator".
Writes into static/: images/logo.svg, images/logo-black-on-white-512.png, images/og-default.png,
favicon.svg, favicon-{16,32,96,192,512}.png, favicon.ico, apple-touch-icon.png.

LINE is the gap between blocks in model units (base cube edge 1.2). The generator's default, 0.028,
matches the designer's photo but is under half a pixel at header size; 0.05 reads at 40 px.
Favicons use a slightly thicker line because they are shown at 16-32 px.
"""
import io, os, re, sys

LINE = 0.05
LINE_ICON = 0.065
# Tab favicons (favicon.svg, 16, 32, .ico) are drawn at 16-32 px, where four steps per arm cannot
# show their gaps. They use a simplified tower: two steps per arm, thicker blocks, much wider lines.
SMALL = dict(steps=2, first_h=0.32, line=0.17, margin=0.08)
ABYSS = "#0A0C10"
SIZE = 1000

gen_dir = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else
                             "~/Documents/Apex Qubits Logo builder Valentin/generator")
sys.path.insert(0, gen_dir)
import apex_logo as A  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

site = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
static = os.path.join(site, "static")

P = dict(A.PRESETS["photo"])
view = A.make_view("isometric", None, None)
FULL = (A.gen_blocks(P),)
FULL += (A.faces_2d(FULL[0], view),)
PS = dict(P, steps=SMALL["steps"], first_h=SMALL["first_h"])
SIMPLE = (A.gen_blocks(PS),)
SIMPLE += (A.faces_2d(SIMPLE[0], view),)


def svg(style, line, margin, colors=None, geo=FULL):
    blocks, faces = geo
    return A.render_svg_exact(faces, blocks, view, style, line, SIZE, margin=margin, colors=colors or {})


def mark(line, margin, fill="#FFFFFF", geo=FULL):
    """Faces only, transparent background and gaps: the gaps show whatever is behind."""
    s = svg("inverse", line, margin, {"bg": "none", "line": "none", "fill": fill}, geo)
    s = re.sub(r'<rect [^>]*/>\n', "", s)
    return re.sub(r'<path fill="none"[^>]*/>\n', "", s)


def titled(s, extra=""):
    return s.replace(f'viewBox="0 0 {SIZE} {SIZE}">',
                     f'viewBox="0 0 {SIZE} {SIZE}" role="img" aria-label="Apex Qubits"><title>Apex Qubits</title>{extra}', 1)


def raster(s, px, alpha=True):
    doc = pymupdf.open(stream=s.encode(), filetype="svg")
    page = doc[0]
    big = max(px, 1024)
    pm = page.get_pixmap(matrix=pymupdf.Matrix(big / page.rect.width, big / page.rect.width), alpha=alpha)
    im = Image.open(io.BytesIO(pm.tobytes("png"))).convert("RGBA" if alpha else "RGB")
    return im.resize((px, px), Image.LANCZOS) if px != big else im


def write(path, text):
    with open(os.path.join(static, path), "w") as fh:
        fh.write(text)
    print(path)


def save(path, im):
    im.save(os.path.join(static, path), optimize=True)
    print(path)


# Header logo: white faces, transparent. A small margin so anti-aliased edges are never clipped;
# the header's CSS gives the outer spacing.
write("images/logo.svg", titled(mark(LINE, 0.03)))

# Structured-data logo: black faces, white gaps, on white, with a real margin.
save("images/logo-black-on-white-512.png", raster(svg("solid", LINE, 0.12), 512, alpha=False))

# Favicons: white mark on a rounded abyss tile. Tab sizes use the simplified tower;
# 96 px and up (bookmarks, Android home screen) use the full logo with room inside the corners.
R = 0.16 * SIZE
tile = f'<rect width="{SIZE}" height="{SIZE}" rx="{R:.0f}" fill="{ABYSS}"/>\n'
fav = titled(mark(SMALL["line"], SMALL["margin"], geo=SIMPLE), tile)
fav_full = titled(mark(LINE_ICON, 0.15), tile)
write("favicon.svg", fav)
for px in (16, 32):
    save(f"favicon-{px}.png", raster(fav, px))
for px in (96, 192, 512):
    save(f"favicon-{px}.png", raster(fav_full, px))
ico = raster(fav, 256)
ico.save(os.path.join(static, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
print("favicon.ico")

# Apple touch icon: full square (iOS rounds it), mark well inside the rounded mask.
apple = mark(LINE_ICON, 0.17).replace(f'viewBox="0 0 {SIZE} {SIZE}">',
                                      f'viewBox="0 0 {SIZE} {SIZE}"><rect width="{SIZE}" height="{SIZE}" fill="{ABYSS}"/>\n', 1)
save("apple-touch-icon.png", raster(apple, 180, alpha=False))

# Open Graph card: 1200x630 abyss, mark 220 px tall in the middle.
og = Image.new("RGB", (1200, 630), ABYSS)
m = raster(mark(LINE, 0.0), 230)
og.paste(m, ((1200 - 230) // 2, (630 - 230) // 2), m)
save("images/og-default.png", og)
