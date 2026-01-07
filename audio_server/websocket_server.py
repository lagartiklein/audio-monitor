"""
WebSocket Server - COMPLETE & FIXED
✅ Control centralizado desde Web UI
✅ Gestión de clientes nativos y web
✅ Broadcast optimizado
✅ Detección de clientes zombie
✅ NUEVO: Streaming de audio para cliente maestro
"""

from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit, disconnect
import time
import os
import logging
import config
import threading  # ✅ Asegurar que threading esté disponible
import json
import numpy as np
import engineio.server
import math
import uuid  # ✅ NUEVO: Para generar device_uuid únicos
from audio_server.audio_mixer import get_audio_mixer

# Configurar logging PRIMERO (antes de usarlo)
logger = logging.getLogger(__name__)

# Configurar rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

# ✅ NUEVO: Estado UI global (orden de clientes) compartido entre navegadores
UI_STATE_FILE = os.path.join(BASE_DIR, 'config', 'web_ui_state.json')
ui_state_lock = __import__('threading').Lock()
ui_state = {
    'client_order': [],
    'updated_at': 0
}


def _load_ui_state_from_disk():
    """Cargar estado global de UI desde disco."""
    try:
        os.makedirs(os.path.dirname(UI_STATE_FILE) or '.', exist_ok=True)
        if not os.path.exists(UI_STATE_FILE):
            return
        with open(UI_STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        order = data.get('client_order', [])
        if not isinstance(order, list):
            order = []

        # Si el cliente maestro está deshabilitado, eliminarlo del orden persistido
        if not getattr(config, 'MASTER_CLIENT_ENABLED', False):
            master_uuid = getattr(config, 'MASTER_CLIENT_UUID', '__master_server_client__')
            order = [x for x in order if str(x) != str(master_uuid)]

        with ui_state_lock:
            ui_state['client_order'] = order
            ui_state['updated_at'] = int(data.get('updated_at') or 0)
        logger.info(f"[WebSocket] 🧭 UI state cargado: {len(order)} items")

        # Persistir limpieza si se removió el maestro
        if not getattr(config, 'MASTER_CLIENT_ENABLED', False):
            _save_ui_state_to_disk()
    except Exception as e:
        logger.debug(f"[WebSocket] UI state load failed: {e}")


def _save_ui_state_to_disk():
    """Guardar estado global de UI a disco."""
    try:
        os.makedirs(os.path.dirname(UI_STATE_FILE) or '.', exist_ok=True)
        with ui_state_lock:
            payload = {
                'client_order': ui_state.get('client_order', []),
                'updated_at': ui_state.get('updated_at', 0)
            }

        tmp_path = UI_STATE_FILE + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, UI_STATE_FILE)
    except Exception as e:
        logger.debug(f"[WebSocket] UI state save failed: {e}")


def _get_client_order() -> list:
    with ui_state_lock:
        order = ui_state.get('client_order', [])
        return order[:] if isinstance(order, list) else []


def _set_client_order(order: list, known_device_uuids: list) -> list:
    """Sanitiza y guarda orden global. Retorna el orden final persistido."""
    if not isinstance(order, list):
        order = []

    # Normalizar a strings y filtrar unknowns
    normalized = []
    for v in order:
        if v is None:
            continue
        s = str(v)
        if s and s not in normalized:
            normalized.append(s)

    known_set = set(str(x) for x in (known_device_uuids or []) if x is not None)
    normalized = [x for x in normalized if x in known_set]

    # Agregar los conocidos que falten al final (mantener orden previo si existe)
    for dev in known_device_uuids or []:
        dev = str(dev)
        if dev and dev not in normalized:
            normalized.append(dev)

    with ui_state_lock:
        ui_state['client_order'] = normalized
        ui_state['updated_at'] = int(time.time() * 1000)

    _save_ui_state_to_disk()
    return normalized


# Cargar estado al importar
_load_ui_state_from_disk()

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
    async_mode="threading",  # Forzado para compatibilidad con PyInstaller
    ping_timeout=15,  # ✅ REDUCIDO: 15s para detección más rápida de desconexiones
    ping_interval=5,  # ✅ AUMENTADO: 5s (ping cada 5 segundos)
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
native_server_instance = None
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


# ✅ NUEVO: Streaming de audio para cliente maestro
master_audio_listeners = {}  # sid -> True (clientes web que escuchan audio del maestro)
master_audio_lock = __import__('threading').Lock()


def broadcast_master_audio(audio_data: bytes, sample_rate: int, channels: int):
    """
    ✅ NUEVO: Emitir audio mezclado del cliente maestro a los listeners web
    
    Args:
        audio_data: bytes del audio en formato int16
        sample_rate: tasa de muestreo
        channels: número de canales en la mezcla
    """
    try:
        if not getattr(config, 'MASTER_CLIENT_ENABLED', False) or not getattr(config, 'WEB_AUDIO_STREAM_ENABLED', False):
            return
        with master_audio_lock:
            if not master_audio_listeners:
                return
            
            listeners = list(master_audio_listeners.keys())
        
        # Emitir solo a los listeners activos
        for sid in listeners:
            try:
                socketio.emit('master_audio_data', {
                    'audio': audio_data,  # bytes en base64 si es necesario
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'timestamp': int(time.time() * 1000)
                }, to=sid, namespace='/')
            except Exception as e:
                logger.debug(f"[WebSocket] Error enviando audio a {sid[:8]}: {e}")
    except Exception as e:
        logger.debug(f"[WebSocket] Error en broadcast_master_audio: {e}")


