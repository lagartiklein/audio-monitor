# config.py
# ⚡ CONFIGURACIÓN ULTRA-BAJA LATENCIA RF + WEB - FASE 3 OPTIMIZADA
# ✅ Prevención de saturación WiFi y fugas de memoria

# ============================================================================
# AUDIO CORE
# ============================================================================
DEFAULT_SAMPLE_RATE = 48000
SAMPLE_RATE = DEFAULT_SAMPLE_RATE

# ✅ FASE 4: BLOCKSIZE ultra-reducido para baja latencia
# 512 samples @ 48kHz ≈ 10.67ms latencia; mejor balance entre latencia y CPU
BLOCKSIZE = 32

# ✅ COMPRESIÓN DE AUDIO: Solo zlib habilitado
ENABLE_OPUS_COMPRESSION = False  # Opus deshabilitado, solo zlib
OPUS_BITRATE = 32  # (Ignorado, solo para compatibilidad)

# ✅ CANALES POR DEFECTO
DEFAULT_NUM_CHANNELS = 2  # Solo fallback; se usa el conteo real del dispositivo

# ✅ MODO MONO ULTRA-BAJA LATENCIA
# Captura solo el primer canal y transmite en mono; el renderer nativo se encarga del estéreo
FORCE_MONO_CAPTURE = False

# ============================================================================
# ✅ OPTIMIZACIONES DE LATENCIA WEB - NUEVO
# ============================================================================
# Debouncing de cambios frecuentes (faders, pan, etc.)
WEBSOCKET_PARAM_DEBOUNCE_MS = 50  # Agrupar cambios dentro de 50ms
WEBSOCKET_BATCH_UPDATES = True      # Enviar cambios en lotes
WEBSOCKET_LATENCY_LOG = False       # Log detallado de latencias

# ✅ Formato de respuesta rápida
WEBSOCKET_QUICK_RESPONSE = True  # Respuesta inmediata sin broadcast completo

# ============================================================================
# ✅ FASE 2: CONFIGURACIÓN ASYNC SEND
# ============================================================================
SEND_QUEUE_SIZE = 8          # Máximo 8 paquetes encolados por cliente
SEND_THREAD_COUNT = 1        # 1 hilo de envío por cliente

# ============================================================================
# ✅ OPTIMIZACIÓN: ThreadPoolExecutor para envío paralelo de audio
# ============================================================================
# Número de hilos para enviar audio paralelo a múltiples clientes Android/nativos
# Con 10 clientes y 16 canales c/u, usar 4-6 hilos evita saturar el hilo de captura
# Por defecto: min(10, max(4, num_cpus))
AUDIO_SEND_POOL_SIZE = 6  # Hilos de envío paralelo (ajusta según tu CPU)

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
WEB_HEARTBEAT_TIMEOUT = 60
NATIVE_HEARTBEAT_TIMEOUT = 120

# 🎚️ CONFIGURACIÓN VU METERS
# ============================================================================
VU_UPDATE_INTERVAL = 100
VU_PEAK_DECAY = 0.95
VU_ENABLED = False  # ⚠️ DESACTIVADO para ultra-baja latencia

# ============================================================================
# ✅ OPTIMIZACIONES DE SOCKET - FIXED
# ============================================================================
SOCKET_SNDBUF = 4096   # ✅ 8 packets máximo (~5ms)
SOCKET_RCVBUF = 4096   # ✅ Simétrico
SOCKET_NODELAY = True
SOCKET_TIMEOUT = 0.010  # ✅ 10ms (15 packets)
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
CLIENT_ALIVE_TIMEOUT = 15.0  # ⚠️ REDUCIDO: 30s → 15s para detección más rápida
CLIENT_MAX_CONSECUTIVE_FAILURES = 5  # Fallos de envío antes de desconectar
MAINTENANCE_INTERVAL = 5.0  # ⚠️ REDUCIDO: 10s → 5s para limpieza más frecuente

# ============================================================================
# NATIVE HEARTBEAT - OPTIMIZADO
# ============================================================================
NATIVE_HEARTBEAT_INTERVAL = 5000  # ⚠️ AUMENTADO: 3s → 5s para procesar menos en servidor
NATIVE_HEARTBEAT_TIMEOUT = 60  # Timeout después de 60 segundos sin respuesta

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
# FORMATO DE AUDIO
# ============================================================================
# Forzar uso de int16 en vez de float32
USE_INT16_ENCODING = True

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
MAX_CHANNELS_PER_CLIENT = 128  # O elimina este límite si no es necesario
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

# ============================================================================
# ✅ CLIENTE MAESTRO (SONIDISTA WEB MONITOR)
# ============================================================================
# El cliente maestro es un cliente especial que:
# - Aparece siempre primero en la lista de clientes
# - Se reproduce vía Web Audio API en el navegador
# - Permite al sonidista monitorear sin interferir con Android
MASTER_CLIENT_ENABLED = False
MASTER_CLIENT_UUID = "__master_server_client__"
MASTER_CLIENT_NAME = "Control"
MASTER_CLIENT_DEFAULT_CHANNELS = []  # Empezar sin canales, el usuario selecciona
WEB_AUDIO_BUFFER_SIZE = 2048  # Buffer para Web Audio (samples)
WEB_AUDIO_STREAM_ENABLED = False  # Desactivado (sin cliente maestro)