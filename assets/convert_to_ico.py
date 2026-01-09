from PIL import Image
import os

# Ruta de entrada y salida
input_path = os.path.join(os.path.dirname(__file__), "icon.png")
output_path = os.path.join(os.path.dirname(__file__), "icono.ico")

# Convertir PNG a ICO con todos los tamaños recomendados
img = Image.open(input_path)
sizes = [(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)]
img.save(output_path, format='ICO', sizes=sizes)
print(f"Icono convertido y guardado en: {output_path} (tamaños: {sizes})")
