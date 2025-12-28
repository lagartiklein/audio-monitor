import sys, signal, threading, time, socket, os, webbrowser
from audio_server.audio_capture import AudioCapture
from audio_server.channel_manager import ChannelManager
from audio_server.native_server import NativeAudioServer
from audio_server.websocket_server import app, socketio, init_server
import config

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

def run_server():
    print("\n" + "="*60)
    print("  SERVIDOR AUDIO RF + WEB DIRECTO (SIN COLAS)")
    print("="*60)
    
    audio_capture = None
    native_server = None
    web_handler = None
    
    def cleanup():
        print("\n🛑 Deteniendo...")
        if native_server:
            native_server.stop()
        if audio_capture:
            audio_capture.stop_capture()
        print("✅ Detenido")
    
    def signal_handler(sig, frame):
        cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("🎙️ Inicializando captura RF DIRECTA...")
        audio_capture = AudioCapture()
        num_channels = audio_capture.start_capture()
        
        print("📡 Inicializando gestor de canales...")
        channel_manager = ChannelManager(num_channels)
        
        print("📱 Inicializando servidor nativo RF...")
        native_server = NativeAudioServer(channel_manager)
        native_server.start()
        
        # ✅ Registrar callback directo para RF
        audio_capture.register_callback(
            native_server.on_audio_data,
            name="native_server"
        )
        
        print("🌐 Inicializando servidor WebSocket...")
        
        # ✅ Crear handler para WebSocket
        class WebAudioHandler:
            def __init__(self):
                self.packet_count = 0
                
            def on_audio_data(self, audio_data):
                """Callback para enviar audio a clientes web"""
                self.packet_count += 1
                
                # Verificar que hay subscripciones
                if not hasattr(channel_manager, 'subscriptions'):
                    return
                
                for client_id, subscription in channel_manager.subscriptions.copy().items():
                    try:
                        if not isinstance(subscription, dict):
                            continue
                        
                        channels = subscription.get('channels', [])
                        if not channels:
                            continue
                        
                        gains = subscription.get('gains', {})
                        
                        # Enviar batch de canales
                        self._send_audio_batch(client_id, audio_data, channels, gains)
                        
                    except Exception as e:
                        pass  # Ignorar errores de clientes específicos
            
            def _send_audio_batch(self, client_id, audio_data, channels, gains):
                """Envío batch optimizado"""
                import struct
                import numpy as np
                
                try:
                    batch_data = []
                    
                    for channel in channels:
                        if channel >= audio_data.shape[1]:
                            continue
                        
                        channel_data = audio_data[:, channel].copy()
                        
                        # Aplicar ganancia
                        gain = gains.get(channel, 1.0)
                        if gain != 1.0:
                            channel_data = channel_data * gain
                        
                        batch_data.append((channel, channel_data))
                    
                    if not batch_data:
                        return
                    
                    # Crear paquete binario
                    packet_parts = [struct.pack('<I', len(batch_data))]
                    
                    for channel_id, channel_audio in batch_data:
                        audio_bytes = channel_audio.astype(np.float32).tobytes()
                        packet_parts.append(struct.pack('<I', channel_id))
                        packet_parts.append(struct.pack('<I', len(audio_bytes)))
                        packet_parts.append(audio_bytes)
                    
                    packet = b''.join(packet_parts)
                    socketio.emit('audio_batch', packet, to=client_id)
                    
                except Exception as e:
                    pass
        
        web_handler = WebAudioHandler()
        
        # ✅ Registrar callback para web
        audio_capture.register_callback(
            web_handler.on_audio_data,
            name="web_server"
        )
        
        # Inicializar servidor web (sin audio_queue, usa callbacks)
        init_server(channel_manager)
        
        local_ip = get_local_ip()
        print("\n" + "="*60)
        print("✅ SERVIDORES RF + WEB DIRECTOS LISTOS")
        print("="*60)
        print(f"🌐 IP Local: {local_ip}")
        print(f"📱 Puerto RF: {config.NATIVE_PORT}")
        print(f"🌐 Puerto Web: {config.WEB_PORT}")
        print(f"🎚️ Canales: {num_channels}")
        print(f"📦 Blocksize: {config.BLOCKSIZE} (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.1f}ms)")
        print(f"⚡ Modo: ENVÍO DIRECTO (sin colas)")
        print(f"📞 Callbacks: native_server, web_server")
        print("="*60)
        print("\n📋 COMANDOS:")
        print("   • 'status' - Ver estado")
        print("   • 'clients' - Listar clientes")
        print("   • 'stats' - Ver estadísticas")
        print("   • 'web' - Abrir navegador")
        print("   • 'quit' - Salir")
        print("="*60)
        
        # Abrir navegador automáticamente
        threading.Thread(
            target=lambda: (time.sleep(2), webbrowser.open(f"http://localhost:{config.WEB_PORT}")), 
            daemon=True
        ).start()
        
        # Comando loop
        def command_loop():
            while True:
                try:
                    cmd = input("\n> ").strip().lower()
                    
                    if cmd in ['q', 'quit', 'exit']:
                        cleanup()
                        os._exit(0)
                    
                    elif cmd == 'status':
                        print("📊 ESTADO:")
                        print(f"   📱 Clientes RF: {native_server.get_client_count()}")
                        print(f"   🌐 Clientes Web: {len(channel_manager.subscriptions)}")
                        print(f"   🎛️ Canales: {num_channels}")
                        print(f"   🎙️ Captura: {'Activa' if audio_capture.running else 'Inactiva'}")
                        print(f"   📦 Posición: {native_server.get_sample_position():,}")
                        print(f"   📞 Callbacks: {len(audio_capture.callbacks)}")
                    
                    elif cmd == 'clients':
                        with native_server.client_lock:
                            clients = list(native_server.clients.keys())
                            print(f"📱 Clientes RF: {len(clients)}")
                            for i, client_id in enumerate(clients, 1):
                                client = native_server.clients[client_id]
                                channels = len(client.subscribed_channels)
                                print(f"   {i}. {client_id[:20]} - {client.address[0]}")
                                print(f"       Canales: {channels}, Enviados: {client.packets_sent}, Perdidos: {client.packets_dropped}")
                        
                        print(f"\n🌐 Clientes Web: {len(channel_manager.subscriptions)}")
                        for i, client_id in enumerate(list(channel_manager.subscriptions.keys()), 1):
                            sub = channel_manager.subscriptions[client_id]
                            channels = len(sub.get('channels', []))
                            print(f"   {i}. {client_id[:8]} ({channels} canales)")
                    
                    elif cmd == 'stats':
                        stats = native_server.get_stats()
                        print("📊 ESTADÍSTICAS RF:")
                        print(f"   Paquetes enviados: {stats['packets_sent']:,}")
                        print(f"   Paquetes perdidos: {stats['packets_dropped']:,}")
                        print(f"   Desconexiones: {stats['clients_disconnected']}")
                        print(f"   Posición: {native_server.get_sample_position():,} samples")
                        print(f"   Tiempo: {native_server.get_sample_position()/config.SAMPLE_RATE:.1f}s")
                        print(f"\n📊 ESTADÍSTICAS WEB:")
                        print(f"   Paquetes procesados: {web_handler.packet_count:,}")
                    
                    elif cmd == 'web':
                        webbrowser.open(f"http://localhost:{config.WEB_PORT}")
                        print(f"🌐 Abriendo navegador: http://localhost:{config.WEB_PORT}")
                    
                    elif cmd == 'help':
                        print("📋 COMANDOS:")
                        print("   status  - Estado general")
                        print("   clients - Listar clientes RF y Web")
                        print("   stats   - Estadísticas detalladas")
                        print("   web     - Abrir navegador")
                        print("   quit    - Salir")
                    
                    elif cmd:
                        print(f"❌ Comando desconocido: '{cmd}'")
                        print("   Use 'help' para ver comandos")
                
                except (KeyboardInterrupt, EOFError):
                    cleanup()
                    os._exit(0)
                except Exception as e:
                    print(f"❌ Error: {e}")
        
        command_thread = threading.Thread(target=command_loop, daemon=True)
        command_thread.start()
        
        # Mantener vivo y ejecutar servidor WebSocket
        print(f"\n⚡ Servidores corriendo en modo DIRECTO...")
        print(f"   RF:  tcp://{local_ip}:{config.NATIVE_PORT}")
        print(f"   Web: http://{local_ip}:{config.WEB_PORT}")
        print(f"\nEsperando conexiones...\n")
        
        # Ejecutar servidor WebSocket (blocking)
        socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False, log_output=False)
        
    except KeyboardInterrupt:
        print("\n👋 Interrupción")
        return 0
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(run_server() or 0)