# Regenerating the profile card

The card is built by `update.py` from three inputs:

- `ascii.txt`: the portrait on the left
- the static fields near the top of `update.py`
- live GitHub stats, cached in `stats.json`

## Change the text

Edit `HEADER`, `ABOUT` or `CONTACT` in `update.py`, then run:

```bash
python3 update.py
```

Without a token this reuses the numbers in `stats.json`. With `GH_TOKEN` set
it fetches fresh ones. The daily workflow does the same on GitHub.

## Change the portrait

`ascii_art.py` needs Pillow (`pip install pillow`). For a photo on a solid
gray background (RGB 128, 128, 128), the gray is left blank:

```bash
python3 tools/ascii_art.py portrait.png --bg 128
python3 update.py
```

Other options:

- `--invert` for a photo on a light background
- `--text AV` to render initials instead of a photo

The art fills 25 rows, and its width follows the photo's proportions, up to
40 columns.
