# Configuración del Sistema de Monitoreo de Audio

# === CONFIGURACIÓN DE AUDIO ===
# Opciones: 22050 (baja latencia, suficiente calidad) o 44100 (CD quality)
SAMPLE_RATE = 44100

# Buffer size en samples
# 128 = ~2.9ms @ 44100Hz (ultra-low latency, más riesgo de dropouts)
# 256 = ~5.8ms @ 44100Hz (balance recomendado)
BLOCKSIZE = 256

# Formato de audio
# 'int16' = 50% menos bandwidth que 'float32'
DTYPE = 'int16'

# === CONFIGURACIÓN DE RED ===
HOST = '0.0.0.0'  # Accesible desde red local
PORT = 5100

# === LÍMITES DEL SISTEMA ===
CHANNELS_MAX = 32  # Máximo de canales a procesar
QUEUE_SIZE = 10    # Buffers en cola (10 * 5.8ms = 58ms max delay)

# === CONFIGURACIÓN DE CLIENTE ===
# Jitter buffer inicial en milisegundos
JITTER_BUFFER_MS = 20  # 20ms para WiFi 5GHz, aumentar a 40ms para 2.4GHz

# === DEBUG ===
VERBOSE = True  # Mostrar información detallada en consola