from PIL import Image
import os

# Ruta de entrada y salida
input_path = os.path.join(os.path.dirname(__file__), "icon.png")
output_path = os.path.join(os.path.dirname(__file__), "icono.ico")

# Convertir PNG a ICO
img = Image.open(input_path)
img.save(output_path, format='ICO', sizes=[(64,64), (32,32), (16,16)])
print(f"Icono convertido y guardado en: {output_path}")
