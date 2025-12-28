# ⚡ CONFIGURACIÓN BÁSICA RF + WEB (COLAS SEPARADAS)
SAMPLE_RATE = 48000
BLOCKSIZE = 64

# ⚡ CONFIGURACIÓN DE COLAS SEPARADAS
QUEUE_SIZE = 3          # Tamaño default (para compatibilidad)
NATIVE_QUEUE_SIZE = 2   # Cola pequeña para baja latencia nativa
WEB_QUEUE_SIZE = 4      # Cola más grande para web (tolerancia a jitter)

WEB_PORT = 5100
WEB_HOST = '0.0.0.0'
NATIVE_PORT = 5101
NATIVE_HOST = '0.0.0.0'
NATIVE_MAX_CLIENTS = 5
DEBUG = True
LOG_QUEUE_STATS = True  # Log estadísticas de colas

LOG_LEVEL = 'INFO'  # 'DEBUG' para troubleshooting
STATS_INTERVAL = 5.0  # Segundos entre reportes de estadísticas