def broadcast_master_audio_internal(audio_data: bytes, sample_rate: int, channels: int, master_client_id: str):
    """
    ✅ NUEVO: Versión interna de broadcast (llamada desde AudioMixer)
    Encapsula audio en base64 si es necesario para transmisión WebSocket
    """
    try:
        if not getattr(config, 'MASTER_CLIENT_ENABLED', False) or not getattr(config, 'WEB_AUDIO_STREAM_ENABLED', False):
            return
        import base64
        
        with master_audio_lock:
            if not master_audio_listeners:
                return
            
            listeners = list(master_audio_listeners.keys())
        
        # Codificar audio en base64 para transmisión segura vía WebSocket
        audio_b64 = base64.b64encode(audio_data).decode('ascii')
        
        for sid in listeners:
            try:
                socketio.emit('master_audio_data', {
                    'audio': audio_b64,
                    'sample_rate': sample_rate,
                    'channels': channels,
                    'client_id': master_client_id,
                    'timestamp': int(time.time() * 1000)
                }, to=sid, namespace='/')
            except Exception as e:
                if config.DEBUG:
                    logger.debug(f"[WebSocket] Error enviando audio a {sid[:8]}: {e}")
    except Exception as e:
        logger.debug(f"[WebSocket] Error en broadcast_master_audio_internal: {e}")


def register_master_audio_listener(sid: str):
    """✅ NUEVO: Registrar un cliente web para recibir audio del maestro"""
    with master_audio_lock:
        master_audio_listeners[sid] = True
        logger.info(f"[WebSocket] 🎧 Listener de audio maestro registrado: {sid[:8]}")


def unregister_master_audio_listener(sid: str):
    """✅ NUEVO: Desregistrar un cliente web del audio del maestro"""
    with master_audio_lock:
        if sid in master_audio_listeners:
            del master_audio_listeners[sid]
            logger.info(f"[WebSocket] 🎧 Listener de audio maestro removido: {sid[:8]}")


# ✅ NUEVO: Funciones de push para cliente nativo (receptor pasivo)

def push_channel_update_to_native(channel_id: int, active: bool = None, gainDb: float = None, pan: float = None):
    """
    ✅ NUEVO: Enviar cambio de canal al cliente nativo Android
    
    Args:
        channel_id: ID del canal (0-indexed)
        active: Estado del canal (True/False)
        gainDb: Ganancia en dB (-60 a +12)
        pan: Pan normalizado (-1.0 a +1.0)
    """
    if not native_server_instance:
        logger.debug("[WebSocket] Native server not available for push")
        return
    
    try:
        # Construir mensaje de actualización
        message = {
            'type': 'channel_update',
            'channel': channel_id
        }
        
        if active is not None:
            message['active'] = active
        if gainDb is not None:
            message['gainDb'] = float(gainDb)
        if pan is not None:
            message['pan'] = float(pan)
        
        # Enviar a todos los clientes nativos conectados
        logger.info(f"[WebSocket] 📤 Push a APK: Canal {channel_id} - {message}")
        native_server_instance.broadcast_to_native_clients(message)
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en push_channel_update_to_native: {e}")


def push_master_gain_to_native(gainDb: float):
    """
    ✅ NUEVO: Enviar cambio de ganancia maestra al cliente nativo
    
    Args:
        gainDb: Ganancia maestra en dB
    """
    if not native_server_instance:
        return
    
    try:
        message = {
            'type': 'master_gain_update',
            'gainDb': float(gainDb)
        }
        logger.info(f"[WebSocket] 📤 Push a APK: Master Gain = {gainDb}dB")
        native_server_instance.broadcast_to_native_clients(message)
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en push_master_gain_to_native: {e}")


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


def init_server(manager, native_server=None):
    global channel_manager, native_server_instance
    channel_manager = manager
    native_server_instance = native_server
    
    # ✅ Inyectar socketio en channel_manager para broadcasts
    if hasattr(channel_manager, 'set_socketio'):
        channel_manager.set_socketio(socketio)
    
    # ✅ Conectar audio mixer SOLO si está habilitado el cliente maestro
    if getattr(config, 'MASTER_CLIENT_ENABLED', False) and getattr(config, 'WEB_AUDIO_STREAM_ENABLED', False):
        audio_mixer = get_audio_mixer()
        if audio_mixer:
            audio_mixer.set_audio_callback(broadcast_master_audio_internal)
            logger.info(f"[WebSocket] ✅ Audio Mixer conectado")
    
    logger.info(f"[WebSocket] ✅ Inicializado (Control Central)")
    logger.info(f"[WebSocket]    Puerto: {config.WEB_PORT}")
    logger.info(f"[WebSocket]    Frontend: {FRONTEND_DIR}")
    logger.info(f"[WebSocket]    Ping interval: 5s, timeout: 15s (MEJORADO PARA DETECCIÓN RÁPIDA)")


def cleanup_initial_state():
    """Limpieza inicial de estados persistentes y clientes inválidos."""
    logger.info("[WebSocket] 🔄 Limpieza inicial de estados y clientes")

    # Limpiar estados persistentes expirados
    cleanup_expired_web_states()

    # Limpiar clientes web desconectados (timeout más agresivo)
    web_client_timeout = getattr(config, 'WEB_CLIENT_TIMEOUT', 10.0)
    with web_clients_lock:
        disconnected_clients = [
            client_id for client_id, client_info in web_clients.items()
            if time.time() - client_info['last_activity'] > web_client_timeout
        ]
        for client_id in disconnected_clients:
            logger.info(f"[WebSocket] 🗑️ Cliente web zombie desconectado: {client_id[:8]}")
            del web_clients[client_id]


# ============================================================================
# RUTAS FLASK
# ============================================================================

@app.route('/')
def index():
    """Página principal"""
    response = send_from_directory(app.static_folder, 'index.html')
    # ✅ No cachear HTML para asegurar cambios inmediatos
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


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

def _restore_client_channels_state(client_id: str, channel_manager) -> dict:
    """
    ✅ NUEVO: Restaurar estado de canales guardado para un cliente
    
    Retorna el estado restaurado (puede estar vacío si no hay guardado)
    """
    if not hasattr(channel_manager, 'device_registry') or not channel_manager.device_registry:
        return {}
    
    try:
        registry = channel_manager.device_registry
        saved_state = registry.get_channels_state(client_id)
        
        if saved_state:
            logger.info(f"[WebSocket] 🔄 Estado de canales restaurado para {client_id[:12]}: "
                       f"{len(saved_state.get('channels', []))} canales")
            return saved_state
        
        return {}
        
    except Exception as e:
        logger.debug(f"[WebSocket] Error restaurando estado de canales: {e}")
        return {}


