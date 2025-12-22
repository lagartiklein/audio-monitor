# Configuración del Sistema de Monitoreo de Audio

# Optimizado para latencia <25ms - AUTO-CONFIGURACIÓN



# === CONFIGURACIÓN DE AUDIO (AUTO) ===

# Estos valores se ajustan automáticamente según la interfaz detectada

SAMPLE_RATE = None  # Auto: se detecta del dispositivo

BLOCKSIZE = 128     # Fijo: 128 samples para ultra-baja latencia

DTYPE = 'float32'   # Sin conversiones (máxima eficiencia)



# === CONFIGURACIÓN DE RED ===

HOST = '0.0.0.0'    # Accesible desde red local

PORT = 5100



# === LÍMITES DEL SISTEMA ===

CHANNELS_MAX = 32       # Máximo de canales a procesar

QUEUE_SIZE = 10         # Buffers en cola (aumentado para estabilidad)

MAX_CLIENTS = 8         # Máximo de clientes simultáneos



# === CONFIGURACIÓN DE CLIENTE (AUTO) ===

# Se calcula automáticamente según latencia de red y sample rate

JITTER_BUFFER_MS = None  # Auto: ajustado dinámicamente



# === WEBSOCKET ===

PING_INTERVAL = 5       # Segundos entre pings

PING_TIMEOUT = 10       # Timeout para considerar desconectado



# === DEBUG ===

VERBOSE = True          # Mostrar información detallada

SHOW_METRICS = False    # Mostrar métricas de rendimiento (cada 5s)