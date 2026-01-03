"""
WebSocket Server - COMPLETE & FIXED
✅ Control centralizado desde Web UI
✅ Gestión de clientes nativos y web
✅ Broadcast optimizado
✅ Detección de clientes zombie
"""

from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit, disconnect
import time
import os
import logging
import config
import threading  # ✅ Asegurar que threading esté disponible
import engineio.server

# ✅ PATCH: Forzar async_modes a solo 'threading' para PyInstaller
original_async_modes = engineio.base_server.BaseServer.async_modes
def patched_async_modes(self):
    return ['threading']
engineio.base_server.BaseServer.async_modes = patched_async_modes

# Configurar rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

# Configurar logging
logger = logging.getLogger(__name__)

# ✅ SUPRIMIR logs innecesarios
logging.getLogger('werkzeug').setLevel(logging.CRITICAL)
logging.getLogger('flask.app').setLevel(logging.WARNING)
logging.getLogger('flask_socketio').setLevel(logging.WARNING)

# Crear aplicación Flask
app = Flask(__name__, 
            static_folder=FRONTEND_DIR,
            template_folder=FRONTEND_DIR)

app.config['SECRET_KEY'] = 'audio-monitor-key-v2.5-fixed'

# Configurar SocketIO (sin app para evitar problemas de inicialización en exe)
socketio = SocketIO(
    cors_allowed_origins="*", 
    async_mode=None,  # ✅ Auto-detect (ahora forzado a threading por el patch)
    ping_timeout=30,  # ✅ AUMENTADO: 30s (era 10s)
    ping_interval=10,  # ✅ Cada 10s
    compression=False,
    max_http_buffer_size=1000000,
    engineio_logger=False,
    logger=False,
    always_connect=True,
    websocket_compression=False,
    binary=True
)

# Inicializar SocketIO con la app después
socketio.init_app(app)

# Estado global
channel_manager = None
web_clients = {}  # ✅ NUEVO: Tracking de clientes web
web_clients_lock = __import__('threading').Lock()

# ✅ Estado persistente para clientes web (auto-reconexión)
web_persistent_state = {}
web_persistent_lock = __import__('threading').Lock()

# ✅ Configuración de limpieza de estados persistentes
WEB_STATE_CACHE_TIMEOUT = 604800  # 7 días (1 semana)
WEB_MAX_PERSISTENT_STATES = 200  # Máximo 200 estados (más para músicos recurrentes)

# ✅ NUEVO: Callback para VU Levels
def broadcast_audio_levels(levels):
    """
    ✅ NUEVO: Emitir niveles de audio a todos los clientes conectados
    levels: dict con {channel: {'rms_percent': 0-100, 'peak_percent': 0-100, ...}}
    """
    try:
        socketio.emit('audio_levels', {
            'levels': levels,
            'timestamp': int(time.time() * 1000)
        }, broadcast=True, namespace='/')
    except Exception as e:
        logger.debug(f"[WebSocket] Error broadcasting audio levels: {e}")

def cleanup_expired_web_states():
    """Limpiar estados persistentes expirados para web clients"""
    current_time = time.time()
    
    with web_persistent_lock:
        expired = [
            pid for pid, state in web_persistent_state.items()
            if current_time - state.get('saved_at', 0) > WEB_STATE_CACHE_TIMEOUT
        ]
        
        for pid in expired:
            logger.info(f"🗑️ Limpiando estado web expirado: {pid[:20]}")
            del web_persistent_state[pid]
        
        # Limitar cantidad máxima de estados
        if len(web_persistent_state) > WEB_MAX_PERSISTENT_STATES:
            # Eliminar los más antiguos
            sorted_states = sorted(
                web_persistent_state.items(),
                key=lambda x: x[1].get('saved_at', 0)
            )
            to_remove = len(web_persistent_state) - WEB_MAX_PERSISTENT_STATES
            for pid, _ in sorted_states[:to_remove]:
                logger.info(f"🗑️ Limpiando estado web por límite: {pid[:20]}")
                del web_persistent_state[pid]