@socketio.on('connect')
def handle_connect(auth=None):
    """Cliente web conectado"""
    client_id = request.sid

    auth = auth or {}
    web_device_uuid = auth.get('device_uuid')
    uuid_assigned = False
    
    # ✅ NUEVO: Si no hay device_uuid, generar uno único para este web
    if not web_device_uuid:
        web_device_uuid = f"web-{uuid.uuid4().hex[:12]}"
        uuid_assigned = True
    
    # ✅ Registrar cliente web
    with web_clients_lock:
        web_clients[client_id] = {
            'connected_at': time.time(),
            'last_activity': time.time(),
            'address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown'),
            'device_uuid': web_device_uuid  # ✅ SIEMPRE tendrá valor
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

        # ✅ Informar al frontend del UUID asignado (si se generó uno nuevo)
        emit('device_uuid_assigned', {
            'device_uuid': web_device_uuid,
            'assigned': uuid_assigned
        })

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
                    # subscribe_client no acepta mutes/master_gain: aplicar por update_client_mix
                    try:
                        channel_manager.update_client_mix(
                            client_id,
                            mutes=config_prev.get('mutes', {}),
                            master_gain=config_prev.get('master_gain')
                        )
                    except Exception:
                        pass
                    logger.info(f"[WebSocket] 🔄 Cliente restaurado desde device_registry: {len(config_prev.get('channels', []))} canales")
                    emit('auto_resubscribed', {
                        'channels': config_prev.get('channels', []),
                        'gains': config_prev.get('gains', {}),
                        'pans': config_prev.get('pans', {}),
                        'mutes': config_prev.get('mutes', {}),
                        'master_gain': config_prev.get('master_gain', 1.0)
                    })
                    restored_from_registry = True
                except Exception as e:
                    logger.error(f"[WebSocket] Error restaurando config de device_registry: {e}")

        # ✅ CONFIGURACIÓN DE SESIÓN: No restaurar desde web_persistent_state (legacy)
        # Las configuraciones se pierden al desconectar - no hay auto-restauración entre sesiones


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
    
    # ✅ CONFIGURACIÓN DE SESIÓN: No guardar estado persistente
    # Las configuraciones de clientes web se pierden al desconectar (solo durante la sesión)
    
    # ✅ NUEVO: Desregistrar listener de audio maestro si estaba activo
    unregister_master_audio_listener(client_id)
    
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
        
        # ✅ Obtener device_uuid del cliente web si existe
        web_device_uuid = None
        with web_clients_lock:
            if client_id in web_clients:
                web_device_uuid = web_clients[client_id].get('device_uuid')
        
        # ✅ Si no hay canales y hay device_uuid, intentar restaurar de device_registry
        if not channels and web_device_uuid and hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
            try:
                saved_config = channel_manager.device_registry.get_configuration(web_device_uuid)
                if saved_config and saved_config.get('channels'):
                    channels = saved_config.get('channels', [])
                    gains_int = saved_config.get('gains', {})
                    pans_int = saved_config.get('pans', {})
                    logger.info(f"[WebSocket] 📂 Configuración restaurada desde device_registry: {len(channels)} canales")
            except Exception as e:
                logger.debug(f"[WebSocket] Error restaurando de device_registry: {e}")
        
        # ✅ Suscribir cliente
        channel_manager.subscribe_client(
            client_id, 
            channels, 
            gains_int,
            pans_int,
            client_type="web",
            device_uuid=web_device_uuid  # ✅ Pasar device_uuid
        )
        
        emit('subscribed', {
            'channels': channels,
            'gains': gains_int,
            'pans': pans_int
        })
        
        logger.info(f"[WebSocket] 📡 {client_id[:8]} suscrito: {len(channels)} canales")
        
        # ✅ CONFIGURACIÓN DE SESIÓN: No guardar en device_registry
        # Las configuraciones solo persisten en memoria durante la sesión actual
        
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
        
        # ✅ Guardar estado previo para detectar cambios
        prev_subscription = channel_manager.get_client_subscription(target_client_id)
        prev_channels = set(prev_subscription.get('channels', [])) if prev_subscription else set()
        
        # ✅ Si el cliente no existe aún, crearlo (suscribción inicial)
        if not prev_subscription:
            # Get device_uuid from web_clients if available
            device_uuid = None
            with web_clients_lock:
                if target_client_id in web_clients:
                    device_uuid = web_clients[target_client_id].get('device_uuid')
            
            # Create initial subscription with provided channels
            channels = data.get('channels', [])
            try:
                sub_success = channel_manager.subscribe_client(
                    target_client_id,
                    channels=channels,
                    gains=data.get('gains'),
                    pans=data.get('pans'),
                    client_type='web',
                    device_uuid=device_uuid
                )
                if not sub_success:
                    emit('error', {'message': f'Failed to create subscription for {target_client_id}'})
                    logger.error(f"[WebSocket] subscribe_client returned False for {target_client_id[:15]}")
                    return
                logger.info(f"[WebSocket] New web client subscribed: {target_client_id[:15]} ({len(channels)} channels)")
            except Exception as e:
                emit('error', {'message': f'Error creating subscription: {str(e)}'})
                logger.error(f"[WebSocket] Error in subscribe_client: {e}", exc_info=True)
                return
            
            # Refresh subscription after creation
            prev_subscription = channel_manager.get_client_subscription(target_client_id)
        
        # ✅ Actualizar mezcla
        success = channel_manager.update_client_mix(
            target_client_id,
            channels=data.get('channels'),
            gains=data.get('gains'),
            pans=data.get('pans'),
            mutes=data.get('mutes'),
            master_gain=data.get('master_gain')
        )
        
        if success:
            emit('mix_updated', {
                'client_id': target_client_id,
                'status': 'ok',
                'timestamp': int(time.time() * 1000)
            })
            
            logger.info(f"[WebSocket] 🎛️ Mezcla actualizada para {target_client_id[:15]}")
            
            # ✅ SINCRONIZACIÓN BIDIRECCIONAL: Emitir cambios específicos para actualización inmediata
            new_subscription = channel_manager.get_client_subscription(target_client_id)
            if new_subscription:
                new_channels = set(new_subscription.get('channels', []))
                
                timestamp = int(time.time() * 1000)
                
                # Emitir cambios de canales (activados/desactivados)
                for ch in new_channels - prev_channels:  # Nuevos canales activados
                    socketio.emit('param_sync', {
                        'type': 'channel_toggle', 'channel': ch, 'value': True,
                        'client_id': target_client_id, 'source': 'web', 'timestamp': timestamp
                    }, skip_sid=request.sid)
                for ch in prev_channels - new_channels:  # Canales desactivados
                    socketio.emit('param_sync', {
                        'type': 'channel_toggle', 'channel': ch, 'value': False,
                        'client_id': target_client_id, 'source': 'web', 'timestamp': timestamp
                    }, skip_sid=request.sid)
            
            # ✅ NUEVO: Guardar estado de canales para persistencia
            _save_client_config_to_registry(target_client_id)
            
            # ✅ Broadcast a todos (incluye el cambio completo)
            broadcast_clients_update()

            # ✅ Si el target es un cliente nativo conectado, empujar mix_state en tiempo real
            try:
                subscription = channel_manager.get_client_subscription(target_client_id)
                if subscription and subscription.get('client_type') == 'native':
                    if native_server_instance is not None:
                        native_server_instance.push_mix_state_to_client(target_client_id)
            except Exception as e:
                logger.debug(f"[WebSocket] mix_state push failed: {e}")
            
        else:
            # Debug: log what went wrong
            subscription_check = channel_manager.get_client_subscription(target_client_id)
            logger.error(f"[WebSocket] update_client_mix failed: subscription_check={subscription_check is not None} for {target_client_id[:15]}")
            emit('error', {'message': f'Failed to update mix for {target_client_id}'})
    
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en update_client_mix: {e}")
        emit('error', {'message': str(e)})


