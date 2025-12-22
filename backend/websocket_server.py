"""

WebSocket Server - Servidor Flask + SocketIO

CORREGIDO: Timestamp en milisegundos, mejor manejo de errores

"""



from flask import Flask, send_from_directory, request

from flask_socketio import SocketIO, emit

import threading

import time

import config



# === VARIABLES GLOBALES ===

audio_capture = None

channel_manager = None



def init_server(capture, manager):

    """

    Inicializar referencias globales

    DEBE llamarse ANTES de crear WebSocketServer

    """

    global audio_capture, channel_manager

    audio_capture = capture

    channel_manager = manager



# === CONFIGURACIÃ“N FLASK ===

app = Flask(__name__, 

            static_folder='../frontend',

            template_folder='../frontend')



app.config['SECRET_KEY'] = 'audio-monitor-ultra-low-latency-2024'



# ConfiguraciÃ³n SocketIO optimizada

socketio = SocketIO(

    app, 

    cors_allowed_origins="*",

    async_mode='threading',

    ping_interval=config.PING_INTERVAL,

    ping_timeout=config.PING_TIMEOUT,

    max_http_buffer_size=1e8,

    logger=False,

    engineio_logger=False

)



# === CLASE SERVIDOR ===

class WebSocketServer:

    def __init__(self, audio_capture_instance, channel_manager_instance):

        self.audio_capture = audio_capture_instance

        self.channel_manager = channel_manager_instance

        self.running = False

        self.audio_thread = None

        self.metrics = {

            'packets_sent': 0,

            'bytes_sent': 0,

            'start_time': time.time(),

            'last_metric_time': time.time()

        }

        

    def start(self):

        """Inicia el servidor y el thread de audio"""

        self.running = True

        

        # Thread que lee audio y lo envÃ­a a clientes

        self.audio_thread = threading.Thread(

            target=self._audio_sender, 

            daemon=True,

            name="AudioSender"

        )

        self.audio_thread.start()

        

        if config.VERBOSE:

            print(f"[*] Thread de audio iniciado")

        

        # Iniciar servidor Flask (bloqueante)

        socketio.run(

            app, 

            host=config.HOST, 

            port=config.PORT, 

            debug=False,

            use_reloader=False,

            log_output=False

        )

    

    def _audio_sender(self):

        """

        Thread que continuamente lee audio y envÃ­a a clientes

        OPTIMIZADO: Mejor manejo de timeouts y mÃ©tricas

        """

        if config.VERBOSE:

            print("[*] Audio sender thread activo")

        

        consecutive_errors = 0

        max_consecutive_errors = 10

        

        while self.running:

            try:

                # Obtener datos con timeout corto

                audio_data = self.audio_capture.get_audio_data(timeout=0.5)

                

                if audio_data is None:

                    # Timeout normal - continuar

                    continue

                

                # Reset error counter en Ã©xito

                consecutive_errors = 0

                

                # Procesar audio por cliente

                processed = self.channel_manager.process_audio(audio_data)

                

                # Enviar a cada cliente

                for client_id, audio_packets in processed.items():

                    for packet in audio_packets:

                        try:

                            socketio.emit('audio', packet, room=client_id, namespace='/')

                            self.metrics['packets_sent'] += 1

                            self.metrics['bytes_sent'] += len(packet)

                        except Exception as e:

                            if config.VERBOSE:

                                print(f"[!] Error enviando a {client_id[:8]}: {e}")

                

                # Mostrar mÃ©tricas cada 5 segundos

                if config.SHOW_METRICS:

                    current_time = time.time()

                    if current_time - self.metrics['last_metric_time'] >= 5.0:

                        elapsed = current_time - self.metrics['start_time']

                        if elapsed > 0:

                            mbps = (self.metrics['bytes_sent'] * 8 / elapsed) / 1_000_000

                            clients = self.channel_manager.get_client_count()

                            channels = self.channel_manager.get_total_channel_count()

                            print(f"[ðŸ“Š] {mbps:.2f} Mbps | Clientes: {clients} | Canales: {channels}")

                        self.metrics['last_metric_time'] = current_time

                        

            except Exception as e:

                consecutive_errors += 1

                if config.VERBOSE:

                    print(f"[!] Error en audio sender: {e}")

                

                if consecutive_errors >= max_consecutive_errors:

                    print(f"[!] Demasiados errores consecutivos ({consecutive_errors}), deteniendo...")

                    self.running = False

                    break

                

                time.sleep(0.1)

        

        if config.VERBOSE:

            print("[*] Audio sender thread detenido")

    

    def stop(self):

        """Detiene el servidor limpiamente"""

        if config.VERBOSE:

            print("[*] Deteniendo servidor...")

        

        self.running = False

        

        if self.audio_thread and self.audio_thread.is_alive():

            self.audio_thread.join(timeout=2)



