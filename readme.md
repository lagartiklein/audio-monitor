# 🎚️ Audio Monitor - Sistema de Monitoreo Multi-canal via WebRTC/WebSocket

Sistema de ultra-baja latencia para monitorear canales individuales de interfaces de audio profesionales. **Ahora con WebRTC para latencia <15ms**.

## ✨ Características

- ✅ **Auto-configuración**: Detecta automáticamente tu interfaz de audio
- ✅ Captura multi-canal (ASIO/WASAPI) con sounddevice
- ✅ **WebRTC para ultra baja latencia** (<15ms)
- ✅ WebSocket como fallback (20-40ms)
- ✅ Control independiente de volumen por canal
- ✅ Interfaz web responsive (funciona en smartphones)
- ✅ Hasta 32 canales simultáneos
- ✅ AudioWorklet API para procesamiento en audio thread
- ✅ Reconexión automática
- ✅ Métricas en tiempo real

## 🚀 Instalación Rápida

### 1. Requisitos
- Python 3.8 o superior
- Interfaz de audio con más de 2 canales
- Drivers ASIO/WASAPI instalados (Windows) o JACK (Linux/Mac)

### 2. Instalar dependencias
```bash
pip install -r requirements.txt