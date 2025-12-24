# config.py - CONFIGURACIÓN FINAL ESTABLE

# === CONFIGURACIÓN AUDIO BÁSICA ===
SAMPLE_RATE = 48000
BLOCKSIZE = 512          # Estable para la mayoría de interfaces
DTYPE = 'float32'
CHANNELS_MAX = 32
QUEUE_SIZE = 300         # Buffer grande para evitar underrun
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
NATIVE_LATENCY_TARGET = 15
NATIVE_CHUNK_SIZE = 512  # ¡DEBE SER IGUAL A BLOCKSIZE!
NATIVE_BUFFER_PACKETS = 3
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
MASTER_VOLUME = 0.8
USE_SOFT_CLIP = True
SOFT_CLIP_THRESHOLD = 0.95

# Cálculos automáticos
if __name__ == "config":
    block_time_ms = (BLOCKSIZE / SAMPLE_RATE) * 1000
    WEB_JITTER_BUFFER = int(block_time_ms * 4)
    
    if VERBOSE:
        print(f"[Config] ✅ Configuración cargada")
        print(f"         • Blocksize: {BLOCKSIZE} samples")
        print(f"         • Block time: {block_time_ms:.1f}ms")
        print(f"         • Queue size: {QUEUE_SIZE}")
        print(f"         • Native chunk: {NATIVE_CHUNK_SIZE}")