@socketio.on('get_clients')
def handle_get_clients():
    """
    ✅ Obtener lista completa de clientes ACTIVOS (sin duplicados)
    """
    update_client_activity(request.sid)
    
    try:
        clients_info = get_all_clients_info()
        
        # ✅ NUEVO: Deduplicar por ID
        seen_ids = set()
        unique_clients = []
        
        for client in clients_info:
            client_id = client.get('id')
            if client_id not in seen_ids:
                seen_ids.add(client_id)
                unique_clients.append(client)
        
        emit('clients_list', {
            'clients': unique_clients,
            'order': _get_client_order(),
            'timestamp': int(time.time() * 1000),
            'total': len(unique_clients)
        })
        
        logger.debug(f"[WebSocket] ✅ Lista de clientes enviada: {len(unique_clients)} activos")
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en get_clients: {e}")
        emit('error', {'message': str(e)})


@socketio.on('set_client_order')
def handle_set_client_order(data):
    """✅ NUEVO: Setear orden global de clientes para TODOS los navegadores."""
    update_client_activity(request.sid)

    try:
        if not channel_manager:
            emit('error', {'message': 'Channel manager not available'})
            return

        order = (data or {}).get('order')

        known = []
        device_registry = getattr(channel_manager, 'device_registry', None)
        if device_registry:
            # Todos los devices conocidos (activos o no)
            for d in device_registry.get_all_devices(active_only=False):
                u = d.get('uuid')
                if u:
                    known.append(u)
        else:
            # Fallback: solo los que están activos
            for c in channel_manager.get_all_clients_info():
                u = c.get('device_uuid') or c.get('id')
                if u:
                    known.append(u)

        final_order = _set_client_order(order, known)

        emit('client_order_saved', {
            'status': 'ok',
            'order': final_order,
            'timestamp': int(time.time() * 1000)
        })

        broadcast_clients_update()

    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en set_client_order: {e}")
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
        
        # Resolver: puede venir client_id (runtime) o directamente device_uuid
        subscription = channel_manager.get_client_subscription(client_id)

        resolved_client_id = client_id
        resolved_device_uuid = None

        if subscription:
            resolved_device_uuid = subscription.get('device_uuid')
        else:
            # Intentar mapear device_uuid -> client_id activo
            try:
                mapped_client_id = None
                if hasattr(channel_manager, 'get_client_by_device_uuid'):
                    mapped_client_id = channel_manager.get_client_by_device_uuid(client_id)
                if mapped_client_id:
                    resolved_client_id = mapped_client_id
                    subscription = channel_manager.get_client_subscription(mapped_client_id)
                    if subscription:
                        resolved_device_uuid = subscription.get('device_uuid')
            except Exception:
                pass

        # Permitir renombrar dispositivo aunque no esté conectado: asumir device_uuid
        if not resolved_device_uuid:
            resolved_device_uuid = client_id

        # Guardar nombre personalizado en device_registry
        if hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
            success = channel_manager.device_registry.set_custom_name(resolved_device_uuid, custom_name)
            if success:
                logger.info(f"[WebSocket] 📝 Nombre personalizado guardado: {str(resolved_device_uuid)[:12]} = {custom_name}")
                emit('client_name_saved', {
                    'client_id': resolved_client_id,
                    'device_uuid': resolved_device_uuid,
                    'custom_name': custom_name,
                    'status': 'ok'
                })
                
                # Notificar a todos los clientes de la actualización
                broadcast_clients_update()
            else:
                emit('error', {'message': 'Failed to save custom name'})
        else:
            emit('error', {'message': 'Device registry not available'})
    
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en set_client_name: {e}")
        emit('error', {'message': str(e)})