def init_server(manager):
    global channel_manager
    channel_manager = manager
    
    # ✅ Inyectar socketio en channel_manager para broadcasts
    if hasattr(channel_manager, 'set_socketio'):
        channel_manager.set_socketio(socketio)
    
    logger.info(f"[WebSocket] ✅ Inicializado (Control Central)")
    logger.info(f"[WebSocket]    Puerto: {config.WEB_PORT}")
    logger.info(f"[WebSocket]    Frontend: {FRONTEND_DIR}")
    logger.info(f"[WebSocket]    Ping interval: 10s, timeout: 30s")


def cleanup_initial_state():
    """Limpieza inicial de estados persistentes y clientes inválidos."""
    logger.info("[WebSocket] 🔄 Limpieza inicial de estados y clientes")

    # Limpiar estados persistentes expirados
    cleanup_expired_web_states()

    # Limpiar clientes web desconectados
    with web_clients_lock:
        disconnected_clients = [
            client_id for client_id, client_info in web_clients.items()
            if time.time() - client_info['last_activity'] > WEB_STATE_CACHE_TIMEOUT
        ]
        for client_id in disconnected_clients:
            logger.info(f"[WebSocket] 🗑️ Eliminando cliente desconectado: {client_id[:8]}")
            del web_clients[client_id]


# ============================================================================
# RUTAS FLASK
# ============================================================================

