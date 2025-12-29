# config.py
# ⚡ CONFIGURACIÓN ULTRA-BAJA LATENCIA RF + WEB
# Optimizado para latencia <5ms en nativo, <15ms en web
# ✅ ACTUALIZADO: Modo RF con auto-reconexión + Int16 encoding

# ============================================================================
# AUDIO CORE
# ============================================================================
DEFAULT_SAMPLE_RATE = 48000
SAMPLE_RATE = DEFAULT_SAMPLE_RATE
BLOCKSIZE = 128  # ✅ ~2.67ms latencia mínima (usa 64 si hay dropouts)

# ============================================================================
# ✅ NUEVO: FORMATO DE AUDIO
# ============================================================================
USE_INT16_ENCODING = True   # ✅ True = -50% datos, False = Float32 original

# ============================================================================
# COLAS (MODO DIRECTO PARA RF)
# ============================================================================
QUEUE_SIZE = 0              # Sin cola default
NATIVE_QUEUE_SIZE = 0       # ✅ RF modo directo (sin buffer)
WEB_QUEUE_SIZE = 2          # Mínimo para web (tolerancia jitter WiFi)

# ============================================================================
# RED
# ============================================================================
WEB_PORT = 5100
WEB_HOST = '0.0.0.0'
NATIVE_PORT = 5101
NATIVE_HOST = '0.0.0.0'
NATIVE_MAX_CLIENTS = 5

# ============================================================================
# OPTIMIZACIONES DE SOCKET - RF MODE
# ============================================================================
SOCKET_SNDBUF = 65536       # ✅ AUMENTADO: 64KB (vs 8KB) para Int16
SOCKET_RCVBUF = 32768       # ✅ AUMENTADO: 32KB (vs 4KB)
SOCKET_NODELAY = True       # ✅ TCP_NODELAY siempre activo
SOCKET_TIMEOUT = 30.0       # ✅ 30 segundos (vs 2s) - tolera cortes WiFi

# TCP Keepalive (detección de clientes muertos, menos agresivo)
TCP_KEEPALIVE = True
TCP_KEEPIDLE = 10           # ✅ Comenzar después de 10s inactivo (vs 1s)
TCP_KEEPINTVL = 5           # ✅ Intervalo entre probes: 5s (vs 1s)
TCP_KEEPCNT = 3             # 3 intentos antes de cerrar

# ============================================================================
# RF MODE - AUTO-RECONEXIÓN Y PERSISTENCIA
# ============================================================================
RF_AUTO_RECONNECT = True            # ✅ Auto-reconexión habilitada
RF_RECONNECT_DELAY_MS = 1000        # ✅ Delay inicial: 1 segundo
RF_MAX_RECONNECT_DELAY_MS = 8000    # ✅ Delay máximo: 8 segundos
RF_RECONNECT_BACKOFF = 1.5          # ✅ Factor de backoff exponencial
RF_STATE_CACHE_TIMEOUT = 300        # ✅ Cache de estado: 5 minutos

# ============================================================================
# DEBUG Y LOGS
# ============================================================================
DEBUG = False               # ✅ DESACTIVAR en producción (reduce latencia)
LOG_QUEUE_STATS = False     # ✅ Sin logs de colas
LOG_LEVEL = 'WARNING'       # Solo errores críticos
STATS_INTERVAL = 10.0       # Reportes cada 10 segundos (vs 5s)

# ============================================================================
# VALIDACIONES
# ============================================================================
VALIDATE_PACKETS = False    # ✅ Sin validación en producción (ahorra ~0.5ms)
VALIDATE_AUDIO = False      # ✅ Sin validación de audio

# ============================================================================
# OPTIMIZACIONES DE SISTEMA
# ============================================================================
AUDIO_THREAD_PRIORITY = True    # ✅ Activar prioridad real-time
CPU_AFFINITY = None             # [2, 3] para cores específicos (ajustar según CPU)
USE_MEMORYVIEW = True           # ✅ Usar memoryview en lugar de copy()

# ============================================================================
# WEB OPTIMIZATIONS
# ============================================================================
WEB_COMPRESSION = True         # ✅ Sin compresión WebSocket (reduce latencia)
WEB_ASYNC_SEND = True           # ✅ Envío asíncrono con ThreadPool
WEB_MAX_WORKERS = 4             # Workers para envío paralelo
WEB_BINARY_MODE = True          # ✅ Modo binario puro (sin base64)

# ============================================================================
# AUDIO WORKLET (No usado en WiFi sin HTTPS)
# ============================================================================
USE_AUDIO_WORKLET = False       # Desactivado (requiere HTTPS)