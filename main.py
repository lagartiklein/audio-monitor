import sys, signal, threading, time, socket, os, webbrowser

from concurrent.futures import ThreadPoolExecutor

import numpy as np

import struct



# ✅ NUEVO: Función para obtener rutas correctas en exe

def get_base_path():

    """Obtener ruta base que funciona tanto en desarrollo como en exe"""

    if getattr(sys, 'frozen', False):

        # Ejecutando como exe de PyInstaller

        return sys._MEIPASS

    else:

        # Ejecutando como script Python

        return os.path.dirname(os.path.abspath(__file__))



# ✅ NUEVO: Configurar rutas antes de imports

sys.path.insert(0, get_base_path())



from audio_server.audio_capture import AudioCapture

from audio_server.channel_manager import ChannelManager

from audio_server.native_server import NativeAudioServer

from audio_server.websocket_server import app, socketio, init_server

from audio_server.scene_manager import SceneManager  # ✅ NUEVO

import config

from gui_monitor import AudioMonitorGUI



# ✅ NUEVO: Función de integración de persistencia

def integrate_persistence_with_native_server(native_server, channel_manager):

    """

    Integrar sistema de persistencia con el servidor nativo

    """

    class ConfigPersistence:

        def __init__(self):

            self.client_configs = {}

        

        def save_client_config(self, address, channels, gains, pans):

            """Guardar configuración de cliente"""

            self.client_configs[address] = {

                'channels': channels,

                'gains': gains,

                'pans': pans,

                'timestamp': time.time()

            }

        

        def get_stats(self):

            """Obtener estadísticas"""

            return {

                'total_clients': len(self.client_configs)

            }

    

    return ConfigPersistence()



