"""Generate a simple bilingual (Arabic + English) app icon -> icon.png / icon.ico"""
import os
from PIL import Image, ImageDraw, ImageFont

# this script lives in dev/; write the icons to the repo root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SIZE = 512
BG = (24, 26, 32)        # dark theme background
ACCENT = (66, 135, 245)  # blue accent
WHITE = (240, 240, 245)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# rounded dark square with an accent ring
d.rounded_rectangle([16, 16, SIZE - 16, SIZE - 16], radius=96, fill=BG)
d.rounded_rectangle([16, 16, SIZE - 16, SIZE - 16], radius=96, outline=ACCENT, width=14)

en = ImageFont.truetype("arialbd.ttf", 200)   # English glyph
ar = ImageFont.truetype("arial.ttf", 130)      # Arabic glyph

def centered(text, font, cy, fill):
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((SIZE - w) / 2 - box[0], cy - h / 2 - box[1]), text, font=font, fill=fill)

centered("ET", en, SIZE * 0.40, WHITE)   # English: EasyTer initials
centered("إ", ar, SIZE * 0.72, ACCENT)  # Arabic letter "إ"

img.save(os.path.join(_ROOT, "icon.png"))
img.save(os.path.join(_ROOT, "icon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Saved icon.png and icon.ico to", _ROOT)
