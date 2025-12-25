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

    print("  ðŸŽ›ï¸  AUDIO MONITOR - Servidor Dual (Web + APK)")

    print("  âš¡ Latencia: APK 3-10ms | Web 20-40ms")

    print("=" * 70)

    print()



def run_web_mode():

    """Modo solo WebSocket para navegadores"""

    print("[*] Iniciando modo WEB...")

    

    # Importar mÃ³dulos web

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

        """Manejador de seÃ±al para modo web"""

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

            print("[!] Verifica que tu interfaz estÃ© conectada (>2 canales)")

            return 1

        

        print("[*] Interfaces de audio detectadas:")

        for idx, dev in enumerate(devices):

            marker = "âœ“" if idx == 0 else " "

            print(f"  [{marker}] {dev['name']}")

            print(f"      Canales: {dev['channels']} | Sample rate: {dev['sample_rate']} Hz")

        print()

        

        # Auto-seleccionar primera interfaz

        selected_device = devices[0]

        print(f"[âœ“] Auto-seleccionado: {selected_device['name']}")

        

        # Configurar sample rate

        config.SAMPLE_RATE = selected_device['sample_rate']

        print(f"[âœ“] Sample rate configurado: {config.SAMPLE_RATE} Hz")

        

        # Configurar jitter buffer

        config.WEB_JITTER_BUFFER = int((config.BLOCKSIZE * 3 / config.SAMPLE_RATE) * 1000)

        print(f"[âœ“] Jitter buffer configurado: {config.WEB_JITTER_BUFFER} ms")

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

        print(f"[âœ“] Servidor Web iniciado exitosamente")

        print()

        print(f"  ðŸ“± URL Local:      {url_local}")

        print(f"  ðŸŒ URL Red Local:  {url_network}")

        print()

        print(f"[*] ConfiguraciÃ³n:")

        print(f"    â€¢ Dispositivo: {selected_device['name']}")

        print(f"    â€¢ Canales: {num_channels}")

        print(f"    â€¢ Sample Rate: {config.SAMPLE_RATE} Hz")

        print(f"    â€¢ Blocksize: {config.BLOCKSIZE} samples ({config.BLOCKSIZE/config.SAMPLE_RATE*1000:.1f}ms)")

        print(f"    â€¢ Jitter Buffer: {config.WEB_JITTER_BUFFER} ms")

        print(f"    â€¢ Protocolo: WebSocket")

        latency_estimate = f"~{config.WEB_JITTER_BUFFER + 20}ms"

        print(f"    â€¢ Latencia estimada: {latency_estimate}")

        print(f"    â€¢ Max clientes: {config.MAX_CLIENTS}")

        print()

        print("[*] El navegador se abrirÃ¡ automÃ¡ticamente en 2 segundos...")

        print("[*] Para dispositivos mÃ³viles, usa la URL de Red Local")

        print("[*] Presiona Ctrl+C para detener el servidor")

        print("=" * 70)

        print()

        

        # 5. Abrir navegador en thread separado

        def open_browser():

            time.sleep(2)

            try:

                webbrowser.open(url_local)

                print("[âœ“] Navegador abierto automÃ¡ticamente")

            except:

                print("[!] No se pudo abrir el navegador automÃ¡ticamente")

        

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

        print(f"\n[!] ERROR CRÃTICO: {e}")

        import traceback

        traceback.print_exc()

        return 1

    

    return 0