@app.route('/')
def index():
    """Página principal"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    """Archivos estáticos"""
    try:
        return send_from_directory(app.static_folder, path)
    except Exception as e:
        logger.debug(f"Error sirviendo archivo {path}: {e}")
        return "File not found", 404


@app.errorhandler(404)
def not_found(e):
    """Redirect 404 a index.html para SPA routing"""
    return send_from_directory(app.static_folder, 'index.html')


# ============================================================================
# EVENTOS SOCKETIO - CONEXIÓN
# ============================================================================

@socketio.on('connect')
def handle_connect(auth=None):
    """Cliente web conectado"""
    client_id = request.sid

    auth = auth or {}
    web_device_uuid = auth.get('device_uuid')
    
    # ✅ Registrar cliente web
    with web_clients_lock:
        web_clients[client_id] = {
            'connected_at': time.time(),
            'last_activity': time.time(),
            'address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown'),
            'device_uuid': web_device_uuid
        }
    
    logger.info(f"[WebSocket] ✅ Cliente web conectado: {client_id[:8]} ({request.remote_addr})")
    
    if not channel_manager:
        logger.warning(f"[WebSocket] ⚠️ Channel manager no inicializado")
        emit('error', {'message': 'Server not ready'})
        return
    
    try:
        # ✅ Enviar información del dispositivo
        device_info = {
            'name': 'Audio Interface RF',
            'channels': channel_manager.num_channels,
            'sample_rate': config.SAMPLE_RATE,
            'blocksize': config.BLOCKSIZE,
            'latency_ms': config.BLOCKSIZE / config.SAMPLE_RATE * 1000,
            'mode': 'control_center',
            'version': '2.5.0-FIXED',
            'operational_channels': list(channel_manager.get_operational_channels()),  # ✅ NUEVO
            'features': {
                'zombie_detection': True,
                'device_change_detection': True,
                'auto_reconnect': True,
                'int16_encoding': getattr(config, 'USE_INT16_ENCODING', True)
            }
        }
        emit('device_info', device_info)

        # --- Restaurar configuración persistente de canales si existe en device_registry ---
        restored_from_registry = False
        if web_device_uuid and getattr(channel_manager, 'device_registry', None):
            registry = channel_manager.device_registry
            config_prev = registry.get_configuration(web_device_uuid)
            if config_prev and config_prev.get('channels'):
                try:
                    channel_manager.subscribe_client(
                        client_id,
                        config_prev.get('channels', []),
                        gains=config_prev.get('gains', {}),
                        pans=config_prev.get('pans', {}),
                        client_type="web",
                        device_uuid=web_device_uuid
                    )
                    logger.info(f"[WebSocket] 🔄 Cliente restaurado desde device_registry: {len(config_prev.get('channels', []))} canales")
                    emit('auto_resubscribed', {
                        'channels': config_prev.get('channels', []),
                        'gains': config_prev.get('gains', {}),
                        'pans': config_prev.get('pans', {})
                    })
                    restored_from_registry = True
                except Exception as e:
                    logger.error(f"[WebSocket] Error restaurando config de device_registry: {e}")

        # Si no se restauró desde device_registry, intentar restaurar desde web_persistent_state (legacy)
        if not restored_from_registry:
            persistent_id = web_device_uuid or f"{request.remote_addr}_{request.headers.get('User-Agent', 'Unknown')}".replace(' ', '_')[:100]
            with web_persistent_lock:
                if persistent_id in web_persistent_state:
                    saved_state = web_persistent_state[persistent_id]
                    logger.info(f"[WebSocket] 💾 Estado persistente encontrado para {str(persistent_id)[:20]}")
                    try:
                        channel_manager.subscribe_client(
                            client_id,
                            saved_state.get('channels', []),
                            gains=saved_state.get('gains', {}),
                            pans=saved_state.get('pans', {}),
                            client_type="web",
                            device_uuid=web_device_uuid
                        )
                        logger.info(f"[WebSocket] ✅ Cliente resuscrito automáticamente: {len(saved_state.get('channels', []))} canales")
                        emit('auto_resubscribed', {
                            'channels': saved_state.get('channels', []),
                            'gains': saved_state.get('gains', {}),
                            'pans': saved_state.get('pans', {})
                        })
                    except Exception as e:
                        logger.error(f"[WebSocket] Error resuscrbiendo: {e}")

        # ✅ Enviar lista de clientes conectados (nativos + web)
        clients_info = get_all_clients_info()
        emit('clients_update', {'clients': clients_info})

        # ✅ Enviar estadísticas del servidor
        server_stats = get_server_stats()
        emit('server_stats', server_stats)

        logger.info(f"[WebSocket]    Info enviada: {len(clients_info)} clientes totales")

        # ✅ Registrar dispositivo web en DeviceRegistry (si existe)
        try:
            if web_device_uuid and getattr(channel_manager, 'device_registry', None):
                channel_manager.device_registry.register_device(web_device_uuid, {
                    'type': 'web',
                    'name': auth.get('device_name') or 'web-control',
                    'primary_ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', 'Unknown')
                })
        except Exception as e:
            logger.debug(f"[WebSocket] DeviceRegistry register failed: {e}")

    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en connect: {e}")
        import traceback
        traceback.print_exc()


@socketio.on('disconnect')
def handle_disconnect():
    """Cliente web desconectado"""
    client_id = request.sid
    
    # ✅ Generar persistent_id y guardar estado antes de desuscribir
    # ✅ Usar el mismo persistent_id que en connect (preferir device_uuid)
    web_device_uuid = None
    with web_clients_lock:
        if client_id in web_clients:
            web_device_uuid = web_clients[client_id].get('device_uuid')

    persistent_id = web_device_uuid or f"{request.remote_addr}_{request.headers.get('User-Agent', 'Unknown')}".replace(' ', '_')[:100]
    if channel_manager:
        subscription = channel_manager.get_client_subscription(client_id)
        if subscription:
            with web_persistent_lock:
                web_persistent_state[persistent_id] = {
                    'channels': subscription.get('channels', []),
                    'gains': subscription.get('gains', {}),
                    'pans': subscription.get('pans', {}),
                    'mutes': subscription.get('mutes', {}),
                    'solos': list(subscription.get('solos', set())),
                    'pre_listen': subscription.get('pre_listen'),
                    'master_gain': subscription.get('master_gain', 1.0),
                    'saved_at': time.time()
                }
                logger.info(f"[WebSocket] 💾 Estado guardado para reconexión: {str(persistent_id)[:20]}")
    
    # ✅ Remover de tracking
    with web_clients_lock:
        client_info = web_clients.pop(client_id, None)
    
    if client_info:
        connection_duration = time.time() - client_info['connected_at']
        logger.info(f"[WebSocket] 🔌 Cliente web desconectado: {client_id[:8]} "
                   f"({connection_duration:.1f}s)")
    
    # ✅ Desuscribir del channel manager
    if channel_manager:
        try:
            channel_manager.unsubscribe_client(client_id)
        except Exception as e:
            logger.error(f"[WebSocket] Error desuscribiendo: {e}")
    
    # ✅ Notificar a otros clientes
    try:
        broadcast_clients_update()
    except:
        pass


# ============================================================================
# EVENTOS SOCKETIO - SUSCRIPCIONES Y CONTROL
# ============================================================================

@socketio.on('subscribe')
def handle_subscribe(data):
    """
    Suscribir cliente web a canales
    data: {
        'channels': [0, 1, 2, ...],
        'gains': {0: 1.0, 1: 0.8, ...},
        'pans': {0: 0.0, 1: -0.5, ...}
    }
    """
    client_id = request.sid
    
    # ✅ Actualizar actividad
    update_client_activity(client_id)
    
    if not channel_manager:
        emit('error', {'message': 'Channel manager not available'})
        return
    
    try:
        channels = data.get('channels', [])
        gains = data.get('gains', {})
        pans = data.get('pans', {})
        
        # ✅ Convertir keys a int
        gains_int = {}
        pans_int = {}
        
        for k, v in gains.items():
            try:
                gains_int[int(k)] = float(v)
            except:
                pass
        
        for k, v in pans.items():
            try:
                pans_int[int(k)] = float(v)
            except:
                pass
        
        # ✅ Suscribir cliente
        channel_manager.subscribe_client(
            client_id, 
            channels, 
            gains_int,
            pans_int,
            client_type="web"
        )
        
        emit('subscribed', {
            'channels': channels,
            'gains': gains_int,
            'pans': pans_int
        })
        
        logger.info(f"[WebSocket] 📡 {client_id[:8]} suscrito: {len(channels)} canales")
        
        # ✅ Notificar a otros clientes
        broadcast_clients_update()
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en subscribe: {e}")
        emit('error', {'message': str(e)})


@socketio.on('update_client_mix')
def handle_update_client_mix(data):
    """
    ✅ Actualizar mezcla de un cliente específico (nativo o web)
    data: {
        'target_client_id': str,
        'channels': [...],
        'gains': {...},
        'pans': {...},
        'mutes': {...},
        'solos': [...],
        'pre_listen': int | None,
        'master_gain': float
    }
    """
    if not channel_manager:
        emit('error', {'message': 'Channel manager not available'})
        return
    
    # ✅ Actualizar actividad
    update_client_activity(request.sid)
    
    try:
        target_client_id = data.get('target_client_id')
        if not target_client_id:
            emit('error', {'message': 'target_client_id required'})
            return
        
        # ✅ Actualizar mezcla
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
            emit('mix_updated', {
                'client_id': target_client_id,
                'status': 'ok',
                'timestamp': int(time.time() * 1000)
            })
            
            logger.info(f"[WebSocket] 🎛️ Mezcla actualizada para {target_client_id[:15]}")
            
            # ✅ NUEVO: Guardar configuración en device_registry para persistencia
            try:
                subscription = channel_manager.get_client_subscription(target_client_id)
                device_uuid = subscription.get('device_uuid') if subscription else None
                
                if device_uuid and hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
                    # Preparar configuración para guardar
                    config_to_save = {
                        'channels': subscription.get('channels', []),
                        'gains': subscription.get('gains', {}),
                        'pans': subscription.get('pans', {}),
                        'mutes': subscription.get('mutes', {}),
                        'solos': list(subscription.get('solos', set())),
                        'pre_listen': subscription.get('pre_listen'),
                        'master_gain': subscription.get('master_gain', 1.0),
                        'timestamp': int(time.time() * 1000)
                    }
                    
                    channel_manager.device_registry.update_configuration(
                        device_uuid,
                        config_to_save
                    )
                    logger.debug(f"[WebSocket] 💾 Configuración guardada en device_registry: {device_uuid[:12]}")
            except Exception as e:
                logger.debug(f"[WebSocket] Error guardando config en device_registry: {e}")
            
            # ✅ Broadcast a todos (incluye el cambio)
            broadcast_clients_update()
            
        else:
            emit('error', {'message': f'Failed to update mix for {target_client_id}'})
    
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en update_client_mix: {e}")
        emit('error', {'message': str(e)})


@socketio.on('get_clients')
def handle_get_clients():
    """
    ✅ Obtener lista completa de clientes (nativos + web)
    """
    update_client_activity(request.sid)
    
    try:
        clients_info = get_all_clients_info()
        emit('clients_list', {
            'clients': clients_info,
            'timestamp': int(time.time() * 1000)
        })
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en get_clients: {e}")
        emit('error', {'message': str(e)})


@socketio.on('set_client_name')
def handle_set_client_name(data):
    """
    ✅ NUEVO: Guardar nombre personalizado de cliente
    data: {
        'client_id': str,
        'custom_name': str
    }
    """
    update_client_activity(request.sid)
    
    try:
        client_id = data.get('client_id')
        custom_name = data.get('custom_name')
        
        if not client_id or not custom_name:
            emit('error', {'message': 'client_id and custom_name required'})
            return
        
        if not channel_manager:
            emit('error', {'message': 'Channel manager not available'})
            return
        
        # Obtener device_uuid del cliente
        subscription = channel_manager.get_client_subscription(client_id)
        if not subscription:
            emit('error', {'message': f'Client {client_id} not found'})
            return
        
        device_uuid = subscription.get('device_uuid')
        
        # Guardar nombre personalizado en device_registry
        if device_uuid and hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
            success = channel_manager.device_registry.set_custom_name(device_uuid, custom_name)
            if success:
                logger.info(f"[WebSocket] 📝 Nombre personalizado guardado: {client_id[:8]} = {custom_name}")
                emit('client_name_saved', {
                    'client_id': client_id,
                    'custom_name': custom_name,
                    'status': 'ok'
                })
                
                # Notificar a todos los clientes de la actualización
                broadcast_clients_update()
            else:
                emit('error', {'message': 'Failed to save custom name'})
        else:
            emit('error', {'message': 'Device registry not available or no device_uuid'})
    
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en set_client_name: {e}")
        emit('error', {'message': str(e)})


@socketio.on('update_gain')
def handle_update_gain(data):
    """
    Actualizar ganancia de un canal (para el cliente actual)
    data: {
        'channel': int,
        'gain': float
    }
    """
    client_id = request.sid
    update_client_activity(client_id)
    
    if not channel_manager:
        return
    
    try:
        channel = data.get('channel')
        gain = data.get('gain')
        
        if channel is None or gain is None:
            return
        
        # ✅ Actualizar en channel manager
        if client_id in channel_manager.subscriptions:
            channel_manager.subscriptions[client_id]['gains'][int(channel)] = float(gain)
            
            if config.DEBUG:
                logger.debug(f"[WebSocket] 🎚️ {client_id[:8]} - Canal {channel}: {gain:.2f}")
            
            # ✅ NUEVO: Guardar en device_registry
            _save_client_config_to_registry(client_id)
    
    except Exception as e:
        if config.DEBUG:
            logger.error(f"[WebSocket] Error update_gain: {e}")


@socketio.on('update_pan')
def handle_update_pan(data):
    """
    ✅ NUEVO: Actualizar panorama de un canal
    data: {
        'channel': int,
        'pan': float (-1.0 a 1.0)
    }
    """
    client_id = request.sid
    update_client_activity(client_id)
    
    if not channel_manager:
        return
    
    try:
        channel = data.get('channel')
        pan = data.get('pan')
        
        if channel is None or pan is None:
            return
        
        # ✅ Actualizar en channel manager
        if client_id in channel_manager.subscriptions:
            channel_manager.subscriptions[client_id]['pans'][int(channel)] = float(pan)
            
            if config.DEBUG:
                logger.debug(f"[WebSocket] 🔊 {client_id[:8]} - Canal {channel} pan: {pan:.2f}")
            
            # ✅ NUEVO: Guardar en device_registry
            _save_client_config_to_registry(client_id)
    
    except Exception as e:
        if config.DEBUG:
            logger.error(f"[WebSocket] Error update_pan: {e}")


@socketio.on('disconnect_client')
def handle_disconnect_client(data):
    """
    ✅ NUEVO: Forzar desconexión de un cliente
    data: {
        'target_client_id': str
    }
    """
    if not channel_manager:
        return
    
    update_client_activity(request.sid)
    
    try:
        target_client_id = data.get('target_client_id')
        if not target_client_id:
            return
        
        logger.info(f"[WebSocket] 🔌 Desconexión forzada: {target_client_id[:15]}")
        
        # ✅ Desuscribir del channel manager
        channel_manager.unsubscribe_client(target_client_id)
        
        # ✅ Si es cliente web, desconectar socket
        if target_client_id in web_clients:
            disconnect(sid=target_client_id)
        
        # ✅ Broadcast actualización
        broadcast_clients_update()
        
        emit('client_disconnected', {
            'client_id': target_client_id,
            'timestamp': int(time.time() * 1000)
        })
        
    except Exception as e:
        logger.error(f"[WebSocket] Error disconnect_client: {e}")


# ============================================================================
# EVENTOS SOCKETIO - MONITOREO
# ============================================================================

@socketio.on('ping')
def handle_ping(data):
    """
    Medir latencia de red
    data: {'timestamp': int}
    """
    update_client_activity(request.sid)
    
    emit('pong', {
        'client_timestamp': data.get('timestamp', 0),
        'server_timestamp': int(time.time() * 1000)
    })


@socketio.on('get_server_stats')
def handle_get_server_stats():
    """
    ✅ NUEVO: Obtener estadísticas del servidor
    """
    update_client_activity(request.sid)
    
    try:
        stats = get_server_stats()
        emit('server_stats', stats)
        
    except Exception as e:
        logger.error(f"[WebSocket] Error get_server_stats: {e}")


@socketio.on('heartbeat')
def handle_heartbeat(data):
    """
    ✅ NUEVO: Heartbeat explícito de cliente web
    """
    client_id = request.sid
    update_client_activity(client_id)
    
    emit('heartbeat_ack', {
        'timestamp': int(time.time() * 1000)
    })


# ============================================================================
# FUNCIONES HELPER
# ============================================================================

def update_client_activity(client_id):
    """✅ Actualizar timestamp de actividad de cliente web"""
    with web_clients_lock:
        if client_id in web_clients:
            web_clients[client_id]['last_activity'] = time.time()


def _save_client_config_to_registry(client_id):
    """
    ✅ NUEVO: Guardar configuración de cliente en device_registry de forma permanente
    """
    try:
        if not channel_manager:
            return
        
        subscription = channel_manager.get_client_subscription(client_id)
        if not subscription:
            return
        
        device_uuid = subscription.get('device_uuid')
        
        if device_uuid and hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
            # Preparar configuración para guardar
            config_to_save = {
                'channels': subscription.get('channels', []),
                'gains': subscription.get('gains', {}),
                'pans': subscription.get('pans', {}),
                'mutes': subscription.get('mutes', {}),
                'solos': list(subscription.get('solos', set())),
                'pre_listen': subscription.get('pre_listen'),
                'master_gain': subscription.get('master_gain', 1.0),
                'timestamp': int(time.time() * 1000)
            }
            
            channel_manager.device_registry.update_configuration(
                device_uuid,
                config_to_save
            )
    except Exception as e:
        logger.debug(f"[WebSocket] Error guardando config en device_registry: {e}")


def get_all_clients_info():
    """
    ✅ Obtener información de TODOS los clientes (nativos + web)
    """
    # --- NUEVO: Mostrar todos los dispositivos conocidos (persistentes y activos) ---
    all_devices = []
    device_registry = getattr(channel_manager, 'device_registry', None)
    if device_registry:
        try:
            all_devices = device_registry.get_all_devices(active_only=False)
        except Exception as e:
            logger.error(f"[WebSocket] Error obteniendo dispositivos de device_registry: {e}")

    # Obtener clientes activos en memoria
    active_clients = {}
    if channel_manager:
        try:
            for c in channel_manager.get_all_clients_info():
                # Indexar por device_uuid si existe, sino por id
                key = c.get('device_uuid') or c.get('id')
                active_clients[key] = c
        except Exception as e:
            logger.error(f"[WebSocket] Error obteniendo clientes activos: {e}")

    # Unir info persistente y activa
    merged_clients = []
    seen_uuids = set()
    for device in all_devices:
        device_uuid = device.get('uuid')
        config_data = device.get('configuration', {})
        client_info = {
            'id': device_uuid,
            'type': device.get('type', 'unknown'),
            'device_uuid': device_uuid,
            'device_model': device.get('device_info', {}).get('model') or device.get('device_info', {}).get('device_model'),
            'custom_name': device.get('custom_name'),
            'device_name': device.get('name'),
            'channels': config_data.get('channels', []),
            'gains': config_data.get('gains', {}),
            'pans': config_data.get('pans', {}),
            'solos': config_data.get('solos', []),
            'active_channels': len(config_data.get('channels', [])),
            'has_solo': bool(config_data.get('solos')),
            'pre_listen': config_data.get('pre_listen'),
            'master_gain': config_data.get('master_gain', 1.0),
            'last_update': device.get('last_seen', 0),
            'connected': False,
            'address': device.get('primary_ip'),
            'connected_at': device.get('first_seen'),
            'last_activity': device.get('last_seen'),
        }
        # Si está activo, sobreescribir info
        active = active_clients.get(device_uuid)
        if active:
            client_info.update(active)
            client_info['connected'] = True
        merged_clients.append(client_info)
        seen_uuids.add(device_uuid)

    # Agregar clientes activos que no tengan device_uuid (ej: legacy o sin registro)
    for key, active in active_clients.items():
        if key and key not in seen_uuids:
            merged_clients.append(active)

    # Enriquecer con info de web_clients (address, last_activity)
    with web_clients_lock:
        for client_info in merged_clients:
            client_id = client_info.get('id')
            if client_id in web_clients:
                web_info = web_clients[client_id]
                client_info['address'] = web_info.get('address')
                client_info['connected_at'] = web_info.get('connected_at')
                client_info['last_activity'] = web_info.get('last_activity')

    # Ordenar: conectados primero, luego desconectados
    merged_clients.sort(key=lambda c: (not c.get('connected', False), -(c.get('last_activity') or 0)))
    return merged_clients


def get_server_stats():
    """
    ✅ NUEVO: Obtener estadísticas completas del servidor
    """
    stats = {
        'timestamp': int(time.time() * 1000),
        'web_clients': 0,
        'native_clients': 0,
        'total_clients': 0,
        'channel_manager': {},
        'native_server': {}
    }
    
    if not channel_manager:
        return stats
    
    try:
        # ✅ Estadísticas de channel manager
        cm_stats = channel_manager.get_stats()
        stats['channel_manager'] = cm_stats
        stats['web_clients'] = cm_stats.get('web_clients', 0)
        stats['native_clients'] = cm_stats.get('native_clients', 0)
        stats['total_clients'] = cm_stats.get('total_clients', 0)
        
        # ✅ Estadísticas de native server
        try:
            from audio_server import native_server
            if hasattr(native_server, 'get_stats'):
                native_stats = native_server.get_stats()
                stats['native_server'] = native_stats
        except:
            pass
        
    except Exception as e:
        logger.error(f"[WebSocket] Error obteniendo stats: {e}")
    
    return stats


def broadcast_clients_update():
    """Optimización de la actualización de clientes."""
    try:
        clients_info = get_all_clients_info()
        socketio.emit('clients_update', {'clients': clients_info})
        logger.info(f"[WebSocket] 📡 Actualización enviada: {len(clients_info)} clientes")
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en broadcast_clients_update: {e}")


def broadcast_client_disconnected(client_id):
    """
    ✅ NUEVO: Notificar desconexión de cliente específico
    """
    try:
        with app.app_context():
            socketio.emit('client_disconnected', {
                'client_id': client_id,
                'timestamp': int(time.time() * 1000)
            }, include_self=False)
        
        logger.info(f"[WebSocket] 📢 Broadcast desconexión: {client_id[:15]}")
        
    except Exception as e:
        logger.error(f"[WebSocket] Error broadcast disconnect: {e}")


# ============================================================================
# MANTENIMIENTO EN BACKGROUND
# ============================================================================

def start_maintenance_thread():
    """
    ✅ NUEVO: Thread de mantenimiento para limpiar clientes web inactivos
    """
    import threading
    
    def maintenance_loop():
        while True:
            time.sleep(30)  # Cada 30 segundos
            
            try:
                current_time = time.time()
                timeout = 120.0  # 2 minutos sin actividad
                
                with web_clients_lock:
                    inactive_clients = []
                    
                    for client_id, info in web_clients.items():
                        last_activity = info.get('last_activity', 0)
                        if current_time - last_activity > timeout:
                            inactive_clients.append(client_id)
                    
                    if inactive_clients:
                        logger.info(f"[WebSocket] 🧹 Limpiando {len(inactive_clients)} clientes web inactivos")
                        
                        for client_id in inactive_clients:
                            web_clients.pop(client_id, None)
                            
                            # Desuscribir del channel manager
                            if channel_manager:
                                channel_manager.unsubscribe_client(client_id)
                            
                            # Desconectar socket
                            try:
                                disconnect(sid=client_id)
                            except:
                                pass
                
                # Broadcast actualización
                if inactive_clients:
                    # broadcast_clients_update()  # ✅ REMOVED: Causa errores de contexto
                    pass
                
                # ✅ Limpiar estados persistentes expirados
                cleanup_expired_web_states()
                    
            except Exception as e:
                logger.error(f"[WebSocket] Error en maintenance: {e}")
    
    thread = threading.Thread(target=maintenance_loop, daemon=True)
    thread.start()
    logger.info("[WebSocket] ✅ Thread de mantenimiento iniciado")


# ============================================================================
# INICIALIZACIÓN
# ============================================================================

# ✅ Iniciar thread de mantenimiento al importar
start_maintenance_thread()


# ============================================================================
# MAIN - Para testing standalone
# ============================================================================

if __name__ == '__main__':
    print("\n" + "="*70)
    print("  WEBSOCKET SERVER - STANDALONE MODE")
    print("="*70)
    print(f"  🌐 Host: {config.WEB_HOST}:{config.WEB_PORT}")
    print(f"  📁 Frontend: {FRONTEND_DIR}")
    print("="*70 + "\n")
    
    # Mock channel manager para testing
    class MockChannelManager:
        def __init__(self):
            self.num_channels = 8
            self.subscriptions = {}
        def subscribe_client(self, client_id, channels, gains=None, pans=None, client_type="web"):
            self.subscriptions[client_id] = {
                'channels': channels,
                'gains': gains or {},
                'pans': pans or {},
                'client_type': client_type
            }
        def unsubscribe_client(self, client_id):
            self.subscriptions.pop(client_id, None)
        def get_all_clients_info(self):
            return [
                {
                    'id': cid,
                    'type': sub['client_type'],
                    'channels': sub['channels'],
                    'active_channels': len(sub['channels'])
                }
                for cid, sub in self.subscriptions.items()
            ]
        def get_stats(self):
            return {
                'total_clients': len(self.subscriptions),
                'web_clients': sum(1 for s in self.subscriptions.values() if s['client_type'] == 'web'),
                'native_clients': sum(1 for s in self.subscriptions.values() if s['client_type'] == 'native')
            }

    # Export for tests
    globals()['MockChannelManager'] = MockChannelManager
    init_server(MockChannelManager())
    
    socketio.run(
        app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        debug=False,
        log_output=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )