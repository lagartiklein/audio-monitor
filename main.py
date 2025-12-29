import sys, signal, threading, time, socket, os, webbrowser
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import struct

from audio_server.audio_capture import AudioCapture
from audio_server.channel_manager import ChannelManager
from audio_server.native_server import NativeAudioServer
from audio_server.websocket_server import app, socketio, init_server
import config
from gui_monitor import AudioMonitorGUI

class AudioServerApp:
    def __init__(self):
        self.audio_capture = None
        self.native_server = None
        self.web_handler = None
        self.channel_manager = None
        self.gui = None
        self.server_running = False
        
        # Configurar manejo de señales
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, sig, frame):
        self.cleanup()
        sys.exit(0)
    
    def get_current_stats(self):
        """Obtener estadísticas actuales para la GUI"""
        if not self.server_running:
            return {
                'clients_rf': 0,
                'clients_web': 0,
                'channels': 0,
                'sample_rate': config.SAMPLE_RATE,
                'blocksize': config.BLOCKSIZE,
                'position': 0,
                'packets_sent': 0,
                'packets_dropped': 0
            }
        
        stats = {
            'clients_rf': 0,
            'clients_web': 0,
            'channels': 0,
            'sample_rate': config.SAMPLE_RATE,
            'blocksize': config.BLOCKSIZE,
            'position': 0,
            'packets_sent': 0,
            'packets_dropped': 0
        }
        
        if self.native_server:
            server_stats = self.native_server.get_stats()
            stats.update({
                'clients_rf': self.native_server.get_client_count(),
                'position': self.native_server.get_sample_position(),
                'packets_sent': server_stats.get('packets_sent', 0),
                'packets_dropped': server_stats.get('packets_dropped', 0)
            })
        
        if self.channel_manager:
            stats.update({
                'clients_web': len(self.channel_manager.subscriptions),
                'channels': self.channel_manager.num_channels
            })
        
        return stats
    
    def start_server_with_device(self, device_id):
        """✅ OPTIMIZADO: Iniciar servidor con dispositivo específico"""
        if self.server_running:
            if self.gui:
                self.gui.queue_log_message("⚠️ El servidor ya está ejecutándose", 'WARNING')
            return
        
        try:
            if self.gui:
                self.gui.queue_log_message(f"🎙️ Iniciando servidor OPTIMIZADO con dispositivo ID: {device_id}", 'RF')
            
            # Inicializar captura de audio
            self.audio_capture = AudioCapture()
            num_channels = self.audio_capture.start_capture(device_id=device_id)
            
            # Inicializar gestor de canales
            self.channel_manager = ChannelManager(num_channels)
            
            # Inicializar servidor nativo
            self.native_server = NativeAudioServer(self.channel_manager)
            self.native_server.start()
            
            # ✅ Registrar callback directo para RF (sin copias)
            self.audio_capture.register_callback(
                self.native_server.on_audio_data,
                name="native_server"
            )
            
            # Inicializar handler WebSocket OPTIMIZADO
            self.setup_web_handler_optimized()
            
            # Inicializar servidor WebSocket
            init_server(self.channel_manager)
            
            # ✅ Registrar callback para web (con ThreadPool)
            self.audio_capture.register_callback(
                self.web_handler.on_audio_data,
                name="web_server"
            )
            
            self.server_running = True
            
            # Obtener información de red
            local_ip = self.get_local_ip()
            
            # Mostrar información en GUI
            if self.gui:
                self.gui.queue_log_message(f"✅ SERVIDOR OPTIMIZADO INICIADO", 'SUCCESS')
                self.gui.queue_log_message(f"", 'INFO')
                self.gui.queue_log_message(f"🌐 INFORMACIÓN DE RED:", 'INFO')
                self.gui.queue_log_message(f"   IP Local: {local_ip}", 'INFO')
                self.gui.queue_log_message(f"   Puerto RF: {config.NATIVE_PORT}", 'RF')
                self.gui.queue_log_message(f"   Puerto Web: {config.WEB_PORT}", 'WEB')
                self.gui.queue_log_message(f"", 'INFO')
                self.gui.queue_log_message(f"📊 CONFIGURACIÓN:", 'INFO')
                self.gui.queue_log_message(f"   Canales: {num_channels}", 'INFO')
                self.gui.queue_log_message(f"   Sample Rate: {config.SAMPLE_RATE} Hz", 'INFO')
                self.gui.queue_log_message(f"   Blocksize: {config.BLOCKSIZE} samples", 'INFO')
                self.gui.queue_log_message(f"   Latencia teórica: ~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms", 'SUCCESS')
                self.gui.queue_log_message(f"", 'INFO')
                self.gui.queue_log_message(f"⚡ OPTIMIZACIONES:", 'INFO')
                self.gui.queue_log_message(f"   Socket SNDBUF: {config.SOCKET_SNDBUF} bytes", 'RF')
                self.gui.queue_log_message(f"   TCP_NODELAY: {config.SOCKET_NODELAY}", 'RF')
                self.gui.queue_log_message(f"   Validación: {'OFF' if not config.VALIDATE_PACKETS else 'ON'}", 'RF')
                self.gui.queue_log_message(f"   Memoryview: {config.USE_MEMORYVIEW}", 'RF')
                self.gui.queue_log_message(f"   Web Async: {config.WEB_ASYNC_SEND}", 'WEB')
                self.gui.queue_log_message(f"   Compresión WS: OFF", 'WEB')
            
            # Iniciar servidor WebSocket en thread separado
            websocket_thread = threading.Thread(
                target=self.run_websocket_server,
                daemon=True
            )
            websocket_thread.start()
            
            # Abrir navegador automáticamente
            threading.Thread(
                target=lambda: (time.sleep(2), webbrowser.open(f"http://localhost:{config.WEB_PORT}")), 
                daemon=True
            ).start()
            
        except Exception as e:
            error_msg = f"❌ Error al iniciar servidor: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            if self.gui:
                self.gui.queue_log_message(error_msg, 'ERROR')
            self.cleanup()
    
    def setup_web_handler_optimized(self):
        """✅ OPTIMIZADO: Handler WebSocket con ThreadPool y envío directo"""
        class WebAudioHandler:
            def __init__(self):
                self.packet_count = 0
                self.channel_manager = None
                
                # ✅ ThreadPool para envío asíncrono
                if config.WEB_ASYNC_SEND:
                    self.executor = ThreadPoolExecutor(
                        max_workers=config.WEB_MAX_WORKERS,
                        thread_name_prefix="web_sender"
                    )
                else:
                    self.executor = None
                
            def on_audio_data(self, audio_data):
                """✅ OPTIMIZADO: Callback no-bloqueante"""
                self.packet_count += 1
                
                if not self.channel_manager or not hasattr(self.channel_manager, 'subscriptions'):
                    return
                
                # ✅ Convertir memoryview a ndarray solo una vez
                if isinstance(audio_data, memoryview):
                    audio_data = np.frombuffer(audio_data, dtype=np.float32)
                    # Reshape según número de canales del manager
                    num_channels = self.channel_manager.num_channels
                    audio_data = audio_data.reshape(-1, num_channels)
                
                # Snapshot de clientes
                clients = list(self.channel_manager.subscriptions.items())
                
                # ✅ Enviar en paralelo sin bloquear
                if self.executor:
                    for client_id, subscription in clients:
                        self.executor.submit(
                            self._send_client_async,
                            client_id,
                            audio_data,
                            subscription
                        )
                else:
                    # Modo síncrono (fallback)
                    for client_id, subscription in clients:
                        self._send_client_sync(client_id, audio_data, subscription)
            
            def _send_client_async(self, client_id, audio_data, subscription):
                """✅ Envío asíncrono por cliente"""
                try:
                    if not isinstance(subscription, dict):
                        return
                    
                    channels = subscription.get('channels', [])
                    gains = subscription.get('gains', {})
                    
                    if channels:
                        self._send_audio_optimized(client_id, audio_data, channels, gains)
                except:
                    pass
            
            def _send_client_sync(self, client_id, audio_data, subscription):
                """Envío síncrono (fallback)"""
                try:
                    if not isinstance(subscription, dict):
                        return
                    
                    channels = subscription.get('channels', [])
                    gains = subscription.get('gains', {})
                    
                    if channels:
                        self._send_audio_optimized(client_id, audio_data, channels, gains)
                except:
                    pass
            
            def _send_audio_optimized(self, client_id, audio_data, channels, gains):
                """✅ OPTIMIZADO: Envío por canal sin batch"""
                try:
                    timestamp = int(time.time() * 1000)
                    
                    for channel in channels:
                        if channel >= audio_data.shape[1]:
                            continue
                        
                        # Obtener datos del canal
                        channel_data = audio_data[:, channel]
                        
                        # Aplicar ganancia si es necesaria
                        gain = gains.get(channel, 1.0)
                        if gain != 1.0:
                            channel_data = channel_data * gain
                        
                        # ✅ Enviar directamente como binary (sin batch)
                        audio_bytes = channel_data.astype(np.float32).tobytes()
                        
                        # ✅ Usar binary mode para evitar conversión base64
                        socketio.emit('audio_channel', {
                            'channel': channel,
                            'timestamp': timestamp,
                            'data': audio_bytes
                        }, to=client_id, binary=True)
                        
                except Exception as e:
                    if config.DEBUG:
                        print(f"[WEB] Error envío: {e}")
            
            def cleanup(self):
                """Limpiar recursos"""
                if self.executor:
                    self.executor.shutdown(wait=False)
        
        self.web_handler = WebAudioHandler()
        self.web_handler.channel_manager = self.channel_manager
        
        if self.gui:
            if config.WEB_ASYNC_SEND:
                self.gui.queue_log_message(f"✅ Web handler: ASYNC con {config.WEB_MAX_WORKERS} workers", 'WEB')
            else:
                self.gui.queue_log_message(f"✅ Web handler: SYNC", 'WEB')
    
    def run_websocket_server(self):
        """Ejecutar servidor WebSocket"""
        try:
            socketio.run(
                app,
                host=config.WEB_HOST,
                port=config.WEB_PORT,
                debug=False,
                log_output=False,
                use_reloader=False
            )
        except Exception as e:
            error_msg = f"❌ Error en servidor WebSocket: {str(e)}"
            print(error_msg)
            if self.gui:
                self.gui.queue_log_message(error_msg, 'ERROR')
    
    def stop_server(self):
        """Detener servidor"""
        self.cleanup()
    
    def cleanup(self):
        """Limpiar recursos"""
        if self.gui:
            self.gui.queue_log_message("🛑 Deteniendo servidor...", 'WARNING')
        
        if self.native_server:
            self.native_server.stop()
            self.native_server = None
        
        if self.web_handler and hasattr(self.web_handler, 'cleanup'):
            self.web_handler.cleanup()
            self.web_handler = None
        
        if self.audio_capture:
            self.audio_capture.stop_capture()
            self.audio_capture = None
        
        self.server_running = False
        
        if self.gui:
            self.gui.queue_log_message("✅ Servidor detenido", 'SUCCESS')
    
    def get_local_ip(self):
        """Obtener IP local"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "localhost"
    
    def run(self):
        """Ejecutar aplicación principal"""
        print("\n" + "="*70)
        print("  FICHATECH MONITOR - Audio RF Server OPTIMIZED")
        print("="*70)
        print(f"  ⚡ Latencia objetivo: <5ms (RF) / <15ms (Web)")
        print(f"  📦 Blocksize: {config.BLOCKSIZE} samples (~{config.BLOCKSIZE/config.SAMPLE_RATE*1000:.2f}ms)")
        print(f"  🎯 Optimizaciones: Socket buffers, TCP_NODELAY, ThreadPool")
        print("="*70)
        print("🚀 Iniciando interfaz gráfica...\n")
        
        # Iniciar GUI
        self.gui = AudioMonitorGUI(self)
        
        # Ejecutar GUI
        self.gui.run()

def main():
    app = AudioServerApp()
    sys.exit(app.run() or 0)

if __name__ == '__main__':
    main()