def run_native_mode():

    """Modo solo Nativo para APK"""

    print("[*] Iniciando modo NATIVO (APK)...")

    

    # Importar mÃ³dulos nativos

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

        """Manejador de seÃ±al para modo nativo"""

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

        print(f"[âœ“] Dispositivo seleccionado: {selected_device['name']}")

        

        # Configurar sample rate

        config.SAMPLE_RATE = selected_device['sample_rate']

        print(f"[âœ“] Sample rate: {config.SAMPLE_RATE} Hz")

        

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

        print(f"[âœ“] Servidor Nativo iniciado exitosamente")

        print()

        print(f"  ðŸ“± IP del Servidor: {local_ip}")

        print(f"  ðŸ”Œ Puerto Nativo: {config.NATIVE_PORT}")

        print()

        print(f"[*] ConfiguraciÃ³n Nativa:")

        print(f"    â€¢ Dispositivo: {selected_device['name']}")

        print(f"    â€¢ Canales: {num_channels}")

        print(f"    â€¢ Sample Rate: {config.SAMPLE_RATE} Hz")

        print(f"    â€¢ Chunk Size: {config.NATIVE_CHUNK_SIZE} samples ({config.NATIVE_CHUNK_SIZE/config.SAMPLE_RATE*1000:.1f}ms)")

        print(f"    â€¢ Latencia objetivo: {config.NATIVE_LATENCY_TARGET}ms")

        print(f"    â€¢ Protocolo: TCP Nativo")

        print(f"    â€¢ Formato: PCM 16-bit")

        print(f"    â€¢ Max clientes APK: {config.NATIVE_MAX_CLIENTS}")

        print()

        print("[*] Conecta tu APK usando:")

        print(f"    â€¢ IP: {local_ip}")

        print(f"    â€¢ Puerto: {config.NATIVE_PORT}")

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

        print(f"\n[!] ERROR CRÃTICO: {e}")

        import traceback

        traceback.print_exc()

        return 1





# AÃ±ade esto al inicio de run_dual_mode() despuÃ©s de iniciar captura:



def run_dual_mode():

    """Modo DUAL (Web + APK) - CORREGIDO con Broadcaster"""

    print("[*] Iniciando modo DUAL (Web + APK)...")

    

    from audio_server.audio_capture import AudioCapture

    from audio_server.channel_manager import ChannelManager

    from audio_server.native_server import NativeAudioServer

    from audio_server.audio_broadcaster import AudioBroadcaster  # âœ… NUEVO

    

    from backend.websocket_server import app, socketio, init_server as init_web_server, stop_audio_thread

    

    import config

    

    # Variables globales

    audio_capture = None

    channel_manager = None

    native_server = None

    broadcaster = None  # âœ… NUEVO

    

    def cleanup_dual():

        """Limpieza completa"""

        print("\n[*] Limpieza completa modo Dual...")

        

        stop_audio_thread()

        

        # âœ… Detener broadcaster ANTES de los servidores

        if broadcaster:

            broadcaster.stop()

        

        if native_server:

            native_server.stop()

        

        if audio_capture:

            audio_capture.stop_capture()

        

        print("[*] Limpieza completada")

    

    def signal_handler(sig, frame):

        """Manejador de seÃ±al"""

        print("\n[*] Deteniendo servidores Dual...")

        cleanup_dual()

        sys.exit(0)

    

    signal.signal(signal.SIGINT, signal_handler)

    atexit.register(cleanup_dual)

    

    try:

        # 1. Inicializar captura de audio (IGUAL QUE ANTES)

        print("[*] Inicializando captura de audio...")

        audio_capture = AudioCapture()

        

        devices = audio_capture.list_devices()

        if not devices:

            print("[!] ERROR: No se encontraron interfaces de audio multi-canal")

            return 1

        

        selected_device = devices[0]

        print(f"[âœ“] Auto-seleccionado: {selected_device['name']}")

        

        config.SAMPLE_RATE = selected_device['sample_rate']

        config.WEB_JITTER_BUFFER = int((config.BLOCKSIZE * 3 / config.SAMPLE_RATE) * 1000)

        

        print("[*] Iniciando captura de audio...")

        num_channels = audio_capture.start_capture(selected_device['id'])

        

        # 2. Inicializar channel manager (IGUAL QUE ANTES)

        print("[*] Inicializando channel manager compartido...")

        channel_manager = ChannelManager(num_channels)

        

        # âœ… 3. CREAR Y INICIAR BROADCASTER

        print("[*] Inicializando Audio Broadcaster...")

        broadcaster = AudioBroadcaster(audio_capture, queue_size=config.QUEUE_SIZE)

        broadcaster.start()

        print("[âœ“] Broadcaster iniciado")

        

        # âœ… 4. REGISTRAR CONSUMIDORES Y ASIGNAR QUEUES

        

        # Queue para servidor nativo

        native_audio_queue = broadcaster.register_consumer("native")

        print("[âœ“] Queue para servidor Nativo registrada")

        

        # Queue para servidor websocket

        websocket_audio_queue = broadcaster.register_consumer("websocket")

        print("[âœ“] Queue para servidor WebSocket registrada")

        

        # âœ… 5. INICIAR SERVIDOR NATIVO CON SU QUEUE

        if config.NATIVE_ENABLED:

            print("[*] Iniciando servidor nativo para APK...")

            native_server = NativeAudioServer(audio_capture, channel_manager)

            

            # âœ… ASIGNAR queue del broadcaster

            native_server.audio_queue = native_audio_queue

            native_server.use_broadcaster = True

            

            native_server.start()

            print(f"[âœ“] Servidor APK en puerto {config.NATIVE_PORT}")

        

        # âœ… 6. INICIAR SERVIDOR WEB CON SU QUEUE

        if config.WEB_ENABLED:

            print("[*] Iniciando servidor Web...")

            

            # Importar y configurar el mÃ³dulo websocket_server

            import backend.websocket_server as ws_server

            

            # âœ… ASIGNAR queue del broadcaster

            ws_server.audio_broadcast_queue = websocket_audio_queue

            ws_server.use_broadcaster = True

            

            init_web_server(audio_capture, channel_manager)

            print(f"[âœ“] Servidor Web en puerto {config.WEB_PORT}")

        

        # 7. Obtener URLs e imprimir info (IGUAL QUE ANTES)

        local_ip = get_local_ip()

        

        print()

        print("=" * 70)

        print("[âœ“] SERVICIOS DUAL INICIADOS (con Broadcaster):")

        if config.NATIVE_ENABLED:

            print(f"  ðŸ“± APK Nativa:  tcp://{local_ip}:{config.NATIVE_PORT}")

        if config.WEB_ENABLED:

            print(f"  ðŸŒ Web Browser: http://{local_ip}:{config.WEB_PORT}")

        print()

        print(f"[*] Arquitectura:")

        print(f"    AudioCapture â†’ Broadcaster â†’ [WebSocket Queue + Native Queue]")

        print(f"    â€¢ Sin race conditions")

        print(f"    â€¢ Audio replicado sin pÃ©rdidas")

        print()

        print(f"[*] ConfiguraciÃ³n completa:")

        print(f"    â€¢ Dispositivo: {selected_device['name']}")

        print(f"    â€¢ Canales: {num_channels}")

        print(f"    â€¢ Sample Rate: {config.SAMPLE_RATE} Hz")

        print(f"    â€¢ Queue size por servidor: {config.QUEUE_SIZE}")

        print()

        

        if config.NATIVE_ENABLED:

            print(f"    ðŸ“± APK Nativa:")

            print(f"      â€¢ Puerto: {config.NATIVE_PORT}")

            print(f"      â€¢ Latencia: {config.NATIVE_LATENCY_TARGET}ms objetivo")

        

        if config.WEB_ENABLED:

            print(f"    ðŸŒ Web Browser:")

            print(f"      â€¢ Puerto: {config.WEB_PORT}")

            print(f"      â€¢ Latencia: ~{config.WEB_JITTER_BUFFER + 20}ms")

        

        print()

        print("[*] Presiona Ctrl+C para detener todos los servidores")

        print("=" * 70)

        print()

        

        # 8. Abrir navegador (IGUAL QUE ANTES)

        if config.WEB_ENABLED:

            def open_browser():

                time.sleep(2)

                try:

                    url_local = f"http://localhost:{config.WEB_PORT}"

                    webbrowser.open(url_local)

                    print("[âœ“] Navegador abierto automÃ¡ticamente")

                except:

                    print("[!] No se pudo abrir el navegador automÃ¡ticamente")

            

            browser_thread = threading.Thread(target=open_browser, daemon=True)

            browser_thread.start()

        

        # 9. Iniciar servidor Flask (bloqueante)

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

            print("[*] Servidor Nativo corriendo...")

            while True:

                time.sleep(1)

                

    except KeyboardInterrupt:

        print("\n[*] Servidores Dual detenidos")

        return 0

        

    except Exception as e:

        print(f"\n[!] ERROR CRÃTICO: {e}")

        import traceback

        traceback.print_exc()

        return 1











def main():

    """FunciÃ³n principal con selecciÃ³n de modo"""

    

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

                       help='Modo de operaciÃ³n (default: dual)')

    

    parser.add_argument('--verbose', '-v',

                       action='store_true',

                       help='Modo verboso (muestra mÃ¡s informaciÃ³n)')

    

    args = parser.parse_args()

    

    # Mostrar banner

    print_banner()

    

    # Configurar verbose si se especificÃ³

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