# === RUTAS FLASK ===

@app.route('/')

def index():

    """Sirve la interfaz web"""

    return send_from_directory(app.static_folder, 'index.html')



@app.route('/<path:path>')

def static_files(path):

    """Sirve archivos estÃ¡ticos (CSS, JS)"""

    return send_from_directory(app.static_folder, path)



# === EVENTOS SOCKETIO ===

@socketio.on('connect')

def handle_connect():

    """Cliente se conecta"""

    client_id = request.sid

    

    # Verificar lÃ­mite de clientes

    if channel_manager.get_client_count() >= config.MAX_CLIENTS:

        if config.VERBOSE:

            print(f"[!] Cliente rechazado (lÃ­mite {config.MAX_CLIENTS} alcanzado)")

        return False

    

    # Enviar info del dispositivo de audio

    device_info = {

        'name': audio_capture.device_info['name'],

        'channels': channel_manager.num_channels,

        'sample_rate': config.SAMPLE_RATE,

        'blocksize': config.BLOCKSIZE,

        'jitter_buffer_ms': config.JITTER_BUFFER_MS

    }

    emit('device_info', device_info)

    

    if config.VERBOSE:

        print(f"[+] Cliente conectado: {client_id[:8]}...")



@socketio.on('disconnect')

def handle_disconnect():

    """Cliente se desconecta"""

    client_id = request.sid

    channel_manager.unsubscribe_client(client_id)

    

    if config.VERBOSE:

        print(f"[-] Cliente desconectado: {client_id[:8]}...")



@socketio.on('subscribe')

def handle_subscribe(data):

    """Cliente se suscribe a canales especÃ­ficos"""

    client_id = request.sid

    channels = data.get('channels', [])

    gains = data.get('gains', {})

    

    # Convertir gains keys a int (vienen como string desde JSON)

    gains = {int(k): float(v) for k, v in gains.items()}

    

    channel_manager.subscribe_client(client_id, channels, gains)

    

    # Enviar confirmaciÃ³n

    emit('subscribed', {'channels': channels})



@socketio.on('update_gain')

def handle_update_gain(data):

    """Cliente actualiza ganancia de un canal"""

    client_id = request.sid

    channel = int(data.get('channel'))

    gain = float(data.get('gain'))

    

    # Limitar ganancia a rango seguro

    gain = max(0.0, min(gain, 4.0))  # 0 a +12dB

    

    channel_manager.update_gain(client_id, channel, gain)



@socketio.on('ping')

def handle_ping(data):

    """

    Responder a ping del cliente (medir latencia de red)

    CORREGIDO: Timestamp en milisegundos

    """

    # Retornar timestamp del cliente + timestamp del servidor

    emit('pong', {

        'client_timestamp': data.get('timestamp', 0),

        'server_timestamp': int(time.time() * 1000)

    })



@socketio.on('get_stats')

def handle_get_stats():

    """Enviar estadÃ­sticas del servidor"""

    stats = {

        'clients': channel_manager.get_client_count(),

        'active_channels': len(channel_manager.get_active_channels()),

        'total_subscriptions': channel_manager.get_total_channel_count()

    }

    emit('stats', stats)