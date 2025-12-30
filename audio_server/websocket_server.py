from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit
import time
import os
import sys
import config
import logging

# ✅ NUEVO: Función para rutas en PyInstaller
def get_base_path():
    """Obtener ruta base que funciona en desarrollo y exe"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_path()
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

# ✅ Verificar que frontend existe
if not os.path.exists(FRONTEND_DIR):
    print(f"⚠️ WARNING: Frontend directory not found at {FRONTEND_DIR}")
    # Intentar buscar en directorio actual
    alt_frontend = os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), 'frontend')
    if os.path.exists(alt_frontend):
        FRONTEND_DIR = alt_frontend
        print(f"✅ Found frontend at: {FRONTEND_DIR}")
    else:
        print(f"❌ Frontend not found. Web UI may not work.")

app = Flask(__name__, 
            static_folder=FRONTEND_DIR,
            template_folder=FRONTEND_DIR)

app.config['SECRET_KEY'] = 'audio-monitor-key'

socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    ping_timeout=30,
    ping_interval=10,
    compression=False,
    max_http_buffer_size=2000000,
    engineio_logger=False,
    logger=False,
    always_connect=True,
    websocket_compression=False,
    binary=True
)

channel_manager = None
logger = logging.getLogger(__name__)

# 🎚️ VU METERS: Sistema de broadcast
vu_last_broadcast = 0
vu_broadcast_interval = 100  # ms - sincronizado con audio_capture

def init_server(manager):
    """✅ CORREGIDO: Inicializar servidor WebSocket y registrar socketio"""
    global channel_manager
    channel_manager = manager
    # ✅ Inyectar socketio en channel_manager
    channel_manager.set_socketio(socketio)
    print(f"[WebSocket] ✅ Inicializado (Control Central + VU Meters)")
    print(f"[WebSocket] 📁 Frontend Dir: {FRONTEND_DIR}")

def broadcast_vu_levels(levels):
    """
    🎚️ Broadcast de niveles VU a todos los clientes web
    
    Args:
        levels: dict {channel: {'rms_percent': float, 'peak_percent': float, ...}}
    """
    global vu_last_broadcast
    
    current_time = time.time() * 1000
    
    # Throttling para no saturar websocket
    if current_time - vu_last_broadcast < vu_broadcast_interval:
        return
    
    vu_last_broadcast = current_time
    
    try:
        # Preparar datos simplificados para envío
        simplified_levels = {}
        for ch, data in levels.items():
            simplified_levels[ch] = {
                'rms': round(data['rms_percent'], 1),  # 0-100
                'peak': round(data['peak_percent'], 1),  # 0-100
                'db': round(data['rms_db'], 1)  # dB real
            }
        
        # Broadcast a todos los clientes conectados
        socketio.emit('vu_levels', {
            'levels': simplified_levels,
            'timestamp': int(current_time)
        })
        
    except Exception as e:
        if config.DEBUG:
            logger.error(f"Error broadcasting VU levels: {e}")

@app.route('/')
def index():
    if os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return send_from_directory(app.static_folder, 'index.html')
    else:
        return f"""
        <html>
        <head><title>Fichatech Monitor - Error</title></head>
        <body style="font-family: monospace; padding: 20px; background: #0a0a0a; color: #00ff00;">
            <h1>❌ Frontend Not Found</h1>
            <p>Frontend directory: <code>{app.static_folder}</code></p>
            <p>Expected: <code>{os.path.join(app.static_folder, 'index.html')}</code></p>
            <hr>
            <p>Base DIR: <code>{BASE_DIR}</code></p>
            <p>Frozen: <code>{getattr(sys, 'frozen', False)}</code></p>
        </body>
        </html>
        """, 404

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    if channel_manager:
        device_info = {
            'name': 'Audio Interface RF',
            'channels': channel_manager.num_channels,
            'sample_rate': config.SAMPLE_RATE,
            'blocksize': config.BLOCKSIZE,
            'latency_ms': config.BLOCKSIZE / config.SAMPLE_RATE * 1000,
            'mode': 'control_center',
            'vu_enabled': True  # 🎚️ Indicar que VU está disponible
        }
        emit('device_info', device_info)
        
        # Enviar lista de clientes conectados
        clients_info = channel_manager.get_all_clients_info()
        emit('clients_update', {'clients': clients_info})
    
    print(f"[WebSocket] ✅ Conectado: {client_id[:8]}")

@socketio.on('disconnect')
def handle_disconnect():
    """✅ CORREGIDO: Sin argumentos (Flask-SocketIO no pasa reason aquí)"""
    client_id = request.sid

    if channel_manager:
        channel_manager.unsubscribe_client(client_id)
        
        # Notificar a otros clientes web
        broadcast_clients_update()
        
        # Emitir evento específico de desconexión
        socketio.emit('client_disconnected', {
            'client_id': client_id,
            'timestamp': int(time.time() * 1000),
            'client_type': 'web'
        }, include_self=False)

    print(f"[WebSocket] ❌ Desconectado: {client_id[:8]}")

@socketio.on('subscribe')
def handle_subscribe(data):
    """Suscribir cliente web (control panel - no recibe audio)"""
    client_id = request.sid
    channels = data.get('channels', [])
    gains = data.get('gains', {})
    
    gains_int = {}
    for k, v in gains.items():
        try:
            gains_int[int(k)] = float(v)
        except:
            pass
    
    if channel_manager:
        channel_manager.subscribe_client(client_id, channels, gains_int, client_type="web")
        emit('subscribed', {'channels': channels})
        print(f"[WebSocket] 📡 {client_id[:8]} suscrito: {len(channels)} canales")

@socketio.on('update_client_mix')
def handle_update_client_mix(data):
    """✅ OPTIMIZADO: Actualizar mezcla de un cliente con validaciones"""
    
    # Extraer command_id si existe (para ACK)
    command_id = data.pop('_commandId', None)
    
    # Validaciones
    if not channel_manager:
        emit('command_failed', {
            'command': 'update_client_mix',
            'reason': 'Channel manager no disponible',
            '_commandId': command_id
        })
        return
    
    target_client_id = data.get('target_client_id')
    if not target_client_id:
        emit('command_failed', {
            'command': 'update_client_mix',
            'reason': 'target_client_id requerido',
            '_commandId': command_id
        })
        return
    
    # Verificar que el cliente existe
    if target_client_id not in channel_manager.subscriptions:
        emit('command_failed', {
            'command': 'update_client_mix',
            'reason': f'Cliente {target_client_id[:8]} no encontrado',
            'client_id': target_client_id,
            '_commandId': command_id
        })
        return
    
    try:
        # ✅ Convertir gains dict keys a int si es necesario
        gains = data.get('gains')
        if gains:
            gains_converted = {}
            for k, v in gains.items():
                try:
                    channel_int = int(k)
                    gain_float = float(v)
                    # Validar rango
                    if 0.0 <= gain_float <= 10.0:
                        gains_converted[channel_int] = gain_float
                    else:
                        logger.warning(f"Gain fuera de rango: {gain_float}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error convirtiendo gain: {k}={v}, {e}")
            data['gains'] = gains_converted if gains_converted else None
        
        # ✅ Convertir pans dict keys a int
        pans = data.get('pans')
        if pans:
            pans_converted = {}
            for k, v in pans.items():
                try:
                    channel_int = int(k)
                    pan_float = float(v)
                    # Validar rango
                    if -1.0 <= pan_float <= 1.0:
                        pans_converted[channel_int] = pan_float
                    else:
                        logger.warning(f"Pan fuera de rango: {pan_float}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error convirtiendo pan: {k}={v}, {e}")
            data['pans'] = pans_converted if pans_converted else None
        
        # ✅ Convertir mutes dict keys a int
        mutes = data.get('mutes')
        if mutes:
            mutes_converted = {}
            for k, v in mutes.items():
                try:
                    mutes_converted[int(k)] = bool(v)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error convirtiendo mute: {k}={v}, {e}")
            data['mutes'] = mutes_converted if mutes_converted else None
        
        # ✅ Validar solos (debe ser lista de ints)
        solos = data.get('solos')
        if solos is not None:
            try:
                if isinstance(solos, list):
                    data['solos'] = [int(ch) for ch in solos if isinstance(ch, (int, str))]
                else:
                    data['solos'] = None
            except (ValueError, TypeError) as e:
                logger.warning(f"Error convirtiendo solos: {solos}, {e}")
                data['solos'] = None
        
        # ✅ Validar channels (debe ser lista de ints)
        channels = data.get('channels')
        if channels is not None:
            try:
                if isinstance(channels, list):
                    data['channels'] = [int(ch) for ch in channels if isinstance(ch, (int, str))]
                else:
                    data['channels'] = None
            except (ValueError, TypeError) as e:
                logger.warning(f"Error convirtiendo channels: {channels}, {e}")
                data['channels'] = None
        
        # ✅ Validar pre_listen
        pre_listen = data.get('pre_listen')
        if pre_listen is not None:
            try:
                if isinstance(pre_listen, (int, str)):
                    data['pre_listen'] = int(pre_listen) if pre_listen != 'null' else None
            except (ValueError, TypeError):
                data['pre_listen'] = None
        
        # ✅ Validar master_gain
        master_gain = data.get('master_gain')
        if master_gain is not None:
            try:
                gain_float = float(master_gain)
                if 0.0 <= gain_float <= 5.0:
                    data['master_gain'] = gain_float
                else:
                    data['master_gain'] = None
            except (ValueError, TypeError):
                data['master_gain'] = None
        
        # Intentar actualizar
        success = channel_manager.update_client_mix(
            target_client_id,
            channels=data.get('channels'),
            gains=data.get('gains'),
            pans=data.get('pans'),
            mutes=data.get('mutes'),
            solos=data.get('solos'),
            pre_listen=data.get('pre_listen'),
            master_gain=data.get('master_gain')
        )
        
        if success:
            # ✅ Confirmar éxito
            emit('command_ack', {
                'command': 'update_client_mix',
                'client_id': target_client_id,
                'timestamp': int(time.time() * 1000),
                '_commandId': command_id
            })
            
            # ✅ Obtener estado actualizado completo
            updated_client = channel_manager.get_client_subscription(target_client_id)
            if updated_client:
                # Broadcast estado actualizado a TODOS los web clients
                client_info = {
                    'id': target_client_id,
                    'type': channel_manager.client_types.get(target_client_id, 'unknown'),
                    'channels': updated_client.get('channels', []),
                    'active_channels': len(updated_client.get('channels', [])),
                    'gains': updated_client.get('gains', {}),
                    'pans': updated_client.get('pans', {}),
                    'mutes': updated_client.get('mutes', {}),
                    'solos': list(updated_client.get('solos', set())),
                    'has_solo': len(updated_client.get('solos', set())) > 0,
                    'pre_listen': updated_client.get('pre_listen'),
                    'master_gain': updated_client.get('master_gain', 1.0),
                    'last_update': updated_client.get('last_update', 0)
                }
                
                socketio.emit('client_mix_updated', {
                    'client': client_info,
                    'timestamp': int(time.time() * 1000)
                })
            
            if config.DEBUG:
                print(f"[WebSocket] ✅ Mix actualizado: {target_client_id[:8]}")
        else:
            # ❌ Cliente no encontrado o error
            emit('command_failed', {
                'command': 'update_client_mix',
                'reason': f'No se pudo actualizar cliente {target_client_id[:8]}',
                'client_id': target_client_id,
                '_commandId': command_id
            })
    
    except Exception as e:
        # ❌ Error inesperado
        logger.error(f"Error en update_client_mix: {e}", exc_info=True)
        emit('command_failed', {
            'command': 'update_client_mix',
            'reason': str(e),
            'client_id': target_client_id,
            '_commandId': command_id
        })
        print(f"[WebSocket] ❌ Error: {e}")

@socketio.on('get_clients')
def handle_get_clients():
    """✅ Obtener lista de clientes con estado completo"""
    if channel_manager:
        clients_info = channel_manager.get_all_clients_info()
        
        # ✅ Agregar información completa de cada cliente
        detailed_clients = []
        for client in clients_info:
            subscription = channel_manager.get_client_subscription(client['id'])
            if subscription:
                client['gains'] = subscription.get('gains', {})
                client['pans'] = subscription.get('pans', {})
                client['mutes'] = subscription.get('mutes', {})
                client['solos'] = list(subscription.get('solos', set()))
            detailed_clients.append(client)
        
        emit('clients_list', {'clients': detailed_clients})

@socketio.on('update_gain')
def handle_update_gain(data):
    """Actualizar ganancia (self - legacy, usar update_client_mix)"""
    client_id = request.sid
    channel = data.get('channel')
    gain = data.get('gain')
    
    if channel_manager:
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

@socketio.on('request_client_state')
def handle_request_client_state(data):
    """✅ NUEVO: Solicitar estado completo de un cliente"""
    target_client_id = data.get('client_id')
    
    if not channel_manager or not target_client_id:
        emit('error', {'message': 'Invalid request'})
        return
    
    subscription = channel_manager.get_client_subscription(target_client_id)
    if subscription:
        client_state = {
            'client_id': target_client_id,
            'channels': subscription.get('channels', []),
            'gains': subscription.get('gains', {}),
            'pans': subscription.get('pans', {}),
            'mutes': subscription.get('mutes', {}),
            'solos': list(subscription.get('solos', set())),
            'pre_listen': subscription.get('pre_listen'),
            'master_gain': subscription.get('master_gain', 1.0),
            'client_type': channel_manager.client_types.get(target_client_id, 'unknown')
        }
        emit('client_state', client_state)
    else:
        emit('error', {'message': 'Client not found'})

# Broadcast de actualización de clientes (llamado desde native_server)
def broadcast_clients_update():
    """✅ CORREGIDO: Enviar actualización de clientes sin 'broadcast' parameter"""
    if channel_manager:
        clients_info = channel_manager.get_all_clients_info()
        
        # Agregar info completa
        detailed_clients = []
        for client in clients_info:
            subscription = channel_manager.get_client_subscription(client['id'])
            if subscription:
                client['gains'] = subscription.get('gains', {})
                client['pans'] = subscription.get('pans', {})
                client['mutes'] = subscription.get('mutes', {})
                client['solos'] = list(subscription.get('solos', set()))
            detailed_clients.append(client)
        
        # ✅ CORREGIDO: Sin 'broadcast=True' - emit() ya hace broadcast por defecto
        socketio.emit('clients_update', {'clients': detailed_clients})

@app.errorhandler(404)
def not_found(e):
    if os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return send_from_directory(app.static_folder, 'index.html')
    else:
        return f"""
        <html>
        <head><title>404 - Not Found</title></head>
        <body style="font-family: monospace; padding: 20px; background: #0a0a0a; color: #00ff00;">
            <h1>❌ 404 - Not Found</h1>
            <p>Requested path: <code>{request.path}</code></p>
            <p>Frontend directory: <code>{app.static_folder}</code></p>
        </body>
        </html>
        """, 404

if __name__ == '__main__':
    print("[WebSocket] 🚀 Servidor WebSocket iniciando...")
    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False)