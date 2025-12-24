"""
WebSocket Server - Servidor Flask + SocketIO completo
"""

from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
import threading
import time
import json
import struct
import numpy as np
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

# === VARIABLES GLOBALES ===
audio_capture = None
channel_manager = None
audio_thread = None
running = False

def init_server(capture, manager):
    """Inicializar referencias globales"""
    global audio_capture, channel_manager
    audio_capture = capture
    channel_manager = manager
    
    # Iniciar thread de envío de audio
    start_audio_thread()
    
    print("[*] WebSocket server inicializado")

def start_audio_thread():
    """Inicia el thread que envía audio a los clientes"""
    global audio_thread, running
    
    if audio_thread and audio_thread.is_alive():
        return
    
    running = True
    audio_thread = threading.Thread(
        target=audio_sender_loop,
        daemon=True,
        name="AudioSender"
    )
    audio_thread.start()
    print("[*] Thread de audio iniciado")

def stop_audio_thread():
    """Detiene el thread de audio"""
    global running
    running = False
    if audio_thread:
        audio_thread.join(timeout=2)
    print("[*] Thread de audio detenido")

def audio_sender_loop():
    """Loop principal que envía audio a clientes conectados"""
    print("[*] Audio sender iniciado")
    
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while running:
        try:
            # Obtener datos de audio
            audio_data = audio_capture.get_audio_data(timeout=0.1)
            
            if audio_data is None:
                continue
            
            # Reset error counter en éxito
            consecutive_errors = 0
            
            # Enviar a cada cliente
            for client_id in list(channel_manager.subscriptions.keys()):
                try:
                    # Procesar audio para este cliente
                    audio_packets = channel_manager.get_audio_for_client(client_id, audio_data)
                    
                    # Enviar cada paquete
                    for packet in audio_packets:
                        socketio.emit('audio', packet, room=client_id)
                        
                except Exception as e:
                    if config.VERBOSE:
                        print(f"[!] Error enviando a {client_id[:8]}: {e}")
    
        except Exception as e:
            consecutive_errors += 1
            if config.VERBOSE:
                print(f"[!] Error en audio sender: {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                print(f"[!] Demasiados errores consecutivos ({consecutive_errors})")
                break
            
            time.sleep(0.1)
    
    print("[*] Audio sender detenido")

# === CONFIGURACIÓN FLASK ===
app = Flask(__name__, 
            static_folder='../frontend',
            template_folder='../frontend')

app.config['SECRET_KEY'] = 'audio-monitor-ultra-low-latency-2024'

# Configuración SocketIO optimizada
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

# === RUTAS FLASK ===
@app.route('/')
def index():
    """Sirve la interfaz web"""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    """Sirve archivos estáticos (CSS, JS)"""
    return send_from_directory(app.static_folder, path)

# === EVENTOS SOCKETIO ===
@socketio.on('connect')
def handle_connect():
    """Cliente se conecta"""
    client_id = request.sid
    
    # Verificar límite de clientes
    if channel_manager.get_client_count() >= config.MAX_CLIENTS:
        if config.VERBOSE:
            print(f"[!] Cliente rechazado (límite {config.MAX_CLIENTS} alcanzado)")
        return False
    
    # Enviar info del dispositivo de audio
    device_info = {
        'name': audio_capture.device_info['name'],
        'channels': channel_manager.num_channels,
        'sample_rate': config.SAMPLE_RATE,
        'blocksize': config.BLOCKSIZE,
        'jitter_buffer_ms': config.WEB_JITTER_BUFFER
    }
    emit('device_info', device_info)
    
    if config.VERBOSE:
        print(f"[+] Cliente conectado: {client_id[:8]}...")
    
    return True

@socketio.on('disconnect')
def handle_disconnect():
    """Cliente se desconecta"""
    client_id = request.sid
    channel_manager.unsubscribe_client(client_id)
    
    if config.VERBOSE:
        print(f"[-] Cliente desconectado: {client_id[:8]}...")

@socketio.on('subscribe')
def handle_subscribe(data):
    """Cliente se suscribe a canales específicos"""
    client_id = request.sid
    channels = data.get('channels', [])
    gains = data.get('gains', {})
    
    # Convertir gains keys a int (vienen como string desde JSON)
    gains = {int(k): float(v) for k, v in gains.items()}
    
    channel_manager.subscribe_client(client_id, channels, gains)
    
    # Enviar confirmación
    emit('subscribed', {'channels': channels})
    
    if config.VERBOSE:
        print(f"[+] {client_id[:8]} suscrito a {len(channels)} canales")

@socketio.on('update_gain')
def handle_update_gain(data):
    """Cliente actualiza ganancia de un canal"""
    client_id = request.sid
    channel = int(data.get('channel'))
    gain = float(data.get('gain'))
    
    channel_manager.update_gain(client_id, channel, gain)

@socketio.on('ping')
def handle_ping(data):
    """Responder a ping del cliente (medir latencia de red)"""
    emit('pong', {
        'client_timestamp': data.get('timestamp', 0),
        'server_timestamp': int(time.time() * 1000)
    })

# Manejar shutdown
import atexit
@atexit.register
def cleanup():
    stop_audio_thread()