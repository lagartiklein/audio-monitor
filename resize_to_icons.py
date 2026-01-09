# resize_to_icons.py
"""
Script para generar PNGs de iconos en múltiples resoluciones a partir de una sola imagen fuente (por ejemplo, logo.png).
Requiere ImageMagick instalado y accesible como 'magick'.
"""
import subprocess
import sys
import os

# Nombre de la imagen fuente (ajusta si tu archivo tiene otro nombre)
SOURCE_IMAGE = 'logo.png'  # Cambia esto si tu imagen tiene otro nombre

# Tamaños requeridos para el .ico
SIZES = [16, 32, 48, 64, 128, 256]

# Verifica que la imagen fuente existe
def check_source():
    if not os.path.exists(SOURCE_IMAGE):
        print(f"No se encuentra {SOURCE_IMAGE} en la carpeta actual.")
        sys.exit(1)

def resize_icons():
    for size in SIZES:
        out_file = f"icon-{size}.png"
        cmd = [
            "magick", SOURCE_IMAGE,
            "-resize", f"{size}x{size}",
            out_file
        ]
        print(f"Generando {out_file} ...")
        subprocess.run(cmd, check=True)
    print("\n¡Listo! Ahora puedes crear el .ico con:")
    print("magick icon-16.png icon-32.png icon-48.png icon-64.png icon-128.png icon-256.png app_icon.ico")

if __name__ == "__main__":
    check_source()
    resize_icons()
