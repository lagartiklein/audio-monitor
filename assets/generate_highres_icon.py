from PIL import Image
import os

# Source PNG (highest resolution available)
SRC = os.path.join(os.path.dirname(__file__), "icon-512.png")
OUT = os.path.join(os.path.dirname(__file__), "fichatech_highres.ico")

sizes = [16, 32, 48, 64, 128, 256]

img = Image.open(SRC).convert("RGBA")
img.save(OUT, sizes=[(s, s) for s in sizes])
print(f"✅ Icono generado: {OUT}")
