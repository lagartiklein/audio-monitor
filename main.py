#!/usr/bin/env python3
"""
Audio Monitor - Sistema de Monitoreo Multi-canal via WiFi
"""

import sys
import signal
import webbrowser
import time
import socket

from backend.audio_capture import AudioCapture
from backend.channel_manager import ChannelManager
from backend.websocket_server import WebSocketServer, init_server
import config

def get_local_ip():
    """Obtiene la IP local para acceso desde red"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

def signal_handler(sig, frame):
    """Maneja Ctrl+C para cerrar limpiamente"""
    print("\n[*] Cerrando servidor...")
    sys.exit(0)

def main():
    print("=" * 60)
    print("  🎚️  Audio Monitor - Sistema de Monitoreo Multi-canal")
    print("=" * 60)
    print()
    
    # Configurar signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 1. Inicializar captura de audio
        audio_capture = AudioCapture()
        
        # Listar dispositivos disponibles
        devices = audio_capture.list_devices()
        
        if not devices:
            print("[!] ERROR: No se encontraron interfaces de audio multi-canal")
            print("[!] Verifica que tu interfaz esté conectada y tenga más de 2 canales")
            return
        
        print("[*] Interfaces de audio detectadas:")
        for dev in devices:
            print(f"    [{dev['id']}] {dev['name']}")
            print(f"        Canales: {dev['channels']} | Sample rate nativo: {dev['sample_rate']} Hz")
        print()
        
        # Usar primera interfaz por defecto
        num_channels = audio_capture.start_capture(devices[0]['id'])
        
        # 2. Inicializar channel manager
        channel_manager = ChannelManager(num_channels)
        
        # 3. Inicializar servidor WebSocket
        init_server(audio_capture, channel_manager)
        server = WebSocketServer(audio_capture, channel_manager)
        
        # 4. Abrir navegador automáticamente
        local_ip = get_local_ip()
        url = f"http://{local_ip}:{config.PORT}"
        
        print()
        print("=" * 60)
        print(f"[✓] Servidor iniciado exitosamente")
        print(f"[✓] URL local: http://localhost:{config.PORT}")
        print(f"[✓] URL red local: {url}")
        print()
        print("[*] Conecta tus dispositivos a esta URL para monitorear audio")
        print("[*] Presiona Ctrl+C para detener el servidor")
        print("=" * 60)
        print()
        
        # Abrir navegador después de 1 segundo
        time.sleep(1)
        webbrowser.open(f"http://localhost:{config.PORT}")
        
        # 5. Iniciar servidor (bloqueante)
        server.start()
        
    except Exception as e:
        print(f"[!] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if 'audio_capture' in locals():
            audio_capture.stop_capture()

if __name__ == '__main__':
    sys.exit(main() or 0)