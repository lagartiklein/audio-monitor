
import sys
import signal
import webbrowser
import time
import socket
import threading
import atexit
import argparse
import os

def get_local_ip():
    """Obtiene la IP local"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

def print_banner():
    """Imprime banner del sistema"""
    print("=" * 70)
    print("  🎛️  AUDIO MONITOR - Servidor Dual (Web + APK)")
    print("  ⚡ Latencia: APK 3-10ms | Web 20-40ms")
    print("=" * 70)
    print()

def run_web_mode():
    """Modo solo WebSocket para navegadores"""
    print("[*] Iniciando modo WEB...")
    
    # Importar módulos web
    from audio_server.audio_capture import AudioCapture
    from audio_server.channel_manager import ChannelManager
    from backend.websocket_server import app, socketio, init_server, stop_audio_thread
    
    import config
    
    # Variables globales
    audio_capture = None
    channel_manager = None
    
    def cleanup_web():
        """Limpieza para modo web"""
        print("\n[*] Limpiando modo Web...")
        stop_audio_thread()
        if audio_capture:
            audio_capture.stop_capture()
    
    def signal_handler(sig, frame):
        """Manejador de señal para modo web"""
        print("\n[*] Deteniendo servidor Web...")
        cleanup_web()
        sys.exit(0)
    
    # Configurar handlers
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_web)
    
    try:
        # 1. Inicializar captura de audio
        print("[*] Inicializando captura de audio...")
        audio_capture = AudioCapture()
        
        # Listar dispositivos disponibles
        devices = audio_capture.list_devices()
        
        if not devices:
            print("[!] ERROR: No se encontraron interfaces de audio multi-canal")
            print("[!] Verifica que tu interfaz esté conectada (>2 canales)")
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
        config.WEB_JITTER_BUFFER = int((config.BLOCKSIZE * 3 / config.SAMPLE_RATE) * 1000)
        print(f"[✓] Jitter buffer configurado: {config.WEB_JITTER_BUFFER} ms")
        print()
        
        # Iniciar captura
        print("[*] Iniciando captura de audio...")
        num_channels = audio_capture.start_capture(selected_device['id'])
        
        # 2. Inicializar channel manager
        print("[*] Inicializando channel manager...")
        channel_manager = ChannelManager(num_channels)
        
        # 3. Inicializar servidor WebSocket
        print("[*] Inicializando servidor WebSocket...")
        init_server(audio_capture, channel_manager)
        
        # 4. Obtener URLs
        local_ip = get_local_ip()
        url_local = f"http://localhost:{config.WEB_PORT}"
        url_network = f"http://{local_ip}:{config.WEB_PORT}"
        
        print()
        print("=" * 70)
        print(f"[✓] Servidor Web iniciado exitosamente")
        print()
        print(f"  📱 URL Local:      {url_local}")
        print(f"  🌐 URL Red Local:  {url_network}")
        print()
        print(f"[*] Configuración:")
        print(f"    • Dispositivo: {selected_device['name']}")
        print(f"    • Canales: {num_channels}")
        print(f"    • Sample Rate: {config.SAMPLE_RATE} Hz")
        print(f"    • Blocksize: {config.BLOCKSIZE} samples ({config.BLOCKSIZE/config.SAMPLE_RATE*1000:.1f}ms)")
        print(f"    • Jitter Buffer: {config.WEB_JITTER_BUFFER} ms")
        print(f"    • Protocolo: WebSocket")
        latency_estimate = f"~{config.WEB_JITTER_BUFFER + 20}ms"
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
            host=config.WEB_HOST, 
            port=config.WEB_PORT, 
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
    
    return 0

def run_native_mode():
    """Modo solo Nativo para APK"""
    print("[*] Iniciando modo NATIVO (APK)...")
    
    # Importar módulos nativos
    from audio_server.audio_capture import AudioCapture
    from audio_server.channel_manager import ChannelManager
    from audio_server.native_server import NativeAudioServer
    
    import config
    
    # Variables globales
    audio_capture = None
    channel_manager = None
    native_server = None
    
    def cleanup_native():
        """Limpieza para modo nativo"""
        print("\n[*] Limpiando modo Nativo...")
        if native_server:
            native_server.stop()
        if audio_capture:
            audio_capture.stop_capture()
    
    def signal_handler(sig, frame):
        """Manejador de señal para modo nativo"""
        print("\n[*] Deteniendo servidor Nativo...")
        cleanup_native()
        sys.exit(0)
    
    # Configurar handlers
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_native)
    
    try:
        # 1. Inicializar captura de audio
        print("[*] Inicializando captura de audio...")
        audio_capture = AudioCapture()
        
        # Listar dispositivos disponibles
        devices = audio_capture.list_devices()
        
        if not devices:
            print("[!] ERROR: No se encontraron interfaces de audio multi-canal")
            return 1
        
        selected_device = devices[0]
        print(f"[✓] Dispositivo seleccionado: {selected_device['name']}")
        
        # Configurar sample rate
        config.SAMPLE_RATE = selected_device['sample_rate']
        print(f"[✓] Sample rate: {config.SAMPLE_RATE} Hz")
        
        # Iniciar captura
        print("[*] Iniciando captura de audio...")
        num_channels = audio_capture.start_capture(selected_device['id'])
        
        # 2. Inicializar channel manager
        print("[*] Inicializando channel manager...")
        channel_manager = ChannelManager(num_channels)
        
        # 3. Crear y ejecutar servidor nativo
        print("[*] Iniciando servidor Nativo para APK...")
        native_server = NativeAudioServer(audio_capture, channel_manager)
        native_server.start()
        
        # 4. Obtener IP
        local_ip = get_local_ip()
        
        print()
        print("=" * 70)
        print(f"[✓] Servidor Nativo iniciado exitosamente")
        print()
        print(f"  📱 IP del Servidor: {local_ip}")
        print(f"  🔌 Puerto Nativo: {config.NATIVE_PORT}")
        print()
        print(f"[*] Configuración Nativa:")
        print(f"    • Dispositivo: {selected_device['name']}")
        print(f"    • Canales: {num_channels}")
        print(f"    • Sample Rate: {config.SAMPLE_RATE} Hz")
        print(f"    • Chunk Size: {config.NATIVE_CHUNK_SIZE} samples ({config.NATIVE_CHUNK_SIZE/config.SAMPLE_RATE*1000:.1f}ms)")
        print(f"    • Latencia objetivo: {config.NATIVE_LATENCY_TARGET}ms")
        print(f"    • Protocolo: TCP Nativo")
        print(f"    • Formato: PCM 16-bit")
        print(f"    • Max clientes APK: {config.NATIVE_MAX_CLIENTS}")
        print()
        print("[*] Conecta tu APK usando:")
        print(f"    • IP: {local_ip}")
        print(f"    • Puerto: {config.NATIVE_PORT}")
        print()
        print("[*] Presiona Ctrl+C para detener el servidor")
        print("=" * 70)
        print()
        
        # Mantener el programa corriendo
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[*] Servidor Nativo detenido")
        return 0
        
    except Exception as e:
        print(f"\n[!] ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        return 1

def run_dual_mode():
    """Modo DUAL (Web + APK) - Recomendado"""
    print("[*] Iniciando modo DUAL (Web + APK)...")
    
    # Importar módulos duales
    from audio_server.audio_capture import AudioCapture
    from audio_server.channel_manager import ChannelManager
    from audio_server.native_server import NativeAudioServer
    
    # También necesitamos el servidor web
    from backend.websocket_server import app, socketio, init_server as init_web_server, stop_audio_thread
    
    import config
    
    # Variables globales
    audio_capture = None
    channel_manager = None
    native_server = None
    
    def cleanup_dual():
        """Limpieza completa para modo dual"""
        print("\n[*] Limpieza completa modo Dual...")
        
        # Detener thread de audio del WebSocket server
        stop_audio_thread()
        
        # Detener servidor nativo
        if native_server:
            native_server.stop()
        
        # Detener captura de audio
        if audio_capture:
            audio_capture.stop_capture()
        
        print("[*] Limpieza completada")
    
    def signal_handler(sig, frame):
        """Manejador de señal para modo dual"""
        print("\n[*] Deteniendo servidores Dual...")
        cleanup_dual()
        sys.exit(0)
    
    # Configurar handlers
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_dual)
    
    try:
        # 1. Inicializar captura de audio
        print("[*] Inicializando captura de audio...")
        audio_capture = AudioCapture()
        
        # Listar dispositivos disponibles
        devices = audio_capture.list_devices()
        
        if not devices:
            print("[!] ERROR: No se encontraron interfaces de audio multi-canal")
            return 1
        
        print("[*] Interfaces de audio detectadas:")
        for idx, dev in enumerate(devices):
            marker = "✓" if idx == 0 else " "
            print(f"  [{marker}] {dev['name']} ({dev['channels']} canales, {dev['sample_rate']} Hz)")
        print()
        
        # Auto-seleccionar primera interfaz
        selected_device = devices[0]
        print(f"[✓] Auto-seleccionado: {selected_device['name']}")
        
        # Configurar sample rate
        config.SAMPLE_RATE = selected_device['sample_rate']
        print(f"[✓] Sample rate configurado: {config.SAMPLE_RATE} Hz")
        
        # Configurar jitter buffer para web
        config.WEB_JITTER_BUFFER = int((config.BLOCKSIZE * 3 / config.SAMPLE_RATE) * 1000)
        print(f"[✓] Jitter buffer Web: {config.WEB_JITTER_BUFFER} ms")
        print()
        
        # Iniciar captura
        print("[*] Iniciando captura de audio...")
        num_channels = audio_capture.start_capture(selected_device['id'])
        
        # 2. Inicializar channel manager (compartido)
        print("[*] Inicializando channel manager compartido...")
        channel_manager = ChannelManager(num_channels)
        
        # 3. INICIAR SERVIDOR APK NATIVA
        if config.NATIVE_ENABLED:
            print("[*] Iniciando servidor nativo para APK...")
            native_server = NativeAudioServer(audio_capture, channel_manager)
            native_server.start()
            print(f"[✓] Servidor APK en puerto {config.NATIVE_PORT}")
            print(f"    • Latencia objetivo: {config.NATIVE_LATENCY_TARGET}ms")
            print(f"    • Formato: PCM 16-bit")
            print(f"    • Chunk: {config.NATIVE_CHUNK_SIZE} samples")
        
        # 4. Iniciar servidor Web
        if config.WEB_ENABLED:
            print("[*] Iniciando servidor Web...")
            init_web_server(audio_capture, channel_manager)
            print(f"[✓] Servidor Web en puerto {config.WEB_PORT}")
            print(f"    • Latencia: ~{config.WEB_LATENCY_TARGET}ms")
        
        # 5. Obtener URLs
        local_ip = get_local_ip()
        
        print()
        print("=" * 70)
        print("[✓] SERVICIOS DUAL INICIADOS:")
        if config.NATIVE_ENABLED:
            print(f"  📱 APK Nativa:  tcp://{local_ip}:{config.NATIVE_PORT}")
        if config.WEB_ENABLED:
            print(f"  🌐 Web Browser: http://{local_ip}:{config.WEB_PORT}")
        print()
        print(f"[*] Configuración completa:")
        print(f"    • Dispositivo: {selected_device['name']}")
        print(f"    • Canales: {num_channels}")
        print(f"    • Sample Rate: {config.SAMPLE_RATE} Hz")
        print()
        
        if config.NATIVE_ENABLED:
            print(f"    📱 APK Nativa:")
            print(f"      • Puerto: {config.NATIVE_PORT}")
            print(f"      • Latencia: {config.NATIVE_LATENCY_TARGET}ms objetivo")
            print(f"      • Formato: PCM 16-bit")
        
        if config.WEB_ENABLED:
            print(f"    🌐 Web Browser:")
            print(f"      • Puerto: {config.WEB_PORT}")
            print(f"      • Latencia: ~{config.WEB_JITTER_BUFFER + 20}ms")
            print(f"      • Protocolo: WebSocket")
        
        print()
        print("[*] El navegador se abrirá automáticamente en 2 segundos...")
        print("[*] Para APK, usa la IP mostrada arriba")
        print("[*] Presiona Ctrl+C para detener todos los servidores")
        print("=" * 70)
        print()
        
        # 6. Abrir navegador en thread separado
        if config.WEB_ENABLED:
            def open_browser():
                time.sleep(2)
                try:
                    url_local = f"http://localhost:{config.WEB_PORT}"
                    webbrowser.open(url_local)
                    print("[✓] Navegador abierto automáticamente")
                except:
                    print("[!] No se pudo abrir el navegador automáticamente")
            
            browser_thread = threading.Thread(target=open_browser, daemon=True)
            browser_thread.start()
        
        # 7. Iniciar servidor Flask (bloqueante)
        if config.WEB_ENABLED:
            print("[*] Iniciando servidor Flask-SocketIO...")
            socketio.run(
                app, 
                host=config.WEB_HOST, 
                port=config.WEB_PORT, 
                debug=False,
                use_reloader=False,
                log_output=False,
                allow_unsafe_werkzeug=True
            )
        else:
            # Si no hay web, mantener vivo
            print("[*] Servidor Nativo corriendo...")
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\n[*] Servidores Dual detenidos")
        return 0
        
    except Exception as e:
        print(f"\n[!] ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        return 1

def main():
    """Función principal con selección de modo"""
    
    # Parsear argumentos
    parser = argparse.ArgumentParser(
        description='Audio Monitor - Servidor de audio en tiempo real',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  %(prog)s              # Inicia modo DUAL (por defecto)
  %(prog)s --mode web   # Solo servidor Web para navegadores
  %(prog)s --mode native # Solo servidor Nativo para APK
  %(prog)s --mode dual   # Ambos servidores (Web + APK)
        """
    )
    
    parser.add_argument('--mode', 
                       choices=['web', 'native', 'dual'], 
                       default='dual',
                       help='Modo de operación (default: dual)')
    
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Modo verboso (muestra más información)')
    
    args = parser.parse_args()
    
    # Mostrar banner
    print_banner()
    
    # Configurar verbose si se especificó
    import config
    if args.verbose:
        config.VERBOSE = True
        print("[*] Modo verboso activado")
    
    # Ejecutar modo seleccionado
    if args.mode == 'web':
        print(f"[*] Modo seleccionado: WEB (puerto {config.WEB_PORT})")
        return run_web_mode()
    
    elif args.mode == 'native':
        print(f"[*] Modo seleccionado: NATIVO (puerto {config.NATIVE_PORT})")
        return run_native_mode()
    
    else:  # dual
        print(f"[*] Modo seleccionado: DUAL (Web:{config.WEB_PORT} + APK:{config.NATIVE_PORT})")
        return run_dual_mode()

if __name__ == '__main__':
    sys.exit(main() or 0)