class AudioServerApp:

    def __init__(self):

        self.audio_capture = None

        self.native_server = None

        self.web_handler = None

        self.channel_manager = None

        self.gui = None

        self.server_running = False

        self.config_persistence = None

        self.scene_manager = None  # ✅ NUEVO

        self.selected_device_id = -1  # ✅ NUEVO: guardar device_id seleccionado

        

        # Configurar manejo de señales

        signal.signal(signal.SIGINT, self.signal_handler)

        signal.signal(signal.SIGTERM, self.signal_handler)

    

    def signal_handler(self, sig, frame):

        """Manejar señales de interrupción"""

        print("\n[Main] 🛑 Señal de interrupción recibida")

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

            

            # ✅ GUARDAR device_id seleccionado (para SceneManager)

            self.selected_device_id = device_id

            

            # Inicializar captura de audio

            self.audio_capture = AudioCapture()

            # ✅ También guardar en audio_capture para SceneManager

            self.audio_capture.selected_device_id = device_id

            num_channels = self.audio_capture.start_capture(device_id=device_id)

            

            # Inicializar gestor de canales

            self.channel_manager = ChannelManager(num_channels)

            

            # Inicializar servidor nativo

            self.native_server = NativeAudioServer(self.channel_manager)

            self.native_server.start()

            

            # ✅ NUEVO: Integrar sistema de persistencia

            self.config_persistence = integrate_persistence_with_native_server(

                self.native_server,

                self.channel_manager

            )

            

            if self.gui:

                self.gui.queue_log_message("💾 Sistema de persistencia activado", 'SUCCESS')

                stats = self.config_persistence.get_stats()

                self.gui.queue_log_message(f"   Configs cargadas: {stats['total_clients']}", 'INFO')

            

            # ✅ NUEVO: Inicializar SceneManager

            self.scene_manager = SceneManager(scenes_dir='scenes')

            self.scene_manager.set_main_app(self)

            

            if self.gui:

                self.gui.queue_log_message("🎬 Sistema de escenas activado", 'SUCCESS')

                scene_stats = self.scene_manager.get_stats()

                self.gui.queue_log_message(f"   Escenas disponibles: {scene_stats['total_scenes']}", 'INFO')

            

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

                self.gui.queue_log_message(f"", 'INFO')

                self.gui.queue_log_message(f"🌐 URLS DE ACCESO:", 'SUCCESS')

                self.gui.queue_log_message(f"   Local: http://localhost:{config.WEB_PORT}", 'WEB')

                self.gui.queue_log_message(f"   Red: http://{local_ip}:{config.WEB_PORT}", 'WEB')

            

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

                self.gui.queue_log_message("Ver detalles en consola", 'ERROR')

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

                        with app.app_context():
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

            if self.gui:

                self.gui.queue_log_message("🌐 Iniciando servidor WebSocket...", 'WEB')

            

            socketio.run(

                app,

                host=config.WEB_HOST,

                port=config.WEB_PORT,

                debug=False,

                log_output=False,

                use_reloader=False,

                allow_unsafe_werkzeug=True  # ✅ Para evitar warnings en producción

            )

        except Exception as e:

            error_msg = f"❌ Error en servidor WebSocket: {str(e)}"

            print(error_msg)

            if self.gui:

                self.gui.queue_log_message(error_msg, 'ERROR')

    

    def stop_server(self):

        """Detener servidor"""

        if self.gui:

            self.gui.queue_log_message("🛑 Solicitando detención del servidor...", 'WARNING')

        self.cleanup()

    

    def cleanup(self):

        """Limpiar recursos"""

        if not self.server_running:

            return

        

        if self.gui:

            self.gui.queue_log_message("🛑 Deteniendo servidor...", 'WARNING')

        

        print("\n[Main] 🧹 Limpiando recursos...")

        

        # Detener servidor nativo

        if self.native_server:

            try:

                print("[Main] 🛑 Deteniendo servidor nativo...")

                self.native_server.stop()

                self.native_server = None

            except Exception as e:

                print(f"[Main] ⚠️ Error al detener servidor nativo: {e}")

        

        # Limpiar web handler

        if self.web_handler and hasattr(self.web_handler, 'cleanup'):

            try:

                print("[Main] 🛑 Limpiando web handler...")

                self.web_handler.cleanup()

                self.web_handler = None

            except Exception as e:

                print(f"[Main] ⚠️ Error al limpiar web handler: {e}")

        

        # Detener captura de audio

        if self.audio_capture:

            try:

                print("[Main] 🛑 Deteniendo captura de audio...")

                self.audio_capture.stop_capture()

                self.audio_capture = None

            except Exception as e:

                print(f"[Main] ⚠️ Error al detener captura: {e}")

        

        self.server_running = False

        

        if self.gui:

            self.gui.queue_log_message("✅ Servidor detenido", 'SUCCESS')

        

        print("[Main] ✅ Limpieza completada")

    

    # ========================================================================

    # MÉTODOS PARA SCENE MANAGER

    # ========================================================================

    

    def save_current_scene(self, name, description=""):

        """

        Guardar escena actual

        Llamado desde GUI

        """

        if not self.scene_manager:

            return False, "Sistema de escenas no inicializado"

        

        if not self.server_running:

            return False, "Servidor no está corriendo"

        

        try:

            success, message = self.scene_manager.save_scene(name, description)

            return success, message

        except Exception as e:

            return False, f"Error: {str(e)}"

    

    def load_scene(self, name):

        """

        Cargar escena

        Llamado desde GUI

        """

        if not self.scene_manager:

            return False, "Sistema de escenas no inicializado"

        

        if not self.server_running:

            return False, "Servidor no está corriendo"

        

        try:

            success, message = self.scene_manager.load_scene(name)

            

            # Notificar a GUI para refrescar

            if self.gui and success:

                self.gui.queue_log_message(f"✅ {message}", 'SUCCESS')

                # Refrescar mixer si está abierto

                if hasattr(self.gui, 'refresh_mixer_clients'):

                    self.gui.root.after(100, self.gui.refresh_mixer_clients)

            

            return success, message

        except Exception as e:

            return False, f"Error: {str(e)}"

    

    def get_available_scenes(self):

        """

        Obtener lista de escenas disponibles

        Llamado desde GUI

        """

        if not self.scene_manager:

            return []

        

        try:

            return self.scene_manager.list_scenes()

        except Exception as e:

            print(f"Error obteniendo escenas: {e}")

            return []

    

    def delete_scene(self, name):

        """

        Eliminar escena

        Llamado desde GUI

        """

        if not self.scene_manager:

            return False, "Sistema de escenas no inicializado"

        

        try:

            return self.scene_manager.delete_scene(name)

        except Exception as e:

            return False, f"Error: {str(e)}"

    

    def export_scene(self, name, destination_path):

        """

        Exportar escena

        Llamado desde GUI

        """

        if not self.scene_manager:

            return False, "Sistema de escenas no inicializado"

        

        try:

            return self.scene_manager.export_scene(name, destination_path)

        except Exception as e:

            return False, f"Error: {str(e)}"

    

    def import_scene(self, source_path):

        """

        Importar escena

        Llamado desde GUI

        """

        if not self.scene_manager:

            return False, "Sistema de escenas no inicializado"

        

        try:

            return self.scene_manager.import_scene(source_path)

        except Exception as e:

            return False, f"Error: {str(e)}"

    

    def get_scene_details(self, name):

        """

        Obtener detalles de una escena

        Llamado desde GUI

        """

        if not self.scene_manager:

            return None

        

        try:

            return self.scene_manager.get_scene_details(name)

        except Exception as e:

            print(f"Error obteniendo detalles: {e}")

            return None

    

    def validate_scene_compatibility(self, scene_name):

        """

        Validar si una escena es compatible

        Llamado desde GUI antes de cargar

        """

        if not self.scene_manager:

            return False, "Sistema de escenas no inicializado"

        

        try:

            scene_data = self.scene_manager.get_scene_details(scene_name)

            if not scene_data:

                return False, "Escena no encontrada"

            

            return self.scene_manager.validate_scene_compatibility(scene_data)

        except Exception as e:

            return False, f"Error: {str(e)}"

    

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

        

        # ✅ Mostrar información de PyInstaller

        if getattr(sys, 'frozen', False):

            print(f"  📦 Modo: EJECUTABLE (PyInstaller)")

            print(f"  📁 Base Path: {get_base_path()}")

        else:

            print(f"  🐍 Modo: DESARROLLO (Python)")

        

        print("="*70)

        print("🚀 Iniciando interfaz gráfica...\n")

        

        try:

            # Iniciar GUI

            self.gui = AudioMonitorGUI(self)

            

            # Ejecutar GUI (blocking)

            self.gui.run()

            

        except Exception as e:

            print(f"\n❌ Error crítico en GUI: {e}")

            import traceback

            traceback.print_exc()

            

            # Asegurar limpieza

            self.cleanup()

            

            return 1

        

        # Limpieza final

        self.cleanup()

        return 0