@socketio.on('update_gain')
def handle_update_gain(data):
    """
    ✅ OPTIMIZADO + SINCRONIZADO: Actualizar ganancia (respuesta inmediata + sync a Android/otros web)
    data: {
        'channel': int,
        'gain': float,
        'target_client_id': str (opcional, si no viene usa cliente actual)
    }
    """
    client_id = data.get('target_client_id') or request.sid
    update_client_activity(request.sid)
    
    if not channel_manager:
        emit('gain_updated', {'status': 'error', 'channel': data.get('channel')})
        return
    
    try:
        channel = data.get('channel')
        gain = data.get('gain')
        
        if channel is None or gain is None:
            return
        
        channel = int(channel)
        gain = float(gain)
        
        # ✅ Actualizar en channel manager (respuesta INMEDIATA)
        if client_id in channel_manager.subscriptions:
            channel_manager.update_client_mix(
                client_id,
                gains={channel: gain},
            )
            
            # ✅ Respuesta inmediata al cliente que solicitó
            emit('gain_updated', {
                'channel': channel,
                'gain': gain,
                'client_id': client_id,
                'timestamp': int(time.time() * 1000)
            }, to=request.sid)
            
            # ✅ SINCRONIZACIÓN BIDIRECCIONAL: Propagar a OTROS clientes web (broadcast)
            socketio.emit('param_sync', {
                'type': 'gain',
                'channel': channel,
                'value': gain,
                'client_id': client_id,
                'source': 'web',
                'timestamp': int(time.time() * 1000)
            }, skip_sid=request.sid)  # No enviar al que ya lo cambió
            
            # ✅ SINCRONIZACIÓN A ANDROID: Empujar estado al cliente nativo objetivo
            try:
                subscription = channel_manager.get_client_subscription(client_id)
                if subscription and subscription.get('client_type') == 'native':
                    if native_server_instance is not None:
                        native_server_instance.push_mix_state_to_client(client_id)
            except Exception as e:
                if config.DEBUG:
                    logger.debug(f"[WebSocket] Android sync failed: {e}")
            
            # ✅ NUEVO: Guardar estado de canales para persistencia
            _save_client_config_to_registry(client_id)
            
            # Broadcast para actualizar estado en todos los clientes web
            broadcast_clients_update()
            
            if config.DEBUG:
                logger.debug(f"[WebSocket] ⚡ Gain CH{channel}: {gain:.2f} ({client_id[:8]}) [synced]")
    
    except Exception as e:
        if config.DEBUG:
            logger.error(f"[WebSocket] Error update_gain: {e}")
        emit('gain_updated', {'status': 'error', 'channel': data.get('channel')})


@socketio.on('update_pan')
def handle_update_pan(data):
    """
    ✅ OPTIMIZADO + SINCRONIZADO: Actualizar panorama (respuesta inmediata + sync a Android/otros web)
    data: {
        'channel': int,
        'pan': float (-1.0 a 1.0),
        'target_client_id': str (opcional, si no viene usa cliente actual)
    }
    """
    client_id = data.get('target_client_id') or request.sid
    update_client_activity(request.sid)
    
    if not channel_manager:
        emit('pan_updated', {'status': 'error', 'channel': data.get('channel')})
        return
    
    try:
        channel = data.get('channel')
        pan = data.get('pan')
        
        if channel is None or pan is None:
            return
        
        channel = int(channel)
        pan = float(pan)
        
        # ✅ Actualizar en channel manager (respuesta INMEDIATA)
        if client_id in channel_manager.subscriptions:
            channel_manager.update_client_mix(
                client_id,
                pans={channel: pan},
            )
            
            # ✅ Respuesta inmediata al cliente que solicitó
            emit('pan_updated', {
                'channel': channel,
                'pan': pan,
                'client_id': client_id,
                'timestamp': int(time.time() * 1000)
            }, to=request.sid)
            
            # ✅ SINCRONIZACIÓN BIDIRECCIONAL: Propagar a OTROS clientes web (broadcast)
            socketio.emit('param_sync', {
                'type': 'pan',
                'channel': channel,
                'value': pan,
                'client_id': client_id,
                'source': 'web',
                'timestamp': int(time.time() * 1000)
            }, skip_sid=request.sid)  # No enviar al que ya lo cambió
            
            # ✅ SINCRONIZACIÓN A ANDROID: Empujar estado al cliente nativo objetivo
            try:
                subscription = channel_manager.get_client_subscription(client_id)
                if subscription and subscription.get('client_type') == 'native':
                    if native_server_instance is not None:
                        native_server_instance.push_mix_state_to_client(client_id)
            except Exception as e:
                if config.DEBUG:
                    logger.debug(f"[WebSocket] Android sync failed: {e}")
            
            # ✅ NUEVO: Guardar estado de canales para persistencia
            _save_client_config_to_registry(client_id)
            
            # Broadcast para actualizar estado en todos los clientes web
            broadcast_clients_update()
            
            if config.DEBUG:
                logger.debug(f"[WebSocket] ⚡ Pan CH{channel}: {pan:.2f} ({client_id[:8]}) [synced]")
    
    except Exception as e:
        if config.DEBUG:
            logger.error(f"[WebSocket] Error update_pan: {e}")
        emit('pan_updated', {'status': 'error', 'channel': data.get('channel')})


