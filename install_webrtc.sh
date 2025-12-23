#!/bin/bash
# Script de instalación para WebRTC Audio Monitor

echo "🚀 Instalando Audio Monitor con WebRTC..."

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no encontrado. Instala Python 3.8 o superior."
    exit 1
fi

# Verificar pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 no encontrado. Instala pip3."
    exit 1
fi

# Crear entorno virtual
echo "📦 Creando entorno virtual..."
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
echo "📥 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

# Instalar dependencias del sistema (Linux)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🔧 Instalando dependencias del sistema (Linux)..."
    sudo apt-get update
    sudo apt-get install -y \
        python3-dev \
        libavdevice-dev \
        libavformat-dev \
        libavcodec-dev \
        libavutil-dev \
        libswscale-dev \
        libswresample-dev \
        portaudio19-dev \
        libopus-dev
fi

# macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "🔧 Instalando dependencias del sistema (macOS)..."
    brew install ffmpeg opus portaudio
fi

# Crear estructura de directorios
echo "📁 Creando estructura de directorios..."
mkdir -p logs
mkdir -p recordings

# Configurar permisos
chmod +x main.py

echo ""
echo "✅ Instalación completada!"
echo ""
echo "Para iniciar el servidor:"
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "Para acceso desde dispositivos móviles:"
echo "  Usa la IP que se mostrará en consola"
echo ""
echo "⚡ WebRTC activado para latencia <15ms"