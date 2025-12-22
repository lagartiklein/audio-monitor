from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import threading
import config

app = Flask(__name__, 
            static_folder='frontend',
            template_folder='frontend')
app.config['SECRET_KEY'] = 'audio-monitor-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class WebSocketServer:
    def __init__(self, audio_capture, channel_manager):
        self.audio_capture = audio_capture
        self.channel_manager = channel_manager
        self.running = False
        self.audio_thread = None
        
    def start(self):
        """Inicia el servidor y el thread de audio"""
        self.running = True
        
        # Thread que lee audio y lo envía
        self.audio_thread = threading.Thread(target=self._audio_sender, daemon=True)
        self.audio_thread.start()
        
        if config.VERBOSE:
            print(f"[*] Servidor WebSocket iniciado en http://{config.HOST}:{config.PORT}")
        
        # Iniciar servidor Flask (bloqueante)
        socketio.run(app, host=config.HOST, port=config.PORT, debug=False, use_reloader=False)
    
    def _audio_sender(self):
        """Thread que continuamente lee audio y envía a clientes"""
        while self.running:
            try:
                # Obtener datos de audio (bloquea hasta que haya datos)
                audio_data = self.audio_capture.get_audio_data()
                
                # Procesar audio por cliente
                processed = self.channel_manager.process_audio(audio_data)
                
                # Enviar a cada cliente
                for client_id, audio_packets in processed.items():
                    for packet in audio_packets:
                        socketio.emit('audio', packet, room=client_id, namespace='/')
                        
            except Exception as e:
                if config.VERBOSE:
                    print(f"[!] Error en audio sender: {e}")
    
    def stop(self):
        """Detiene el servidor"""
        self.running = False
        if self.audio_thread:
            self.audio_thread.join(timeout=2)

# === Rutas Flask ===
@app.route('/')
def index():
    return render_template('index.html')

# === Eventos SocketIO ===
@socketio.on('connect')
def handle_connect():
    client_id = request.sid  # Session ID único
    
    # Enviar info de dispositivo
    device_info = {
        'name': audio_capture.device_info['name'],
        'channels': channel_manager.num_channels,
        'sample_rate': config.SAMPLE_RATE,
        'blocksize': config.BLOCKSIZE
    }
    emit('device_info', device_info)
    
    if config.VERBOSE:
        print(f"[+] Cliente conectado: {client_id}")

@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    channel_manager.unsubscribe_client(client_id)
    
    if config.VERBOSE:
        print(f"[-] Cliente desconectado: {client_id}")

@socketio.on('subscribe')
def handle_subscribe(data):
    """Cliente se suscribe a canales"""
    client_id = request.sid
    channels = data.get('channels', [])
    gains = data.get('gains', {})
    
    # Convertir gains keys a int (vienen como string desde JSON)
    gains = {int(k): v for k, v in gains.items()}
    
    channel_manager.subscribe_client(client_id, channels, gains)

@socketio.on('update_gain')
def handle_update_gain(data):
    """Cliente actualiza ganancia de un canal"""
    client_id = request.sid
    channel = data.get('channel')
    gain = data.get('gain')
    
    channel_manager.update_gain(client_id, channel, gain)

# Variables globales para acceso desde routes
audio_capture = None
channel_manager = None

def init_server(capture, manager):
    """Inicializar referencias globales"""
    global audio_capture, channel_manager
    audio_capture = capture
    channel_manager = manager