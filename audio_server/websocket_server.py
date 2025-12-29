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

# ✅ Configuración optimizada para baja latencia
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    
    # ✅ Optimizaciones de latencia
    ping_timeout=10,                    # Timeout más corto
    ping_interval=5,                    # Ping cada 5s
    compression=False,                  # ✅ Sin compresión (ahorra ~2-5ms)
    
    # ✅ Buffers optimizados
    max_http_buffer_size=1000000,       # 1MB máximo
    
    # ✅ Sin logs innecesarios
    engineio_logger=False,
    logger=False,
    
    # ✅ Configuración WebSocket
    always_connect=True,
    websocket_compression=False,        # ✅ Sin compresión WS
    
    # ✅ Modo binario puro
    binary=True
)

channel_manager = None

def init_server(manager):
    """
    ✅ Inicializar servidor WebSocket optimizado
    """
    global channel_manager
    channel_manager = manager
    print(f"[WebSocket] ✅ Inicializado (modo DIRECTO + ASYNC)")
    print(f"[WebSocket] ⚡ Compresión: OFF")
    print(f"[WebSocket] 🎯 Latencia objetivo: <15ms")

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
            'name': 'Audio Interface RF OPTIMIZED',
            'channels': channel_manager.num_channels,
            'sample_rate': config.SAMPLE_RATE,
            'blocksize': config.BLOCKSIZE,
            'latency_ms': config.BLOCKSIZE / config.SAMPLE_RATE * 1000,
            'supports_webrtc': False,
            'jitter_buffer_ms': 5,
            'mode': 'direct_async',
            'compression': False,
            'binary': True
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
                if config.DEBUG:
                    print(f"[WebSocket] Error update_gain: {e}")

@socketio.on('ping')
def handle_ping(data):
    """Medir latencia de red"""
    emit('pong', {
        'client_timestamp': data.get('timestamp', 0),
        'server_timestamp': int(time.time() * 1000)
    })

# Manejo de errores
@app.errorhandler(404)
def not_found(e):
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    print("[WebSocket] 🚀 Servidor WebSocket iniciando...")
    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False)