@socketio.on('toggle_mute')
def handle_toggle_mute(data):
    """
    ✅ NUEVO: Toggle mute de un canal (respuesta ultra-rápida)
    data: {
        'channel': int,
        'muted': bool,
        'target_client_id': str (opcional)
    }
    """
    client_id = data.get('target_client_id') or request.sid
    update_client_activity(request.sid)
    
    if not channel_manager:
        emit('mute_toggled', {'status': 'error', 'channel': data.get('channel')})
        return
    
    try:
        channel = data.get('channel')
        muted = bool(data.get('muted', False))
        
        if channel is None:
            return
        
        channel = int(channel)
        
        # ✅ Actualizar en channel manager (respuesta INMEDIATA)
        if client_id in channel_manager.subscriptions:
            channel_manager.update_client_mix(
                client_id,
                mutes={channel: muted},
            )
            
            # ✅ Respuesta inmediata al cliente que solicitó
            emit('mute_toggled', {
                'channel': channel,
                'muted': muted,
                'client_id': client_id,
                'timestamp': int(time.time() * 1000)
            }, to=request.sid)
            
            # ✅ SINCRONIZACIÓN BIDIRECCIONAL: Propagar a OTROS clientes web
            socketio.emit('param_sync', {
                'type': 'mute',
                'channel': channel,
                'value': muted,
                'client_id': client_id,
                'source': 'web',
                'timestamp': int(time.time() * 1000)
            }, skip_sid=request.sid)
            
            # ✅ SINCRONIZACIÓN A ANDROID: Enviar mix_state al cliente nativo objetivo
            try:
                subscription = channel_manager.get_client_subscription(client_id)
                if subscription and subscription.get('client_type') == 'native':
                    if native_server_instance is not None:
                        native_server_instance.push_mix_state_to_client(client_id)
            except Exception as e:
                if config.DEBUG:
                    logger.debug(f"[WebSocket] Android sync failed: {e}")
            
            # ✅ NUEVO: Guardar estado de canales para persistencia
            _save_client_config_to_registry(client_id)
            
            # Broadcast para actualizar estado en todos los clientes web
            broadcast_clients_update()
            
            if config.DEBUG:
                logger.debug(f"[WebSocket] 🔇 Mute CH{channel}: {muted} ({client_id[:8]}) [synced]")
    
    except Exception as e:
        if config.DEBUG:
            logger.error(f"[WebSocket] Error toggle_mute: {e}")
        emit('mute_toggled', {'status': 'error', 'channel': data.get('channel')})


def validate_channels(channels, operational_channels):
    """✅ NUEVO: Validar canales contra los operacionales"""
    if not channels:
        return []
    try:
        channels = [int(ch) for ch in channels]
    except (ValueError, TypeError):
        return []
    
    valid = [ch for ch in channels if ch in operational_channels]
    invalid = set(channels) - set(valid)
    if invalid:
        logger.warning(f"[WebSocket] ⚠️ Canales inválidos ignorados: {invalid}")
    return valid


