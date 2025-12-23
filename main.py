#!/usr/bin/env python3
"""
Audio Monitor - Sistema con WebRTC para ultra baja latencia
Versión final con soporte dual WebSocket/WebRTC
"""

import sys
import signal
import webbrowser
import time
import socket
import threading
import atexit

from backend.audio_capture import AudioCapture
from backend.channel_manager import ChannelManager
from backend.websocket_server import app, socketio, init_server, stop_audio_thread
import config_webrtc as config

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

# Variables globales para cleanup
audio_capture = None
channel_manager = None

def cleanup():
    """Limpieza completa del sistema"""
    print("\n[*] Realizando limpieza completa...")
    
    # Importar componentes WebRTC si existen
    try:
        from backend.webrtc_bridge import webrtc_bridge
        if webrtc_bridge:
            webrtc_bridge.stop()
            print("[*] WebRTC Bridge detenido")
    except ImportError:
        pass
    
    # Detener thread de audio del WebSocket server
    stop_audio_thread()
    
    # Detener captura de audio
    if audio_capture:
        audio_capture.stop_capture()
    
    print("[*] Limpieza completada")

def signal_handler(sig, frame):
    """Maneja Ctrl+C para cerrar limpiamente"""
    print("\n[*] Cerrando servidor...")
    cleanup()
    print("[*] ¡Servidor detenido! Adiós.")
    sys.exit(0)

def check_webrtc_dependencies():
    """Verifica dependencias WebRTC"""
    try:
        import aiortc
        import av
        print("[✓] Dependencias WebRTC disponibles")
        return True
    except ImportError as e:
        print(f"[!] Dependencias WebRTC faltantes: {e}")
        print("[*] Instala con: pip install aiortc av")
        return False

def main():
    global audio_capture, channel_manager
    
    print("=" * 70)
    print("  🎚️  Audio Monitor - WebRTC Ultra Low Latencia (<15ms)")
    print("=" * 70)
    print()
    
    # Verificar dependencias WebRTC
    webrtc_available = check_webrtc_dependencies()
    if not webrtc_available:
        print("[⚠] WebRTC no disponible, usando solo WebSocket")
        config.WEBRTC_ENABLED = False
    
    # Configurar signal handler y cleanup
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup)
    
    try:
        # 1. Inicializar captura de audio
        print("[*] Inicializando captura de audio...")
        audio_capture = AudioCapture()
        
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
        
        # Configurar sample rate
        config.SAMPLE_RATE = selected_device['sample_rate']
        print(f"[✓] Sample rate configurado: {config.SAMPLE_RATE} Hz")
        
        # Configurar jitter buffer
        config.JITTER_BUFFER_MS = int((config.BLOCKSIZE * 3 / config.SAMPLE_RATE) * 1000)
        print(f"[✓] Jitter buffer configurado: {config.JITTER_BUFFER_MS} ms")
        
        # Informar sobre WebRTC
        if config.WEBRTC_ENABLED:
            print(f"[⚡] WebRTC ACTIVADO - Latencia objetivo: {config.TARGET_LATENCY_MS}ms")
        else:
            print(f"[🌐] WebRTC desactivado - Usando WebSocket (~{config.JITTER_BUFFER_MS + 20}ms)")
        print()
        
        # Iniciar captura
        print("[*] Iniciando captura de audio...")
        num_channels = audio_capture.start_capture(selected_device['id'])
        
        # 2. Inicializar channel manager
        print("[*] Inicializando channel manager...")
        channel_manager = ChannelManager(num_channels)
        
        # 3. Inicializar servidores
        print("[*] Inicializando servidores...")
        init_server(audio_capture, channel_manager)
        
        # 4. Obtener URLs
        local_ip = get_local_ip()
        url_local = f"http://localhost:{config.PORT}"
        url_network = f"http://{local_ip}:{config.PORT}"
        
        print()
        print("=" * 70)
        print(f"[✓] Servidores iniciados exitosamente")
        print()
        print(f"  📱 URL Local:      {url_local}")
        print(f"  🌐 URL Red Local:  {url_network}")
        print()
        print(f"[*] Configuración:")
        print(f"    • Dispositivo: {selected_device['name']}")
        print(f"    • Canales: {num_channels}")
        print(f"    • Sample Rate: {config.SAMPLE_RATE} Hz")
        print(f"    • Blocksize: {config.BLOCKSIZE} samples ({config.BLOCKSIZE/config.SAMPLE_RATE*1000:.1f}ms)")
        print(f"    • Jitter Buffer: {config.JITTER_BUFFER_MS} ms")
        
        if config.WEBRTC_ENABLED:
            print(f"    • Protocolos: WebRTC (<{config.TARGET_LATENCY_MS}ms) + WebSocket (fallback)")
            latency_estimate = f"{config.TARGET_LATENCY_MS}ms (WebRTC)"
        else:
            print(f"    • Protocolo: WebSocket")
            latency_estimate = f"~{config.JITTER_BUFFER_MS + 20}ms"
        
        print(f"    • Latencia estimada: {latency_estimate}")
        print(f"    • Max clientes: {config.MAX_CLIENTS}")
        print()
        print("[*] El navegador se abrirá automáticamente en 2 segundos...")
        print("[*] Para dispositivos móviles, usa la URL de Red Local")
        print("[*] Presiona Ctrl+C para detener el servidor")
        print("=" * 70)
        print()
        
        # 5. Abrir navegador en thread separado
        def open_browser():
            time.sleep(2)
            try:
                webbrowser.open(url_local)
                print("[✓] Navegador abierto automáticamente")
            except:
                print("[!] No se pudo abrir el navegador automáticamente")
        
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
        
        # 6. Iniciar servidor Flask (bloqueante)
        print("[*] Iniciando servidor Flask-SocketIO...")
        socketio.run(
            app, 
            host=config.HOST, 
            port=config.PORT, 
            debug=False,
            use_reloader=False,
            log_output=False,
            allow_unsafe_werkzeug=True
        )
        
    except KeyboardInterrupt:
        print("\n[*] Detenido por usuario")
        return 0
        
    except Exception as e:
        print(f"\n[!] ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main() or 0)