from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
import threading
import time
import struct
import numpy as np
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

audio_capture = None
channel_manager = None
audio_thread = None
running = False
audio_broadcast_queue = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

app = Flask(__name__, 
            static_folder=FRONTEND_DIR,
            template_folder=FRONTEND_DIR)

app.config['SECRET_KEY'] = 'audio-monitor-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

def init_server(capture, manager, broadcast_queue=None):
    global audio_capture, channel_manager, audio_broadcast_queue
    audio_capture = capture
    channel_manager = manager
    audio_broadcast_queue = broadcast_queue
    start_audio_thread()
    print("[*] WebSocket server inicializado")

def start_audio_thread():
    global audio_thread, running
    if audio_thread and audio_thread.is_alive():
        return
    running = True
    audio_thread = threading.Thread(target=audio_sender_loop, daemon=True)
    audio_thread.start()

def stop_audio_thread():
    global running
    running = False
    if audio_thread:
        audio_thread.join(timeout=2)

def create_audio_packet_websocket(audio_data, channel, gain=1.0):
    """Crea paquete WebSocket para audio de un solo canal."""
    # Extraer solo este canal
    channel_data = audio_data[:, channel:channel+1]
    
    # Aplicar ganancia
    channel_data = channel_data * gain
    
    # Convertir a bytes
    audio_bytes = channel_data.astype(np.float32).tobytes()
    
    # Crear paquete: [channel (4 bytes)][audio_data]
    packet = struct.pack(f'<I{len(audio_bytes)}s', channel, audio_bytes)
    return packet

def audio_sender_loop():
    print("[*] Audio sender WebSocket iniciado")
    while running:
        try:
            if audio_broadcast_queue:
                try:
                    audio_data = audio_broadcast_queue.get(timeout=0.1)
                except:
                    continue
            else:
                audio_data = audio_capture.get_audio_data(timeout=0.05)
            
            if audio_data is None:
                continue
            
            # Enviar audio a cada cliente
            for client_id, subscription in channel_manager.subscriptions.copy().items():
                try:
                    channels = subscription['channels']
                    gains = subscription['gains']
                    
                    if not channels:
                        continue
                    
                    # Enviar cada canal por separado
                    for channel in channels:
                        gain = gains.get(channel, 1.0)
                        packet = create_audio_packet_websocket(
                            audio_data, 
                            channel, 
                            gain
                        )
                        
                        try:
                            socketio.emit('audio', packet, room=client_id)
                        except:
                            # Si falla, eliminar cliente
                            channel_manager.unsubscribe_client(client_id)
                            break
                            
                except Exception as e:
                    logger.error(f"Error procesando cliente {client_id[:8]}: {e}")
                    channel_manager.unsubscribe_client(client_id)
        
        except Exception as e:
            logger.error(f"Error en audio sender: {e}")
            time.sleep(0.1)
    
    print("[*] Audio sender WebSocket detenido")

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    if audio_capture and hasattr(audio_capture, 'device_info'):
        device_info = {
            'name': audio_capture.device_info['name'],
            'channels': channel_manager.num_channels,
            'sample_rate': config.SAMPLE_RATE,
            'blocksize': config.BLOCKSIZE,
            'supports_webrtc': False
        }
        emit('device_info', device_info)
    print(f"[+] WebSocket conectado: {client_id[:8]}")

@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    channel_manager.unsubscribe_client(client_id)
    print(f"[-] WebSocket desconectado: {client_id[:8]}")

@socketio.on('subscribe')
def handle_subscribe(data):
    client_id = request.sid
    channels = data.get('channels', [])
    gains = data.get('gains', {})
    gains_int = {}
    for k, v in gains.items():
        try:
            gains_int[int(k)] = float(v)
        except:
            pass
    channel_manager.subscribe_client(client_id, channels, gains_int)
    emit('subscribed', {'channels': channels})
    print(f"[+] WebSocket {client_id[:8]} suscrito a {len(channels)} canales")

@socketio.on('update_gain')
def handle_update_gain(data):
    client_id = request.sid
    channel = int(data.get('channel'))
    gain = float(data.get('gain'))
    if client_id in channel_manager.subscriptions:
        channel_manager.subscriptions[client_id]['gains'][channel] = gain

@socketio.on('ping')
def handle_ping(data):
    emit('pong', {
        'client_timestamp': data.get('timestamp', 0),
        'server_timestamp': int(time.time() * 1000)
    })