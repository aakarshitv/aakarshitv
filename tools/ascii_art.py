"""Convert an image into the ASCII art shown on the left of the profile card.

Usage:
    python tools/ascii_art.py photo.jpg            # writes ascii.txt
    python tools/ascii_art.py photo.png --bg 128   # blank out a solid gray background
    python tools/ascii_art.py --text AV            # renders initials instead

Requires Pillow (pip install pillow). Only needed locally, not in CI.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

# Dark to light. The card draws light text on dark (and the reverse in light
# mode), so dense characters mark the bright parts of the image.
RAMP = " .'`^,:;Il!i><~+_-?][}{1)(|tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
# A shorter ramp reads better for faces: fewer steps, so shading shows as
# clear bands instead of character noise.
PORTRAIT_RAMP = " .'`,:;!|ilj*kmnrwMHN%@"
COLS, ROWS = 40, 25  # upper bounds; update.py trims blank rows around the art
CELL_ASPECT = 0.48  # character width / line height on the card (~9.6px / 20px)


def from_image(path, invert=False, bg=None):
    rgb = Image.open(path).convert("RGB")
    # Keep the photo's proportions: fill the rows and use as many columns as
    # that needs, up to COLS.
    cols = min(COLS, round(ROWS * rgb.width / rgb.height / CELL_ASPECT))

    img = ImageOps.grayscale(rgb)
    if invert:
        img = ImageOps.invert(img)
    img = img.resize((cols, ROWS), Image.Resampling.LANCZOS)

    blank = None
    if bg is not None:
        # A cell is background when most of its pixels are the solid gray.
        is_bg = rgb.point(lambda v: 255 if abs(v - bg) <= 6 else 0).convert("L")
        is_bg = Image.eval(is_bg, lambda v: 255 if v == 255 else 0)
        is_bg = is_bg.resize((cols, ROWS), Image.Resampling.BOX)
        blank = [[is_bg.getpixel((x, y)) > 150 for x in range(cols)] for y in range(ROWS)]
        # Stretch contrast over the subject only, ignoring the gray.
        subject = is_bg.point(lambda v: 255 if v <= 150 else 0)
        img = ImageOps.autocontrast(img, cutoff=1, mask=subject)
    else:
        img = ImageOps.autocontrast(img, cutoff=2)
    return to_ascii(img, PORTRAIT_RAMP, blank)


def from_text(text):
    img = Image.new("L", (COLS * 20, ROWS * 40), 0)
    draw = ImageDraw.Draw(img)
    font = None
    for name in ("/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, 640)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    x = (img.width - (box[2] - box[0])) / 2 - box[0]
    y = (img.height - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), text, fill=255, font=font)
    img = img.resize((COLS, ROWS), Image.Resampling.LANCZOS)
    # Treat near-black as empty so faint edges don't leave stray dots.
    return to_ascii(img, RAMP, [[img.getpixel((x, y)) < 48 for x in range(COLS)]
                                for y in range(ROWS)])


def to_ascii(img, ramp, blank=None):
    """Map an already-resized grayscale image to text. Cells marked in `blank`
    become spaces; every other cell gets at least the lightest visible glyph
    so dark areas (hair, clothes) keep their outline."""
    lines = []
    for y in range(img.height):
        row = "".join(
            " " if blank and blank[y][x]
            else ramp[max(1, img.getpixel((x, y)) * (len(ramp) - 1) // 255)]
            for x in range(img.width)
        )
        lines.append(row.rstrip())
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?")
    parser.add_argument("--text")
    parser.add_argument("--invert", action="store_true", help="for photos on a light background")
    parser.add_argument("--bg", type=int, help="gray level of a solid background to leave blank")
    parser.add_argument("-o", "--output", default=Path(__file__).parent.parent / "ascii.txt")
    args = parser.parse_args()
    if not (args.image or args.text):
        parser.error("give an image path or --text")
    art = from_text(args.text) if args.text else from_image(args.image, args.invert, args.bg)
    Path(args.output).write_text(art)
    print(art)
