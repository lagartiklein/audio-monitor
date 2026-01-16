# config.py - ACTUALIZADO CON SOPORTE DE 64 CANALES

# ============================================================================
# ✅ NUEVO: CONFIGURACIÓN DE TIMEOUTS Y TOLERANCIA PARA SUSCRIPCIONES
# ============================================================================

# Timeouts críticos para evitar reinicios al suscribir
SOCKET_READ_TIMEOUT = 5.0  # Aumentado de 2s para mensajes grandes
CLIENT_ALIVE_TIMEOUT = 60.0  # Aumentado de 30s para actividad general
CLIENT_BUFFER_GRACE = 90.0  # Aumentado de 30s para buffers llenos temporales
MAX_MAGIC_ERRORS = 10  # Aumentado de 3 para tolerar más errores de corrupción
MAX_SEND_FAILURES = 20  # Aumentado de 10 para suscripciones grandes
ZOMBIE_CHECK_TIMEOUT = 15.0  # Aumentado de 1s para detección zombie menos agresiva

# Máximo número de canales lógicos soportados
# Hardware típico: 8, 16, 24, 32, 48, 64 canales
# Protocolo soporta: hasta 64 canales (usando 64-bit channel_mask)
MAX_LOGICAL_CHANNELS = 64

# Mapeo automático de dispositivos
# Si un dispositivo tiene >2 canales, se registra automáticamente
MIN_CHANNELS_REQUIRE_MAPPING = 2

# Advertencia si se intenta usar más canales
WARN_CHANNELS_ABOVE = 64

# Descripción de canales por tipo de interfaz (para UI)
CHANNEL_LABELS = {
    8: ["In 1", "In 2", "In 3", "In 4", "In 5", "In 6", "In 7", "In 8"],
    16: [f"In {i+1}" for i in range(16)],
    24: [f"In {i+1}" for i in range(24)],
    32: [f"In {i+1}" for i in range(32)],
    48: [f"In {i+1}" for i in range(48)],
    64: [f"In {i+1}" for i in range(64)],
}

# ============================================================================
# CONFIGURACIÓN DE AUDIO EXISTENTE
# ============================================================================

DEFAULT_SAMPLE_RATE = 48000
SAMPLE_RATE = DEFAULT_SAMPLE_RATE
BLOCKSIZE = 120
DEFAULT_NUM_CHANNELS = 2  # Solo fallback; se usa el conteo real del dispositivo
FORCE_MONO_CAPTURE = False

# ============================================================================
# CONFIGURACIÓN DE WEBSOCKET
# ============================================================================

WEBSOCKET_PARAM_DEBOUNCE_MS = 50
WEBSOCKET_BATCH_UPDATES = True
WEBSOCKET_LATENCY_LOG = False
WEBSOCKET_QUICK_RESPONSE = True
SEND_QUEUE_SIZE = 8
SEND_THREAD_COUNT = 1
AUDIO_SEND_POOL_SIZE = 6
QUEUE_SIZE = 0
NATIVE_QUEUE_SIZE = 0
WEB_QUEUE_SIZE = 2

WEB_PORT = 5100
WEB_HOST = '0.0.0.0'
NATIVE_PORT = 5101
NATIVE_HOST = '0.0.0.0'
NATIVE_MAX_CLIENTS = 10

WEB_HEARTBEAT_TIMEOUT = 60
NATIVE_HEARTBEAT_TIMEOUT = 120

# ============================================================================
# CONFIGURACIÓN DE AUDIO
# ============================================================================

VU_UPDATE_INTERVAL = 100
VU_PEAK_DECAY = 0.95
VU_ENABLED = False  # âš ï¸ DESACTIVADO para ultra-baja latencia

SOCKET_SNDBUF = 4096   # âœ… 8 packets máximo (~5ms)
SOCKET_RCVBUF = 4096   # âœ… Simétrico
SOCKET_NODELAY = True
SOCKET_TIMEOUT = 0.010  # âœ… 10ms (15 packets)

TCP_KEEPALIVE = True
TCP_KEEPIDLE = 10
TCP_KEEPINTVL = 5
TCP_KEEPCNT = 3

# ============================================================================
# CONFIGURACIÓN RF (AUDIO NATIVO)
# ============================================================================

RF_AUTO_RECONNECT = True
RF_RECONNECT_DELAY_MS = 1000
RF_MAX_RECONNECT_DELAY_MS = 8000
RF_RECONNECT_BACKOFF = 1.5
RF_STATE_CACHE_TIMEOUT = 0  # âœ… 0 = no expira (persiste hasta reiniciar servidor)
RF_MAX_RECONNECT_ATTEMPTS = 10
RF_MAX_PERSISTENT_STATES = 50

CLIENT_ALIVE_TIMEOUT = 60.0  # ✅ AUMENTADO: 15s → 60s para tolerar suscripciones lentas
CLIENT_MAX_CONSECUTIVE_FAILURES = 20  # ✅ AUMENTADO: 5 → 20 para suscripciones grandes
MAINTENANCE_INTERVAL = 5.0

NATIVE_HEARTBEAT_INTERVAL = 5000  # âš ï¸ AUMENTADO: 3s → 5s
NATIVE_HEARTBEAT_TIMEOUT = 60

# ============================================================================
# DEPURACIÓN Y LOGGING
# ============================================================================

DEBUG = False  # ✅ Desactivado para mejor rendimiento en producción
LOG_QUEUE_STATS = False
LOG_LEVEL = 'WARNING'  # ✅ Reducido de DEBUG para mejor rendimiento
STATS_INTERVAL = 10.0

VALIDATE_PACKETS = False  # ✅ Mantenido desactivado para rendimiento
VALIDATE_AUDIO = False

# ============================================================================
# OPTIMIZACIONES
# ============================================================================

USE_INT16_ENCODING = False
AUDIO_THREAD_PRIORITY = True
CPU_AFFINITY = None
USE_MEMORYVIEW = True
WEB_COMPRESSION = False
WEB_ASYNC_SEND = True
WEB_MAX_WORKERS = 4
WEB_BINARY_MODE = True

# ============================================================================
# COMPRESIÓN DE AUDIO
# ============================================================================

AUDIO_COMPRESSION_ENABLED = True  # âœ… Opus activado - ~90% reducción de ancho de banda
AUDIO_COMPRESSION_BITRATE = 32000  # Bitrate para Opus (baja latencia)

MAX_CHANNELS_PER_CLIENT = 128
MAX_GAIN_VALUE = 10.0
MAX_MASTER_GAIN = 5.0

AUDIO_BUFFER_POOL_SIZE = 10
MAX_CONCURRENT_SENDS = 4

# ============================================================================
# CLIENTE MAESTRO (MASTER CLIENT)
# ============================================================================

USE_AUDIO_WORKLET = False
MASTER_CLIENT_ENABLED = False
MASTER_CLIENT_UUID = "__master_server_client__"
MASTER_CLIENT_NAME = "Control"
MASTER_CLIENT_DEFAULT_CHANNELS = []
WEB_AUDIO_BUFFER_SIZE = 2048
WEB_AUDIO_STREAM_ENABLED = False