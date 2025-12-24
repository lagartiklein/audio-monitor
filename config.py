# config.py - CONFIGURACIÓN ADAPTATIVA AL HARDWARE REAL

# === CONFIGURACIÓN AUDIO BÁSICA ===
# ✅ ESTÁNDAR FORZADO: 256 samples para ultra-baja latencia
SAMPLE_RATE = 44100      # Se ajusta dinámicamente según hardware
BLOCKSIZE = 256          # ✅ FORZADO: 256 samples estándar
DTYPE = 'float32'
CHANNELS_MAX = 32
QUEUE_SIZE = 5         # ✅ Reducido para baja latencia
MAX_CLIENTS = 8

# === CONFIGURACIÓN WEB ===
WEB_ENABLED = True
WEB_PORT = 5100
WEB_HOST = '0.0.0.0'
WEB_LATENCY_TARGET = 40
WEB_JITTER_BUFFER = 40
PING_INTERVAL = 5
PING_TIMEOUT = 10

# === CONFIGURACIÓN NATIVE ===
NATIVE_ENABLED = True
NATIVE_PORT = 5101
NATIVE_HOST = '0.0.0.0'
NATIVE_LATENCY_TARGET = 10       # ✅ 10ms objetivo con 256 samples
NATIVE_CHUNK_SIZE = 256          # ✅ FORZADO: 256 samples estándar
NATIVE_BUFFER_PACKETS = 2        # ✅ Mínimo (2x256 = 512 total)
NATIVE_MAGIC_NUMBER = 0xA1D10A7C
NATIVE_PROTOCOL_VERSION = 2
NATIVE_HEADER_SIZE = 20
NATIVE_MAX_CLIENTS = 10
NATIVE_HEARTBEAT_INTERVAL = 2.0

# === DEBUG ===
VERBOSE = True
LOG_NATIVE_PACKETS = False
MEASURE_LATENCY = True

# === CALIDAD DE AUDIO ===
MASTER_VOLUME = 1.0      # ✅ Sin atenuación
USE_SOFT_CLIP = True
SOFT_CLIP_THRESHOLD = 0.95

# ✅ Función para actualizar solo sample rate (blocksize es fijo)
def update_audio_config(detected_sample_rate):
    """
    Actualiza solo sample rate - blocksize siempre es 256
    """
    global SAMPLE_RATE, WEB_JITTER_BUFFER
    
    SAMPLE_RATE = detected_sample_rate
    
    # Ajustar jitter buffer según sample rate
    block_time_ms = (BLOCKSIZE / SAMPLE_RATE) * 1000
    WEB_JITTER_BUFFER = int(block_time_ms * 4)
    
    if VERBOSE:
        print(f"[Config] ✅ Configuración adaptada:")
        print(f"         • Sample Rate: {SAMPLE_RATE} Hz (del hardware)")
        print(f"         • Blocksize: {BLOCKSIZE} samples (FORZADO)")
        print(f"         • Block time: {block_time_ms:.2f}ms")
        print(f"         • Native chunk: {NATIVE_CHUNK_SIZE}")
        print(f"         • Queue size: {QUEUE_SIZE}")
        print(f"         • Latencia objetivo: {NATIVE_LATENCY_TARGET}ms")

# Cálculos iniciales
if __name__ == "config":
    block_time_ms = (BLOCKSIZE / SAMPLE_RATE) * 1000
    WEB_JITTER_BUFFER = int(block_time_ms * 4)
    
    if VERBOSE:
        print(f"[Config] ⚙️ Configuración estándar:")
        print(f"         • Sample Rate: {SAMPLE_RATE} Hz (se ajustará al hardware)")
        print(f"         • Blocksize: {BLOCKSIZE} samples (FORZADO)")
        print(f"         • Block time: {block_time_ms:.2f}ms")