# config.py
# ⚡ CONFIGURACIÓN ULTRA-BAJA LATENCIA RF + WEB - FIXED
# ✅ Prevención de saturación WiFi y fugas de memoria

# ============================================================================
# AUDIO CORE
# ============================================================================
DEFAULT_SAMPLE_RATE = 48000
SAMPLE_RATE = DEFAULT_SAMPLE_RATE
BLOCKSIZE = 128  # ✅ ~2.67ms latencia mínima

# ============================================================================
# ✅ FORMATO DE AUDIO
# ============================================================================
USE_INT16_ENCODING = True   # ✅ True = -50% datos, False = Float32 original

# ============================================================================
# COLAS (MaaDO DIRECTO PARA RF)
# ============================================================================
QUEUE_SIZE = 0
NATIVE_QUEUE_SIZE = 0
WEB_QUEUE_SIZE = 2

# ============================================================================
# RED
# ============================================================================
WEB_PORT = 5100
WEB_HOST = '0.0.0.0'
NATIVE_PORT = 5101
NATIVE_HOST = '0.0.0.0'
NATIVE_MAX_CLIENTS = 10

# 🎚️ CONFIGURACIÓN VU METERS
# ============================================================================
VU_UPDATE_INTERVAL = 100
VU_PEAK_DECAY = 0.95

# ============================================================================
# ✅ OPTIMIZACIONES DE SOCKET - FIXED
# ============================================================================
SOCKET_SNDBUF = 65536
SOCKET_RCVBUF = 32768
SOCKET_NODELAY = True
SOCKET_TIMEOUT = 5.0  # ✅ REDUCIDO: 5s (era 30s) para detectar zombies rápido

# TCP Keepalive (más agresivo para detectar clientes muertos)
TCP_KEEPALIVE = True
TCP_KEEPIDLE = 10
TCP_KEEPINTVL = 5
TCP_KEEPCNT = 3

# ============================================================================
# ✅ RF MODE - AUTO-RECONEXIÓN Y PERSISTENCIA - FIXED
# ============================================================================
RF_AUTO_RECONNECT = True
RF_RECONNECT_DELAY_MS = 1000
RF_MAX_RECONNECT_DELAY_MS = 8000
RF_RECONNECT_BACKOFF = 1.5
RF_STATE_CACHE_TIMEOUT = 0  # ✅ 0 = no expira (persiste hasta reiniciar servidor)
RF_MAX_RECONNECT_ATTEMPTS = 10
RF_MAX_PERSISTENT_STATES = 50  # ✅ NUEVO: Límite máximo de estados guardados

# ✅ NUEVO: Detección de clientes zombie
CLIENT_ALIVE_TIMEOUT = 30.0  # Segundos sin actividad antes de considerar zombie
CLIENT_MAX_CONSECUTIVE_FAILURES = 5  # Fallos de envío antes de desconectar
MAINTENANCE_INTERVAL = 10.0  # ✅ REDUCIDO: 10s (era 30s) para limpieza frecuente

# ============================================================================
# DEBUG Y LOGS
# ============================================================================
DEBUG = False
LOG_QUEUE_STATS = False
LOG_LEVEL = 'WARNING'
STATS_INTERVAL = 10.0

# ============================================================================
# VALIDACIONES
# ============================================================================
VALIDATE_PACKETS = False
VALIDATE_AUDIO = False

# ============================================================================
# OPTIMIZACIONES DE SISTEMA
# ============================================================================
AUDIO_THREAD_PRIORITY = True
CPU_AFFINITY = None
USE_MEMORYVIEW = True

# ============================================================================
# WEB OPTIMIZATIONS
# ============================================================================
WEB_COMPRESSION = False
WEB_ASYNC_SEND = True
WEB_MAX_WORKERS = 4
WEB_BINARY_MODE = True

# ============================================================================
# SEGURIDAD Y LÍMITES
# ============================================================================
MAX_CHANNELS_PER_CLIENT = 32
MAX_GAIN_VALUE = 10.0
MAX_MASTER_GAIN = 5.0
NATIVE_HEARTBEAT_TIMEOUT = 120
WEB_HEARTBEAT_TIMEOUT = 60

# ============================================================================
# BUFFER SIZES OPTIMIZADOS
# ============================================================================
AUDIO_BUFFER_POOL_SIZE = 10
MAX_CONCURRENT_SENDS = 4

# ============================================================================
# AUDIO WORKLET (No usado en WiFi sin HTTPS)
# ============================================================================
USE_AUDIO_WORKLET = False