@socketio.on('sync_to_android')
def handle_sync_to_android(data):
    """
    ✅ NUEVO: Sincronizar cambios web → Android
    data: {
        'target_client_id': str,
        'type': 'gain'|'pan'|'channel_toggle'|'mute',
        'channel': int,
        'value': float|bool
    }
    """
    if not channel_manager or not native_server_instance:
        return
    
    update_client_activity(request.sid)
    
    try:
        target_client_id = data.get('target_client_id')
        sync_type = data.get('type')
        channel = int(data.get('channel', -1))
        value = data.get('value')
        
        if not target_client_id or sync_type is None:
            return
        
        # Obtener suscripción del cliente
        subscription = channel_manager.get_client_subscription(target_client_id)
        if not subscription:
            return
        
        # Validar canal contra operacionales
        operational = channel_manager.get_operational_channels()
        if channel not in operational:
            logger.warning(f"[WebSocket] ⚠️ Canal {channel} no operacional")
            return
        
        # Registrar cambio específico
        if sync_type == 'gain':
            if not subscription.get('gains'):
                subscription['gains'] = {}
            subscription['gains'][channel] = float(value)
            logger.debug(f"[WebSocket] 📊 Sync Web→Android: gain ch{channel}={value:.2f}")
        
        elif sync_type == 'pan':
            if not subscription.get('pans'):
                subscription['pans'] = {}
            subscription['pans'][channel] = float(value)
            logger.debug(f"[WebSocket] 📊 Sync Web→Android: pan ch{channel}={value:.2f}")
        
        elif sync_type == 'channel_toggle':
            channels = subscription.get('channels', [])
            if bool(value):
                if channel not in channels:
                    channels.append(channel)
            else:
                if channel in channels:
                    channels.remove(channel)
            subscription['channels'] = channels
            logger.debug(f"[WebSocket] 📊 Sync Web→Android: ch{channel} toggle={value}")
        
        elif sync_type == 'mute':
            if not subscription.get('mutes'):
                subscription['mutes'] = {}
            subscription['mutes'][channel] = bool(value)
            logger.debug(f"[WebSocket] 📊 Sync Web→Android: mute ch{channel}={value}")
        
        # Empujar estado al cliente nativo si está conectado
        if subscription.get('client_type') == 'native':
            try:
                if native_server_instance:
                    native_server_instance.push_mix_state_to_client(target_client_id)
            except Exception as e:
                logger.debug(f"[WebSocket] Error empujando estado a Android: {e}")
        
        emit('sync_complete', {'status': 'ok', 'type': sync_type})
    
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en sync_to_android: {e}")
        emit('sync_error', {'message': str(e)})


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
    ✅ NUEVO: Heartbeat explícito de cliente web (respuesta ultra-rápida)
    Los clientes web envían esto cada 3 segundos para confirmar conexión activa
    """
    client_id = request.sid
    update_client_activity(client_id)
    # ✅ Respuesta inmediata sin procesar
    emit('heartbeat_ack', {
        'client_id': client_id[:8],
        'server_timestamp': int(time.time() * 1000),
        'client_timestamp': data.get('timestamp', 0) if isinstance(data, dict) else 0,
        'status': 'alive'
    })


# ============================================================================
# EVENTOS SOCKETIO - CLIENTE MAESTRO (AUDIO STREAMING)
# ============================================================================

@socketio.on('start_master_audio')
def handle_start_master_audio():
    """
    ✅ NUEVO: Iniciar recepción de audio del cliente maestro
    El cliente web solicita recibir el stream de audio del maestro
    """
    client_id = request.sid
    update_client_activity(client_id)

    if not getattr(config, 'MASTER_CLIENT_ENABLED', False) or not getattr(config, 'WEB_AUDIO_STREAM_ENABLED', False):
        emit('error', {'message': 'Master client disabled'})
        return
    
    if not channel_manager:
        emit('error', {'message': 'Channel manager not available'})
        return
    
    try:
        # Verificar que el cliente maestro existe
        master_id = channel_manager.get_master_client_id()
        if not master_id:
            emit('error', {'message': 'Master client not enabled'})
            return
        
        # Registrar como listener
        register_master_audio_listener(client_id)
        
        # Enviar confirmación con información del stream
        emit('master_audio_started', {
            'master_client_id': master_id,
            'sample_rate': config.SAMPLE_RATE,
            'buffer_size': getattr(config, 'WEB_AUDIO_BUFFER_SIZE', 2048),
            'channels': 2,  # Siempre stereo para el master
            'status': 'streaming',
            'timestamp': int(time.time() * 1000)
        })
        
        logger.info(f"[WebSocket] 🎧 Cliente {client_id[:8]} inició stream de audio maestro")
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en start_master_audio: {e}")
        emit('error', {'message': str(e)})


@socketio.on('stop_master_audio')
def handle_stop_master_audio():
    """
    ✅ NUEVO: Detener recepción de audio del cliente maestro
    """
    client_id = request.sid
    update_client_activity(client_id)
    
    try:
        unregister_master_audio_listener(client_id)
        
        emit('master_audio_stopped', {
            'status': 'stopped',
            'timestamp': int(time.time() * 1000)
        })
        
        logger.info(f"[WebSocket] 🎧 Cliente {client_id[:8]} detuvo stream de audio maestro")
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en stop_master_audio: {e}")


@socketio.on('get_master_client_info')
def handle_get_master_client_info():
    """
    ✅ NUEVO: Obtener información del cliente maestro
    """
    update_client_activity(request.sid)
    
    if not channel_manager:
        emit('error', {'message': 'Channel manager not available'})
        return

    if not getattr(config, 'MASTER_CLIENT_ENABLED', False):
        emit('master_client_info', {
            'enabled': False,
            'message': 'Master client disabled'
        })
        return
    
    try:
        master_id = channel_manager.get_master_client_id()
        if not master_id:
            emit('master_client_info', {
                'enabled': False,
                'message': 'Master client not enabled'
            })
            return
        
        subscription = channel_manager.get_client_subscription(master_id)
        
        emit('master_client_info', {
            'enabled': True,
            'master_client_id': master_id,
            'name': getattr(config, 'MASTER_CLIENT_NAME', 'Control'),
            'channels': subscription.get('channels', []) if subscription else [],
            'sample_rate': config.SAMPLE_RATE,
            'buffer_size': getattr(config, 'WEB_AUDIO_BUFFER_SIZE', 2048),
            'streaming_available': getattr(config, 'WEB_AUDIO_STREAM_ENABLED', True),
            'timestamp': int(time.time() * 1000)
        })
        
    except Exception as e:
        logger.error(f"[WebSocket] ❌ Error en get_master_client_info: {e}")


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
    ✅ NUEVO: Guardar estado de canales de cliente de forma permanente
    Persiste ganancia, pan, canales activos y mutes para restauración en reinicio
    """
    try:
        if not channel_manager:
            return
        
        subscription = channel_manager.get_client_subscription(client_id)
        if not subscription:
            return

        # ✅ Clave estable para persistencia (evita guardar por SID efímero)
        persistent_key = subscription.get('device_uuid') or client_id
        
        # ✅ NUEVO: Guardar en channels_state para persistencia global
        state_to_save = {
            'channels': subscription.get('channels', []),
            'gains': subscription.get('gains', {}),
            'pans': subscription.get('pans', {}),
            'mutes': subscription.get('mutes', {}),
            'solos': list(subscription.get('solos', set())),
            'master_gain': subscription.get('master_gain', 1.0),
            'timestamp': int(time.time() * 1000)
        }
        
        # Guardar en device_registry
        if hasattr(channel_manager, 'device_registry') and channel_manager.device_registry:
            channel_manager.device_registry.update_channels_state(persistent_key, state_to_save)
            logger.debug(f"[WebSocket] 💾 Estado de canales guardado para {str(persistent_key)[:12]}")
        
        # ✅ CONFIGURACIÓN DE SESIÓN: No guardar en device_registry (deshabilitado)
        if False:  # DISABLED FOR SESSION-ONLY CONFIG
            pass
            
    except Exception as e:
        logger.debug(f"[WebSocket] Error guardando estado de canales: {e}")


