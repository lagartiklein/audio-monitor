#!/usr/bin/env python3
"""
Audio Monitor - Sistema de Monitoreo Multi-canal via WiFi
Optimizado para latencia <25ms con auto-configuración
"""

import sys
import signal
import webbrowser
import time
import socket
import threading

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

# Variable global para cleanup
_server = None
_audio_capture = None

def signal_handler(sig, frame):
    """Maneja Ctrl+C para cerrar limpiamente"""
    print("\n[*] Cerrando servidor...")
    if _server:
        _server.stop()
    if _audio_capture:
        _audio_capture.stop_capture()
    sys.exit(0)

def main():
    global _server, _audio_capture
    
    print("=" * 70)
    print("  🎚️  Audio Monitor - Sistema Ultra-Baja Latencia (<25ms)")
    print("=" * 70)
    print()
    
    # Configurar signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 1. Inicializar captura de audio
        audio_capture = AudioCapture()
        _audio_capture = audio_capture
        
        # Listar dispositivos disponibles
        devices = audio_capture.list_devices()
        
        if not devices:
            print("[!] ERROR: No se encontraron interfaces de audio multi-canal")
            print("[!] Verifica que tu interfaz esté conectada (>2 canales)")
            print()
            print("    TIP: Instala drivers ASIO o configura WASAPI en Windows")
            return 1
        
        print("[*] Interfaces de audio detectadas:")
        for idx, dev in enumerate(devices):
            marker = "✓" if idx == 0 else " "
            print(f"  [{marker}] {dev['name']}")
            print(f"      Canales: {dev['channels']} | Sample rate: {dev['sample_rate']} Hz")
        print()
        
        # Auto-seleccionar primera interfaz
        selected_device = devices[0]
        print(f"[✓] Auto-seleccionado: {selected_device['name']}")
        
        # AUTO-CONFIGURAR sample rate
        config.SAMPLE_RATE = selected_device['sample_rate']
        print(f"[✓] Sample rate configurado: {config.SAMPLE_RATE} Hz")
        
        # AUTO-CONFIGURAR jitter buffer (3 bloques = ~8.7ms @ 44100Hz)
        config.JITTER_BUFFER_MS = int((config.BLOCKSIZE * 3 / config.SAMPLE_RATE) * 1000)
        print(f"[✓] Jitter buffer configurado: {config.JITTER_BUFFER_MS} ms")
        print()
        
        # Iniciar captura
        num_channels = audio_capture.start_capture(selected_device['id'])
        
        # 2. Inicializar channel manager
        channel_manager = ChannelManager(num_channels)
        
        # 3. Inicializar referencias globales
        init_server(audio_capture, channel_manager)
        
        # 4. Crear servidor WebSocket
        server = WebSocketServer(audio_capture, channel_manager)
        _server = server
        
        # 5. Obtener URLs
        local_ip = get_local_ip()
        url_local = f"http://localhost:{config.PORT}"
        url_network = f"http://{local_ip}:{config.PORT}"
        
        print()
        print("=" * 70)
        print(f"[✓] Servidor iniciado exitosamente")
        print()
        print(f"  📱 URL Local:      {url_local}")
        print(f"  🌐 URL Red Local:  {url_network}")
        print()
        print(f"[*] Configuración optimizada:")
        print(f"    • Sample Rate: {config.SAMPLE_RATE} Hz")
        print(f"    • Blocksize: {config.BLOCKSIZE} samples ({config.BLOCKSIZE/config.SAMPLE_RATE*1000:.1f}ms)")
        print(f"    • Jitter Buffer: {config.JITTER_BUFFER_MS} ms")
        print(f"    • Latencia estimada: ~{config.BLOCKSIZE/config.SAMPLE_RATE*1000 + config.JITTER_BUFFER_MS + 10:.0f}ms")
        print(f"    • Max clientes: {config.MAX_CLIENTS}")
        print()
        print("[*] El navegador se abrirá automáticamente en 2 segundos...")
        print("[*] Para dispositivos móviles, usa la URL de Red Local")
        print("[*] Presiona Ctrl+C para detener el servidor")
        print("=" * 70)
        print()
        
        # Abrir navegador en thread separado
        def open_browser():
            time.sleep(2)
            try:
                webbrowser.open(url_local)
                print("[✓] Navegador abierto automáticamente")
            except:
                print("[!] No se pudo abrir el navegador automáticamente")
        
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
        
        # 6. Iniciar servidor (bloqueante)
        server.start()
        
    except KeyboardInterrupt:
        print("\n[*] Detenido por usuario")
        return 0
        
    except Exception as e:
        print(f"\n[!] ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Limpieza
        if _audio_capture:
            _audio_capture.stop_capture()
        if _server:
            _server.stop()

if __name__ == '__main__':
    sys.exit(main() or 0)