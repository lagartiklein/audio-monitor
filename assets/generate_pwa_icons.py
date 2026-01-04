"""
Script para generar iconos PWA en múltiples tamaños
Requiere: pip install Pillow
"""

from PIL import Image
import os

# Tamaños requeridos para PWA
SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

def generate_pwa_icons():
    # Rutas
    script_dir = os.path.dirname(os.path.abspath(__file__))
    source_icon = os.path.join(script_dir, 'icon.png')
    
    if not os.path.exists(source_icon):
        print(f"❌ No se encontró icon.png en {script_dir}")
        return
    
    print(f"📦 Generando iconos PWA desde: {source_icon}")
    
    # Abrir imagen original
    img = Image.open(source_icon)
    
    # Convertir a RGBA si es necesario
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    print(f"   Imagen original: {img.size[0]}x{img.size[1]}")
    
    # Generar cada tamaño
    for size in SIZES:
        output_path = os.path.join(script_dir, f'icon-{size}.png')
        
        # Redimensionar manteniendo calidad
        resized = img.resize((size, size), Image.Resampling.LANCZOS)
        
        # Guardar
        resized.save(output_path, 'PNG', optimize=True)
        print(f"   ✅ Generado: icon-{size}.png ({size}x{size})")
    
    # También copiar el original a 512 si es diferente
    if img.size != (512, 512):
        resized_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
        resized_512.save(os.path.join(script_dir, 'icon-512.png'), 'PNG', optimize=True)
    
    print(f"\n✅ {len(SIZES)} iconos PWA generados exitosamente!")
    print(f"   Ubicación: {script_dir}")

if __name__ == '__main__':
    generate_pwa_icons()
