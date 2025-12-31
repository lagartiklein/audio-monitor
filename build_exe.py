# build_exe.py
"""
Script para compilar Fichatech Monitor a ejecutable .exe
Uso: python build_exe.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

print("="*70)
print("  FICHATECH MONITOR - BUILD SCRIPT")
print("="*70)

# Configuración
APP_NAME = "FichatechMonitor"
MAIN_SCRIPT = "main.py"
ICON_FILE = "icono.ico"
VERSION = "1.0.0"

# Verificar que PyInstaller está instalado
try:
    import PyInstaller
    print(f"✅ PyInstaller {PyInstaller.__version__} encontrado")
except ImportError:
    print("❌ PyInstaller no encontrado")
    print("📦 Instalando PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    print("✅ PyInstaller instalado")

# Verificar archivos necesarios
if not os.path.exists(MAIN_SCRIPT):
    print(f"❌ Error: {MAIN_SCRIPT} no encontrado")
    sys.exit(1)

if not os.path.exists(ICON_FILE):
    print(f"⚠️  Advertencia: {ICON_FILE} no encontrado, se usará icono por defecto")
    ICON_FILE = None

print("\n📋 CONFIGURACIÓN:")
print(f"   Nombre: {APP_NAME}")
print(f"   Script principal: {MAIN_SCRIPT}")
print(f"   Icono: {ICON_FILE or 'Por defecto'}")
print(f"   Versión: {VERSION}")

# Limpiar builds anteriores
print("\n🧹 Limpiando builds anteriores...")
for folder in ['build', 'dist', '__pycache__']:
    if os.path.exists(folder):
        shutil.rmtree(folder)
        print(f"   Eliminado: {folder}/")

# Eliminar archivos .spec anteriores
spec_files = list(Path('.').glob('*.spec'))
for spec in spec_files:
    spec.unlink()
    print(f"   Eliminado: {spec}")

print("\n🔨 INICIANDO COMPILACIÓN...")
print("="*70)

# Construir comando de PyInstaller
cmd = [
    "pyinstaller",
    "--name", APP_NAME,
    "--onefile",  # Un solo ejecutable
    "--windowed",  # Sin consola (GUI)
    "--clean",
    
    # Datos adicionales
    "--add-data", f"audio_server{os.pathsep}audio_server",
    
    # Paquetes ocultos necesarios
    "--hidden-import", "sounddevice",
    "--hidden-import", "numpy",
    "--hidden-import", "flask",
    "--hidden-import", "flask_socketio",
    "--hidden-import", "flask_cors",
    "--hidden-import", "engineio",
    "--hidden-import", "socketio",
    "--hidden-import", "eventlet",
    "--hidden-import", "eventlet.wsgi",
    "--hidden-import", "eventlet.green",
    "--hidden-import", "dns",
    "--hidden-import", "dns.resolver",
    
    # Optimizaciones
    "--optimize", "2",
    "--strip",  # Reducir tamaño
    
    # Información
    f"--version-file=version_info.txt" if os.path.exists("version_info.txt") else "",
]

# Añadir icono si existe
if ICON_FILE:
    cmd.extend(["--icon", ICON_FILE])

# Script principal
cmd.append(MAIN_SCRIPT)

# Filtrar elementos vacíos
cmd = [c for c in cmd if c]

print("Ejecutando PyInstaller...")
print(f"Comando: {' '.join(cmd)}\n")

try:
    result = subprocess.run(cmd, check=True, capture_output=False, text=True)
    print("\n" + "="*70)
    print("✅ COMPILACIÓN EXITOSA")
    print("="*70)
    
    # Información del ejecutable
    exe_path = Path("dist") / f"{APP_NAME}.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n📦 EJECUTABLE GENERADO:")
        print(f"   Ubicación: {exe_path.absolute()}")
        print(f"   Tamaño: {size_mb:.2f} MB")
        
        print(f"\n🚀 LISTO PARA DISTRIBUCIÓN:")
        print(f"   1. El ejecutable está en: dist/{APP_NAME}.exe")
        print(f"   2. Puedes distribuir solo ese archivo")
        print(f"   3. No requiere Python instalado en el PC destino")
        
        # Crear carpeta de distribución
        dist_folder = Path("release")
        if dist_folder.exists():
            shutil.rmtree(dist_folder)
        dist_folder.mkdir()
        
        # Copiar ejecutable
        shutil.copy(exe_path, dist_folder / f"{APP_NAME}.exe")
        
        # Crear README
        readme_content = f"""
FICHATECH MONITOR v{VERSION}
============================

INSTALACIÓN:
1. Ejecuta {APP_NAME}.exe
2. Selecciona tu interfaz de audio
3. Inicia el servidor

REQUISITOS:
- Windows 10/11 (64-bit)
- Interfaz de audio conectada
- Puerto 5100 (Web) y 5101 (RF) disponibles

PRIMER USO:
1. Al ejecutar por primera vez, Windows Defender puede mostrar advertencia
2. Haz click en "Más información" → "Ejecutar de todas formas"
3. Esto es normal para aplicaciones sin firma digital

SOPORTE:
Para reportar problemas, incluye el archivo error_log_*.txt si se genera.

© 2024 Fichatech
"""
        
        with open(dist_folder / "README.txt", "w", encoding="utf-8") as f:
            f.write(readme_content)
        
        print(f"\n📁 CARPETA DE DISTRIBUCIÓN CREADA:")
        print(f"   {dist_folder.absolute()}/")
        print(f"   ├── {APP_NAME}.exe")
        print(f"   └── README.txt")
        
    else:
        print(f"⚠️  Advertencia: No se encontró {exe_path}")
        
except subprocess.CalledProcessError as e:
    print("\n" + "="*70)
    print("❌ ERROR EN LA COMPILACIÓN")
    print("="*70)
    print(f"\nCódigo de error: {e.returncode}")
    print("\n💡 SOLUCIONES COMUNES:")
    print("1. Verifica que todas las dependencias estén instaladas:")
    print("   pip install -r requirements.txt")
    print("2. Revisa que main.py no tenga errores de sintaxis")
    print("3. Comprueba que audio_server/ exista como carpeta")
    sys.exit(1)

except Exception as e:
    print(f"\n❌ Error inesperado: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("  BUILD COMPLETADO")
print("="*70)