def get_all_clients_info():
    """
    ✅ Obtener información de clientes ACTIVOS para mostrar en web
    ✅ FILTRO ESTRICTO: Solo mostrar:
       1. Cliente maestro (servidor - monitor sonidista) si está habilitado
       2. Clientes Android nativos ACTIVOS CONECTADOS (con conexión real)
    ✅ NO mostrar: 
       - Clientes web (solo aplicaciones nativas)
       - Clientes inactivos/fantasmas (sin actividad reciente)
       - Clientes que nunca se han conectado
    """
    result_clients = []
    current_time = time.time()
    activity_timeout = 10.0  # 10 segundos sin actividad = considerado desconectado
    
    if channel_manager:
        try:
            all_info = channel_manager.get_all_clients_info()
            device_registry = getattr(channel_manager, 'device_registry', None)
            for c in all_info:
                client_type = c.get('type', 'unknown')
                is_master = c.get('is_master', False)
                is_connected = c.get('connected', False)
                last_activity = c.get('last_activity', 0)
                device_uuid = c.get('device_uuid')
                # Verificar activo en DeviceRegistry
                is_active_registry = True
                if device_registry and device_uuid:
                    dev = device_registry.get_device(device_uuid)
                    is_active_registry = dev.get('active', False) if dev else False

                # ✅ MOSTRAR: Cliente maestro si está habilitado
                if is_master:
                    if getattr(config, 'MASTER_CLIENT_ENABLED', False):
                        result_clients.append(c)
                    continue

                # ✅ MOSTRAR: Clientes native/android SOLO si:
                #   1. Están marcados como conectados
                #   2. Tienen actividad reciente (últimos 3 minutos)
                #   3. Están activos en DeviceRegistry
                if client_type in ('native', 'android'):
                    if is_connected and (current_time - last_activity) < activity_timeout and is_active_registry:
                        result_clients.append(c)
                        logger.debug(f"[WebSocket] ✅ Cliente activo mostrado: {c.get('id', 'unknown')[:12]} "
                                   f"(tipo: {client_type}, actividad: {current_time - last_activity:.1f}s, registry: {is_active_registry})")
                    else:
                        reason = "desconectado" if not is_connected else (f"inactivo ({current_time - last_activity:.1f}s)" if (current_time - last_activity) >= activity_timeout else "no activo en registry")
                        logger.debug(f"[WebSocket] ⊘ Cliente ignorado ({reason}): {c.get('id', 'unknown')[:12]} "
                                   f"(tipo: {client_type}, registry: {is_active_registry})")
                    continue
                # ✅ NO mostrar otros tipos (web, etc)
        except Exception as e:
            logger.error(f"[WebSocket] Error obteniendo clientes activos: {e}")

    # ✅ Deduplicar por device_uuid para evitar duplicados
    seen_uuids = set()
    deduped_clients = []
    
    for client in result_clients:
        uuid = client.get('device_uuid') or client.get('id')
        if uuid and uuid not in seen_uuids:
            seen_uuids.add(uuid)
            deduped_clients.append(client)
        elif uuid:
            logger.debug(f"[WebSocket] ⚠️ Cliente duplicado filtrado: {uuid[:12]}")
    
    # ✅ Orden final: Maestro primero, luego Android nativos ordenados por actividad
    master_clients = [c for c in deduped_clients if c.get('is_master', False)]
    other_clients = [c for c in deduped_clients if not c.get('is_master', False)]
    
    # Ordenar Android nativos por actividad reciente (más reciente primero)
    other_clients.sort(key=lambda c: -(c.get('last_activity') or 0))
    
    final_result = master_clients + other_clients
    
    logger.debug(f"[WebSocket] 📊 Lista de clientes activos: {len(final_result)} "
               f"(maestro: {len(master_clients)}, nativos: {len(other_clients)})")
    
    return final_result


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
    """
    ✅ Optimización de la actualización de clientes.
    ✅ MEJORADO: Deduplicación automática y validación de clientes activos
    """
    try:
        clients_info = get_all_clients_info()
        
        # ✅ NUEVO: Deduplicar antes de enviar (por si acaso hay duplicados)
        seen_ids = set()
        unique_clients = []
        
        for client in clients_info:
            client_id = client.get('id')
            if client_id not in seen_ids:
                seen_ids.add(client_id)
                unique_clients.append(client)
            else:
                logger.warning(f"[WebSocket] ⚠️ Duplicado detectado en broadcast: {client_id[:12]}")
        
        socketio.emit('clients_update', {
            'clients': unique_clients,
            'order': _get_client_order(),
            'timestamp': int(time.time() * 1000),
            'count': len(unique_clients)
        })
        
        if len(unique_clients) != len(clients_info):
            logger.warning(f"[WebSocket] ⚠️ Se filtraron {len(clients_info) - len(unique_clients)} duplicados")
        
        logger.info(f"[WebSocket] 📡 Actualización enviada: {len(unique_clients)} clientes activos")
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
            time.sleep(3)  # ✅ Reducido de 5s a 3s para detección más rápida
            try:
                current_time = time.time()
                timeout = 10.0  # 10 segundos sin actividad

                with web_clients_lock:
                    inactive_clients = []
                    web_clients_snapshot = list(web_clients.items())
                    
                    for client_id, info in web_clients_snapshot:
                        last_activity = info.get('last_activity', 0)
                        if current_time - last_activity > timeout:
                            inactive_clients.append((client_id, info))

                    if inactive_clients:
                        logger.info(f"[WebSocket] 🧹 Limpiando {len(inactive_clients)} clientes web inactivos")
                        for client_id, info in inactive_clients:
                            # Marcar como inactivo en DeviceRegistry si existe device_uuid
                            device_uuid = info.get('device_uuid')
                            if device_uuid and getattr(channel_manager, 'device_registry', None):
                                try:
                                    channel_manager.device_registry.mark_inactive(device_uuid)
                                    logger.info(f"[WebSocket] 📌 Dispositivo marcado inactivo: {device_uuid[:12]}")
                                except Exception as e:
                                    logger.debug(f"[WebSocket] Error marcando inactivo en DeviceRegistry: {e}")

                            if client_id in web_clients:
                                web_clients.pop(client_id, None)
                            # Desuscribir del channel manager
                            if channel_manager:
                                try:
                                    channel_manager.unsubscribe_client(client_id)
                                except Exception:
                                    pass
                            # Desconectar socket
                            try:
                                disconnect(sid=client_id)
                            except:
                                pass

                # Limpiar clientes nativos desconectados del channel_manager
                if channel_manager:
                    try:
                        device_registry = getattr(channel_manager, 'device_registry', None)
                        subscriptions_snapshot = list(channel_manager.subscriptions.items())
                        
                        for client_id, sub in subscriptions_snapshot:
                            client_type = channel_manager.client_types.get(client_id, "unknown")
                            # Si es nativo, verificar que está activo en DeviceRegistry
                            if client_type in ("native", "android"):
                                device_uuid = sub.get('device_uuid')
                                if device_uuid and device_registry:
                                    dev = device_registry.get_device(device_uuid)
                                    # Si no existe o no está activo, eliminar
                                    if not dev or not dev.get('active', False):
                                        logger.info(f"[WebSocket] 🧹 Eliminando cliente nativo inactivo: {client_id[:12]} (uuid: {device_uuid[:12]})")
                                        if client_id in channel_manager.subscriptions:
                                            channel_manager.unsubscribe_client(client_id)
                    except Exception as e:
                        logger.debug(f"[WebSocket] Error limpiando nativos inactivos: {e}")

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