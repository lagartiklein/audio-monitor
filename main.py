import sys, signal, threading, time, socket, argparse, os, webbrowser

from datetime import datetime

import queue



def get_local_ip():

    try:

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        s.connect(("8.8.8.8", 80))

        ip = s.getsockname()[0]

        s.close()

        return ip

    except:

        return "localhost"



def print_banner():

    print("\n" + "="*60)

    print("       SERVIDOR DE AUDIO MULTICANAL")

    print("="*60)

    print(f"⏰ Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("="*60)



def run_dual_mode():

    print_banner()

    print("🚀 Iniciando modo DUAL (Nativo + Web)...")

    

    from audio_server.audio_capture import AudioCapture

    from audio_server.channel_manager import ChannelManager

    from audio_server.native_server import NativeAudioServer

    from audio_server.audio_broadcaster import AudioBroadcaster

    from audio_server.websocket_server import app, socketio, init_server, start_audio_thread

    

    import config

 

    audio_capture = None

    native_server = None

    broadcaster = None

    

    def cleanup():

        print("\n" + "="*60)

        print("🛑 Deteniendo servidor...")

        print("="*60)

        

        if broadcaster: 

            print("🔌 Deteniendo broadcaster...")

            broadcaster.stop()

        if native_server: 

            print("🔌 Deteniendo servidor nativo...")

            native_server.stop()

        if audio_capture: 

            print("🎙️  Deteniendo captura de audio...")

            audio_capture.stop_capture()

        

        print("✅ Servidor detenido correctamente")

        print("="*60)

    

    def signal_handler(sig, frame):

        print(f"\n⚠️  Señal {sig} recibida, deteniendo...")

        cleanup()

        sys.exit(0)

    

    signal.signal(signal.SIGINT, signal_handler)

    signal.signal(signal.SIGTERM, signal_handler)

    

    try:

        print("🔧 Inicializando componentes...")

        

        # 1. Captura de audio

        print("🎙️  Inicializando captura de audio...")

        audio_capture = AudioCapture()

        devices = audio_capture.list_devices()

        

        if not devices:

            print("❌ No se encontraron interfaces de audio multicanal")

            return 1

        

        print(f"✅ Encontradas {len(devices)} interfaces:")

        for i, device in enumerate(devices):

            print(f"   {i+1}. {device['name']} ({device['channels']} canales)")

        

        num_channels = audio_capture.start_capture(devices[0]['id'])

        print(f"✅ Captura iniciada: {num_channels} canales")

        

        # 2. Channel Manager

        print("📡 Inicializando gestor de canales...")

        channel_manager = ChannelManager(num_channels)

        

        # 3. Broadcaster

        print("📡 Inicializando broadcaster...")

        broadcaster = AudioBroadcaster(audio_capture)

        broadcaster.start()

        

        # 4. Colas de audio

        print("🔗 Creando colas de audio...")

        web_audio_queue = broadcaster.register_consumer("websocket")

        native_audio_queue = broadcaster.register_consumer("native")

        

        # 5. Servidor nativo

        print("📱 Inicializando servidor nativo...")

        native_server = NativeAudioServer(audio_capture, channel_manager)

        native_server.use_broadcaster = True

        native_server.audio_queue = native_audio_queue

        native_server.start()

        

        # 6. Servidor WebSocket

        print("🌐 Inicializando servidor WebSocket...")

        init_server(audio_capture, channel_manager, web_audio_queue)

        start_audio_thread()

        

        # Mostrar información de conexión

        local_ip = get_local_ip()

        print("\n" + "="*60)

        print("✅ SERVIDOR LISTO")

        print("="*60)

        print(f"🌐 IP Local: {local_ip}")

        print(f"📱 Puerto Nativo: {config.NATIVE_PORT}")

        print(f"🌐 Puerto Web: {config.WEB_PORT}")

        print(f"🎚️  Canales: {num_channels}")

        print(f"⏱️  Sample Rate: {config.SAMPLE_RATE} Hz")

        print(f"📦 Block Size: {config.BLOCKSIZE} samples")

        print("="*60)

        print("\n📋 COMANDOS DISPONIBLES:")

        print("   • 'status' - Ver estado del servidor")

        print("   • 'clients' - Listar clientes conectados")

        print("   • 'stats' - Ver estadísticas")

        print("   • 'debug' - Debug del sistema")

        print("   • 'quit' o Ctrl+C - Salir")

        print("="*60 + "\n")

        

        # Abrir navegador automáticamente

        threading.Thread(

            target=lambda: (time.sleep(2), webbrowser.open(f"http://localhost:{config.WEB_PORT}")), 

            daemon=True

        ).start()

        

        # Comando interactivo

        def command_loop():

            while True:

                try:

                    cmd = input("> ").strip().lower()

                    

                    if cmd in ['q', 'quit', 'exit']:

                        print("👋 Saliendo...")

                        cleanup()

                        os._exit(0)

                    

                    elif cmd == 'status':

                        if native_server:

                            native_server.print_status()

                        else:

                            print("⚠️  Servidor nativo no disponible")

                    

                    elif cmd == 'clients':

                        if native_server:

                            with native_server.client_lock:

                                clients = list(native_server.clients.keys())

                                print(f"👥 Clientes conectados: {len(clients)}")

                                for i, client_id in enumerate(clients, 1):

                                    client = native_server.clients[client_id]

                                    print(f"   {i}. {client_id[:15]} - {client.address[0]}")

                        else:

                            print("⚠️  Servidor nativo no disponible")

                    

                    elif cmd == 'stats':

                        if native_server:

                            print("📊 ESTADÍSTICAS:")

                            print(f"   Paquetes enviados: {native_server.stats['total_packets_sent']:,}")

                            print(f"   Bytes enviados: {native_server.stats['bytes_sent']:,}")

                            print(f"   Errores de audio: {native_server.stats['audio_errors']}")

                        else:

                            print("⚠️  Servidor nativo no disponible")

                    

                    elif cmd == 'debug':

                        print("\n" + "="*60)

                        print("🐛 DEBUG DEL SISTEMA")

                        print("="*60)

                        

                        # Estado del audio capture

                        if audio_capture:

                            if audio_capture.stream and audio_capture.running:

                                queue_size = audio_capture.audio_queue.qsize()

                                print(f"🎙️  CAPTURA DE AUDIO: ACTIVA")

                                print(f"   Cola: {queue_size} bloques")

                                print(f"   Canales: {audio_capture.actual_channels}")

                            else:

                                print(f"🎙️  CAPTURA DE AUDIO: INACTIVA")

                        

                        # Estado del broadcaster

                        if broadcaster:

                            b_stats = broadcaster.get_stats()

                            print(f"🎙️  BROADCASTER:")

                            print(f"   📦 Paquetes totales: {b_stats['total_packets']:,}")

                            print(f"   🔗 Consumidores: {b_stats['active_consumers']}")

                            for consumer, queue in broadcaster.output_queues.items():

                                print(f"   📊 '{consumer}': cola={queue.qsize()}")

                        

                        # Estado del servidor nativo

                        if native_server:

                            print(f"📱 SERVIDOR NATIVO:")

                            print(f"   🟢 Corriendo: {native_server.running}")

                            print(f"   👥 Clientes: {len(native_server.clients)}")

                            print(f"   📦 Paquetes enviados: {native_server.stats['total_packets_sent']:,}")

                            

                            if native_server.stats['total_packets_sent'] == 0:

                                print(f"   ⚠️  ¡ALERTA! No se han enviado paquetes de audio")

                        

                        print("="*60 + "\n")

                    

                    elif cmd == 'help':

                        print("📋 COMANDOS:")

                        print("   status    - Ver estado del servidor")

                        print("   clients   - Listar clientes conectados")

                        print("   stats     - Ver estadísticas")

                        print("   debug     - Debug del sistema")

                        print("   quit      - Salir del servidor")

                        print("   help      - Mostrar esta ayuda")

                    

                    elif cmd:

                        print(f"❌ Comando desconocido: '{cmd}'")

                        print("   Escribe 'help' para ver comandos disponibles")

                

                except (KeyboardInterrupt, EOFError):

                    print("\n👋 Saliendo...")

                    cleanup()

                    os._exit(0)

                except Exception as e:

                    print(f"❌ Error en comando: {e}")

        

        # Iniciar loop de comandos en thread separado

        command_thread = threading.Thread(target=command_loop, daemon=True)

        command_thread.start()

        

        # Ejecutar servidor WebSocket

        if __name__ == '__main__':

            print(f"🌐 Iniciando servidor Web en http://{local_ip}:{config.WEB_PORT}")

            socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False, log_output=False)

        

    except KeyboardInterrupt:

        print("\n👋 Interrupción por teclado")

        return 0

    except Exception as e:

        print(f"❌ ERROR CRÍTICO: {e}")

        import traceback

        traceback.print_exc()

        return 1



def main():

    parser = argparse.ArgumentParser(description='Audio Server')

    parser.add_argument('--mode', choices=['web', 'native', 'dual'], default='dual')

    parser.add_argument('--verbose', '-v', action='store_true', help='Mostrar logs detallados')

    parser.add_argument('--port', type=int, default=5101, help='Puerto para servidor nativo')

    parser.add_argument('--web-port', type=int, default=5100, help='Puerto para servidor web')

    args = parser.parse_args()

    

    if args.verbose:

        import config

        config.VERBOSE = True

    

    # Actualizar puertos si se especifican

    if args.port != 5101:

        import config

        config.NATIVE_PORT = args.port

    

    if args.web_port != 5100:

        import config

        config.WEB_PORT = args.web_port

    

    return run_dual_mode()



if __name__ == '__main__':

    sys.exit(main() or 0)