def main():

    """Punto de entrada principal"""

    # ✅ NUEVO: Manejar excepciones no capturadas en modo exe

    try:

        print(f"\n{'='*70}")

        print(f"  FICHATECH MONITOR - Starting...")

        print(f"{'='*70}")

        

        # Verificar entorno

        if getattr(sys, 'frozen', False):

            print(f"✅ Running as executable")

            print(f"📁 Executable path: {sys.executable}")

            print(f"📁 Working directory: {os.getcwd()}")

            print(f"📁 Base path: {get_base_path()}")

        else:

            print(f"✅ Running as Python script")

            print(f"📁 Script path: {__file__}")

        

        print(f"{'='*70}\n")

        

        # Crear y ejecutar app

        app = AudioServerApp()

        exit_code = app.run()

        

        print(f"\n{'='*70}")

        print(f"  Application exited with code: {exit_code}")

        print(f"{'='*70}\n")

        

        sys.exit(exit_code or 0)

        

    except KeyboardInterrupt:

        print("\n\n[Main] ⚠️ Interrupted by user (Ctrl+C)")

        sys.exit(0)

        

    except Exception as e:

        error_msg = f"\n❌ FATAL ERROR: {str(e)}\n"

        print(error_msg)

        

        import traceback

        traceback.print_exc()

        

        # En modo exe sin consola, guardar error en archivo

        if getattr(sys, 'frozen', False):

            try:

                error_file = os.path.join(

                    os.path.dirname(sys.executable), 

                    f'error_log_{int(time.time())}.txt'

                )

                

                with open(error_file, 'w', encoding='utf-8') as f:

                    f.write("="*70 + "\n")

                    f.write("FICHATECH MONITOR - ERROR LOG\n")

                    f.write("="*70 + "\n\n")

                    f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

                    f.write(f"Executable: {sys.executable}\n")

                    f.write(f"Working Dir: {os.getcwd()}\n")

                    f.write(f"Base Path: {get_base_path()}\n\n")

                    f.write("="*70 + "\n")

                    f.write("ERROR DETAILS\n")

                    f.write("="*70 + "\n\n")

                    f.write(f"Error: {str(e)}\n\n")

                    f.write("Traceback:\n")

                    f.write(traceback.format_exc())

                

                print(f"\n💾 Error log saved to: {error_file}")

                

                # Mostrar mensaje al usuario

                try:

                    import tkinter as tk

                    from tkinter import messagebox

                    

                    root = tk.Tk()

                    root.withdraw()

                    

                    messagebox.showerror(

                        "Fichatech Monitor - Error",

                        f"Error fatal:\n\n{str(e)}\n\n"

                        f"Log guardado en:\n{error_file}"

                    )

                    

                except:

                    pass

                

            except Exception as log_error:

                print(f"⚠️ No se pudo guardar log de error: {log_error}")

        

        sys.exit(1)



if __name__ == '__main__':

    main()