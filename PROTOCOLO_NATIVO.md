# 📱 PROTOCOLO NATIVO - Android & RF

## 📋 Tabla de Contenidos
1. [Visión General](#visión-general)
2. [Formato del Protocolo](#formato-del-protocolo)
3. [Tipos de Mensajes](#tipos-de-mensajes)
4. [Flujo de Comunicación](#flujo-de-comunicación)
5. [Optimizaciones RF](#optimizaciones-rf)
6. [Implementación Android](#implementación-android)

---

## 🎯 Visión General

El protocolo nativo está diseñado para:
- **Baja latencia**: Protocolo binario comprimido
- **Eficiencia de ancho de banda**: RF es limitado
- **Confiabilidad**: Validación de integridad
- **Escalabilidad**: Múltiples dispositivos simultáneamente

### Características
- **Header binario**: 16 bytes de metadatos
- **Compresión**: zlib para audio
- **Checksums**: Validación CRC
- **Versionado**: Soporte para múltiples versiones de protocolo
- **Flags**: Control granular de opciones

---

## 📦 Formato del Protocolo

### Header (16 bytes)

```
Byte Layout:
┌──────────┬──────────┬──────────┬────────┬────────┬──────────────┐
│ MAGIC    │ VERSION  │ MSG_TYPE │ FLAGS  │ RESERVED│ PAYLOAD_SIZE │
│ (4 bytes)│ (1 byte) │ (1 byte) │(1 byte)│(1 byte)│  (4 bytes)   │
├──────────┼──────────┼──────────┼────────┼────────┼──────────────┤
│ 0xA1D1   │    2     │  0x01    │  0x01  │  0x00  │     1024     │
│ 0A7C     │          │          │        │        │              │
└──────────┴──────────┴──────────┴────────┴────────┴──────────────┘
```

### Detalles del Header

```python
class NativeAndroidProtocol:
    HEADER_SIZE = 16
    MAGIC_NUMBER = 0xA1D10A7C        # Identificador único del protocolo
    PROTOCOL_VERSION = 2              # Versión actual
    
    # Tipos de mensaje
    MSG_TYPE_AUDIO = 0x01             # Datos de audio
    MSG_TYPE_CONTROL = 0x02           # Control (gain/pan/mute)
    
    # Flags de formato de audio
    FLAG_FLOAT32 = 0x01               # Audio en formato float32
    FLAG_INT16 = 0x02                 # Audio en formato int16
    FLAG_RF_MODE = 0x80               # Modo RF (compresión máxima)
    
    # Tamaños máximos
    MAX_CONTROL_PAYLOAD = 500_000     # 500KB para control
    MAX_AUDIO_PAYLOAD = 2_000_000     # 2MB para audio
```

### Estructura en Python

```python
import struct

# Header struct pre-compilado (Big-endian)
_header_struct = struct.Struct('!IHHII')
# I = unsigned int (4 bytes) - MAGIC + VERSION+MSG_TYPE (empaquetados)
# H = unsigned short (2 bytes) - FLAGS + PAYLOAD_SIZE (parte 1)
# I = unsigned int (4 bytes) - PAYLOAD_SIZE (parte 2)

def pack_header(msg_type, flags, payload_size):
    """Empaquetar header binario"""
    magic_version = (MAGIC_NUMBER << 8) | (PROTOCOL_VERSION << 16) | msg_type
    return _header_struct.pack(
        magic_version,
        flags,
        payload_size >> 16,  # Parte alta de payload size
        payload_size & 0xFFFF  # Parte baja de payload size
    )

def unpack_header(header_bytes):
    """Desempaquetar header binario"""
    magic_version, flags_high, size_high, size_low = _header_struct.unpack(header_bytes)
    
    magic = (magic_version >> 0) & 0xFFFFFF
    version = (magic_version >> 24) & 0xFF
    msg_type = (magic_version >> 16) & 0xFF
    flags = flags_high & 0xFF
    payload_size = (size_high << 16) | size_low
    
    return {
        'magic': magic,
        'version': version,
        'msg_type': msg_type,
        'flags': flags,
        'payload_size': payload_size
    }
```

---

## 📨 Tipos de Mensajes

### 1. **HELLO Message** (Conexión Inicial)

**Enviado por**: Cliente Android
**Receptor**: NativeServer
**Propósito**: Registrar dispositivo y obtener configuración

```python
class HelloPayload:
    """Datos del primer mensaje de conexión"""
    device_uuid: str          # UUID único del dispositivo (ej: "abc-123-xyz")
    device_name: str          # Nombre legible (ej: "Samsung Tab S7")
    android_version: str      # ej: "12"
    app_version: str          # ej: "1.0.5"
    capabilities: int         # Flags de capacidades (bits)
```

**Estructura JSON enviada**:
```json
{
  "msg_type": "HELLO",
  "device_uuid": "abc-123-xyz",
  "device_name": "Samsung Galaxy Tab S7",
  "android_version": "12",
  "app_version": "1.0.5",
  "capabilities": {
    "supports_float32": true,
    "supports_int16": true,
    "supports_compression": true,
    "supports_rf_mode": true
  }
}
```

**Respuesta del Servidor**:
```json
{
  "status": "ok",
  "num_channels": 2,
  "sample_rate": 48000,
  "blocksize": 64,
  "device_id": "dev-001"  # ID asignado por servidor
}
```

### 2. **MSG_TYPE_AUDIO** (Streaming de Audio)

**Enviado por**: NativeServer → Cliente Android
**Formato**: Binario comprimido

```
┌──────────────┬──────────────┐
│ HEADER (16B) │ AUDIO PAYLOAD│
└──────────────┴──────────────┘
       │               │
       ├─ Magic        ├─ Audio samples (comprimido)
       ├─ Version      ├─ Compresión: zlib
       ├─ Msg Type     └─ Formato: Int16 o Float32
       ├─ Flags
       └─ Payload Size
```

**Flags para Audio**:
```python
FLAG_INT16 = 0x02      # Audio en int16 (16-bit signed)
FLAG_FLOAT32 = 0x01    # Audio en float32 (32-bit float)
FLAG_RF_MODE = 0x80    # Máxima compresión para RF
```

**Payload de Audio**:
```python
audio_data = {
    'timestamp': 1704547200.123,  # Timestamp del frame
    'sample_count': 64,            # Muestras por canal
    'channel_count': 2,            # Número de canales
    'samples': [...]               # Buffer de audio comprimido
}
```

**Ejemplo de Envío (Python)**:
```python
def send_audio_frame(socket, samples, client_device_uuid):
    """
    samples: numpy array de forma (64, 2) @ 48kHz
    """
    
    # Convertir a int16 para RF (optimización de ancho de banda)
    audio_int16 = (samples * 32767).astype(np.int16)
    
    # Comprimir con zlib (ratio típico: 10:1)
    compressed = zlib.compress(audio_int16.tobytes(), level=6)
    
    # Construir payload
    header = pack_header(
        msg_type=MSG_TYPE_AUDIO,
        flags=FLAG_INT16 | FLAG_RF_MODE,
        payload_size=len(compressed)
    )
    
    # Enviar: header + compressed audio
    socket.sendall(header + compressed)
```

### 3. **MSG_TYPE_CONTROL** (Control de Parámetros)

**Enviado por**: NativeServer → Cliente Android
**Propósito**: Cambios de ganancia, pan, mute

```json
{
  "msg_type": "CONTROL",
  "channel_updates": [
    {
      "channel": 0,
      "gain": 0.8,
      "pan": -0.5,
      "mute": false
    },
    {
      "channel": 1,
      "gain": 1.2,
      "pan": 0.0,
      "mute": false
    }
  ]
}
```

**Estructura Binaria**:
```python
# Empaquetado con struct para eficiencia
control_data = struct.pack(
    '!HffB',  # Format string
    channel_id,        # H: unsigned short (2 bytes)
    gain,             # f: float (4 bytes)
    pan,              # f: float (4 bytes)
    mute_flag         # B: unsigned char (1 byte)
)  # Total: 11 bytes por canal
```

---

## 🔄 Flujo de Comunicación

### Fase 1: Conexión Inicial

```
Cliente Android (TCP 9999)
        │
        ├─ Envía HELLO packet
        │  ├─ device_uuid: "abc-123-xyz"
        │  ├─ device_name: "Samsung Tab"
        │  └─ capabilities: {float32, int16, compression}
        │
        ↓
Server NativeServer
        │
        ├─ Valida conexión
        ├─ Consulta Device Registry
        ├─ Si es nuevo: crea entrada
        ├─ Asigna device_id
        │
        ├─ Envía CONFIG response
        │  ├─ num_channels: 2
        │  ├─ sample_rate: 48000
        │  ├─ blocksize: 64
        │  └─ device_id: "dev-001"
        │
        └─ Comienza streaming de audio
```

### Fase 2: Streaming Continuo

```
NativeServer (Audio Capture)
        │
        ├─ Cada 10.67ms (64 samples @ 48kHz)
        │
        ├─ Aplicar gains/pans del cliente
        │
        ├─ Comprimir audio (zlib)
        │
        ├─ Enviar frame via TCP
        │  └─ Header (16B) + Audio comprimido (típico: 100-200B)
        │
        └─ Latencia total: ~20ms
           ├─ Captura: 10.67ms
           ├─ Procesamiento: 5ms
           └─ Transmisión: 4-5ms

        ↓
Cliente Android (recibe frame)
        │
        ├─ Valida header
        ├─ Descomprime audio
        ├─ Renderiza en altavoz/headset
        └─ Latencia nativa: ~10-20ms
```

### Fase 3: Control Dinámico

```
Web UI (usuario ajusta slider)
        │
        ├─ Socket.IO: 'set_gain' event
        │
        ↓
WebSocket Server
        │
        ├─ Actualiza state de canal
        ├─ Broadcast a todos los clientes web
        │
        └─ Prepara CONTROL message para Native
            │
            ├─ Empaquetar header + control payload
            │
            └─ Enviar a cliente Android vía NativeServer
                │
                ├─ Android recibe CONTROL message
                ├─ Aplica nuevos parámetros
                └─ Audio siguiente frame ya tiene cambios
                   Latencia: ~30-50ms
```

---

## 📡 Optimizaciones RF

### Problema RF: Ancho de Banda Limitado

- **Conexión típica**: 2-4 Mbps en RF
- **Audio sin comprimir**: 48000 Hz × 2 ch × 2 bytes = 192 kbps
- **Compresión zlib**: ~20 kbps (ratio 10:1)
- **Overhead TCP**: ~5% adicional

### Estrategias de Optimización

#### 1. **Compresión Inteligente**
```python
# Nivel 6: Balance velocidad/compresión
COMPRESSION_LEVEL = 6

# Resultado típico:
# - Sin comprimir: 192 kbps
# - Con compresión: 20 kbps (90% reducción)
# - Overhead: < 5%
# - Latencia de compresión: < 2ms
```

#### 2. **Control Selectivo de Canales**
```python
# Cliente solo recibe canales que necesita
subscriptions = {
    'device_uuid_1': {
        'channels': [0, 1],  # Solo estos canales
        'gain': [1.0, 0.8],
        'pan': [0.0, -0.5],
        'mute': [False, False]
    }
}

# Ejemplo: Si cliente solo necesita canal 0
# Ahorro: 50% de ancho de banda de audio
```

#### 3. **Debouncing de Control**
```python
# Agrupar cambios frecuentes (ej: ajuste de fader)
CONTROL_DEBOUNCE_MS = 50

# Envío agrupado:
# Enviar control message cada 50ms máximo
# Beneficio: Reduce overhead TCP en comandos rápidos
```

#### 4. **Formato de Dato Optimizado**
```python
# Int16 en lugar de Float32
# Uso: Int16 = 2 bytes vs Float32 = 4 bytes (50% menos)
# Calidad: Suficiente para audio profesional
# Rango: -32768 a +32767 @ ±1.0 normalizado

def convert_to_int16(float_samples):
    """Convertir float32 [-1.0, 1.0] a int16 [-32768, 32767]"""
    return (float_samples * 32767).astype(np.int16)
```

#### 5. **Batching de Frames**
```python
# Posibilidad de enviar múltiples frames en una TCP packet
# Beneficio: Reduce overhead TCP/IP (40 bytes per packet)
# Tradeoff: Ligero aumento de latencia (tolerable para RF)

# Ejemplo:
# 1 frame = 64 samples
# 2 frames batched = 128 samples
# Ahorro de overhead: 40 bytes / (2 × 150 bytes) = 13% menos overhead
```

---

## 📱 Implementación Android

### Lado Android (Kotlin)

```kotlin
class NativeAudioClient {
    private lateinit var socket: Socket
    private val audioBuffer = ByteArray(4096)
    private var audioRenderer: AudioRenderer? = null
    
    fun connect(serverHost: String, serverPort: Int) {
        Thread {
            socket = Socket(serverHost, serverPort)
            
            // Enviar HELLO packet
            sendHelloPacket()
            
            // Recibir configuración
            val config = receiveConfig()
            audioRenderer = AudioRenderer(config)
            
            // Loop de recepción de audio
            receiveAudioLoop()
        }.start()
    }
    
    private fun sendHelloPacket() {
        val json = JSONObject().apply {
            put("msg_type", "HELLO")
            put("device_uuid", getDeviceUUID())
            put("device_name", getDeviceName())
            put("android_version", Build.VERSION.RELEASE)
            put("app_version", BuildConfig.VERSION_NAME)
            put("capabilities", JSONObject().apply {
                put("supports_float32", true)
                put("supports_int16", true)
                put("supports_compression", true)
            })
        }
        
        socket.outputStream.write(json.toString().toByteArray())
        socket.outputStream.flush()
    }
    
    private fun receiveAudioLoop() {
        val inputStream = socket.inputStream
        
        while (true) {
            // Leer header (16 bytes)
            val header = ByteArray(16)
            inputStream.readFully(header)
            
            val (msgType, flags, payloadSize) = parseHeader(header)
            
            when (msgType) {
                MSG_TYPE_AUDIO -> {
                    // Leer payload comprimido
                    val compressed = ByteArray(payloadSize)
                    inputStream.readFully(compressed)
                    
                    // Descomprimir
                    val decompressed = decompress(compressed)
                    
                    // Convertir a float32 para renderizado
                    val samples = convertInt16ToFloat(decompressed)
                    
                    // Renderizar (nativo con Oboe)
                    audioRenderer?.renderSamples(samples)
                }
                MSG_TYPE_CONTROL -> {
                    // Aplicar cambios de control
                    handleControlMessage(compressed)
                }
            }
        }
    }
    
    private fun convertInt16ToFloat(int16Data: ByteArray): FloatArray {
        val floatArray = FloatArray(int16Data.size / 2)
        for (i in floatArray.indices) {
            val int16 = ((int16Data[i * 2].toInt() and 0xFF) shl 8) or 
                       (int16Data[i * 2 + 1].toInt() and 0xFF)
            floatArray[i] = (int16 / 32768f)
        }
        return floatArray
    }
}
```

### Renderizado Nativo (Oboe C++)

```cpp
// native_audio_engine.cpp
#include <oboe/Oboe.h>
#include <cstring>

class AudioEngine : public oboe::AudioStreamCallback {
public:
    oboe::DataCallbackResult onAudioReady(
        oboe::AudioStream *audioStream,
        void *audioData,
        int32_t numFrames) override {
        
        // audioData es float* buffer para llenar
        // numFrames = frames a procesar
        
        if (currentAudioBuffer) {
            std::memcpy(audioData, 
                       currentAudioBuffer, 
                       numFrames * sizeof(float) * channelCount);
        }
        
        return oboe::DataCallbackResult::Continue;
    }
    
private:
    float* currentAudioBuffer = nullptr;
    int channelCount = 2;
};
```

---

## 🔍 Validación de Integridad

### CRC32 (Checksum)

```python
import zlib

def add_crc32(data: bytes) -> bytes:
    """Agregar CRC32 al final del payload"""
    crc = zlib.crc32(data) & 0xFFFFFFFF
    return data + struct.pack('!I', crc)

def verify_crc32(data: bytes) -> bool:
    """Verificar CRC32 del payload"""
    if len(data) < 4:
        return False
    
    payload = data[:-4]
    expected_crc = struct.unpack('!I', data[-4:])[0]
    actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
    
    return expected_crc == actual_crc
```

### Heartbeat (Detección de Desconexión)

```python
class NativeServer:
    def __init__(self):
        self.client_heartbeats = {}  # {client_id: last_seen_timestamp}
    
    def send_heartbeat_request(self, client_id):
        """Enviar solicitud de heartbeat"""
        header = pack_header(
            msg_type=MSG_TYPE_HEARTBEAT,
            flags=0,
            payload_size=0
        )
        # Enviar solo header, sin payload
        self.clients[client_id].send(header)
    
    def check_timeouts(self):
        """Detectar clientes zombies"""
        now = time.time()
        timeout_clients = []
        
        for client_id, last_seen in self.client_heartbeats.items():
            elapsed = now - last_seen
            
            if elapsed > HEARTBEAT_TIMEOUT:  # 30 segundos
                timeout_clients.append(client_id)
        
        for client_id in timeout_clients:
            self.disconnect_client(client_id)
```

---

## 📊 Estadísticas y Monitoreo

### Métricas Enviadas al Dashboard

```python
NATIVE_STATS = {
    'connected_clients': 5,
    'bytes_sent_per_second': 25000,  # ~200 kbps / 8
    'bytes_compressed_ratio': 0.1,    # 10:1 compresión
    'audio_latency_ms': 18.5,
    'last_frame_timestamp': 1704547200.123,
    'device_registry': {
        'total_devices': 12,
        'active_devices': 5,
        'offline_devices': 7
    }
}
```

