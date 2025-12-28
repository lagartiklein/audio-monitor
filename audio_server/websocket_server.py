from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
import time
import os
import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

app = Flask(__name__, 
            static_folder=FRONTEND_DIR,
            template_folder=FRONTEND_DIR)

app.config['SECRET_KEY'] = 'audio-monitor-key'

# Configuración optimizada
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    engineio_logger=False,
    logger=False
)

channel_manager = None

def init_server(manager):
    """
    Inicializar servidor WebSocket SIN colas
    El audio se enviará directamente desde callbacks en main.py
    """
    global channel_manager
    channel_manager = manager
    print(f"[WebSocket] ✅ Inicializado (modo DIRECTO - sin colas)")

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    if channel_manager:
        device_info = {
            'name': 'Audio Interface RF DIRECT',
            'channels': channel_manager.num_channels,
            'sample_rate': 48000,
            'blocksize': 128,
            'supports_webrtc': False,
            'jitter_buffer_ms': 5,
            'mode': 'direct'
        }
        emit('device_info', device_info)
    print(f"[WebSocket] ✅ Conectado: {client_id[:8]}")

@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    if channel_manager and hasattr(channel_manager, 'subscriptions'):
        if client_id in channel_manager.subscriptions:
            channel_manager.unsubscribe_client(client_id)
    print(f"[WebSocket] ❌ Desconectado: {client_id[:8]}")

@socketio.on('subscribe')
def handle_subscribe(data):
    client_id = request.sid
    channels = data.get('channels', [])
    gains = data.get('gains', {})
    
    # Convertir gains a int keys
    gains_int = {}
    for k, v in gains.items():
        try:
            gains_int[int(k)] = float(v)
        except:
            pass
    
    if channel_manager:
        channel_manager.subscribe_client(client_id, channels, gains_int)
        emit('subscribed', {'channels': channels})
        print(f"[WebSocket] 📡 {client_id[:8]} suscrito: {len(channels)} canales")

@socketio.on('update_gain')
def handle_update_gain(data):
    client_id = request.sid
    channel = data.get('channel')
    gain = data.get('gain')
    
    if channel_manager and hasattr(channel_manager, 'subscriptions'):
        if client_id in channel_manager.subscriptions:
            try:
                channel_manager.subscriptions[client_id]['gains'][int(channel)] = float(gain)
            except Exception as e:
                print(f"[WebSocket] Error update_gain: {e}")

@socketio.on('ping')
def handle_ping(data):
    emit('pong', {
        'client_timestamp': data.get('timestamp', 0),
        'server_timestamp': int(time.time() * 1000)
    })

# Manejo de errores
@app.errorhandler(404)
def not_found(e):
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    print("[WebSocket] 🚀 Servidor WebSocket iniciando en modo desarrollo...")
    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=True)