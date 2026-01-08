# 📡 Protocolos de Comunicación

Documentación completa de los protocolos utilizados en Fichatech Audio Monitor: WebSocket, Protocolo Nativo Binario y Modo RF.

---

## 📋 Tabla de Contenidos

- [Visión General](#visión-general)
- [WebSocket Protocol](#websocket-protocol)
- [Protocolo Nativo Binario](#protocolo-nativo-binario)
- [Modo RF (Reconexión Automática)](#modo-rf-reconexión-automática)
- [Comparativa de Protocolos](#comparativa-de-protocolos)
- [Ejemplos de Implementación](#ejemplos-de-implementación)
- [Troubleshooting de Protocolo](#troubleshooting-de-protocolo)

---

## 🎯 Visión General

Fichatech implementa **dos protocolos de comunicación** optimizados para diferentes escenarios:

```
┌─────────────────────────────────────┐
│       Fichatech Audio Monitor        │
├─────────────────────────────────────┤
│                                     │
│  Puerto 5100: WebSocket             │
│  - Clientes Web (navegador)         │
│  - JSON-based + Socket.IO           │
│  - Fácil debugging                  │
│                                     │
│  Puerto 5101: Protocolo Nativo      │
│  - Clientes Android/iOS             │
│  - Binario comprimido               │
│  - Ultra-baja latencia              │
│                                     │
│  Ambos: Modo RF opcional            │
│  - Reconexión automática            │
│  - Caché de estado persistente      │
│                                     │
└─────────────────────────────────────┘
```

---

## 🔌 WebSocket Protocol

### Características

- **Base**: Socket.IO (compatible con WebSocket estándar)
- **Formato**: JSON + Binary
- **Latencia**: ~20-50ms (según red)
- **Clientes**: Navegadores web, aplicaciones Node.js
- **Puerto**: 5100
- **Ruta**: `http://host:5100/socket.io/`

### Eventos de Cliente (Servidor → Cliente)

#### `connect`
Confirmación de conexión exitosa.

```javascript
{
  event: 'connect'
  // Servidor envía datos iniciales en respuesta
}
```

#### `server_stats`
Estadísticas del servidor en tiempo real (cada 500ms).

```json
{
  "cpu": 8.5,
  "memory": 156.2,
  "latency": 45,
  "active_clients": 3,
  "timestamp": 1704672000000
}
```

#### `device_list`
Lista de dispositivos de audio disponibles.

```json
{
  "devices": [
    {
      "id": 0,
      "name": "Microphone Array (Realtek High Definition Audio)",
      "channels": 2,
      "sample_rate": 48000,
      "latency": "low"
    },
    {
      "id": 1,
      "name": "USB Audio Device",
      "channels": 4,
      "sample_rate": 96000,
      "latency": "medium"
    }
  ]
}
```

#### `channel_list`
Estado actual de todos los canales.

```json
{
  "channels": [
    {
      "id": 0,
      "name": "Channel 1",
      "volume": 0.85,
      "pan": -0.2,
      "mute": false,
      "selected": true,
      "monitor": true
    },
    {
      "id": 1,
      "name": "Channel 2",
      "volume": 0.75,
      "pan": 0.1,
      "mute": false,
      "selected": false,
      "monitor": false
    }
  ]
}
```

#### `channel_volume_changed`
Notificación de cambio de volumen de canal.

```json
{
  "channel_id": 0,
  "volume": 0.9
}
```

#### `channel_pan_changed`
Cambio de pan (panorama estéreo).

```json
{
  "channel_id": 0,
  "pan": -0.5
}
```

#### `channel_mute_changed`
Cambio de estado mute.

```json
{
  "channel_id": 0,
  "mute": true
}
```

#### `audio_data` (Stream Binario)
Datos de audio comprimidos (stream de audio).

```javascript
{
  data: "H4sICFoL12UC/2F1ZGlvLmRhdGEA...",  // Base64 compressed
  shape: [32, 2],  // 32 muestras, 2 canales
  timestamp: 1704672000000
}
```

#### `connection_error`
Error de conexión del servidor.

```json
{
  "error": "Audio device disconnected",
  "code": "DEVICE_ERROR"
}
```

### Eventos de Servidor (Cliente → Servidor)

#### `set_channel_volume`
Cambiar volumen de un canal.

**Enviar:**
```json
{
  "channel_id": 0,
  "volume": 0.85
}
```

**Validación:**
- `channel_id`: 0-31
- `volume`: 0.0-2.0 (0-200%)

#### `set_channel_pan`
Cambiar panorama estéreo.

**Enviar:**
```json
{
  "channel_id": 0,
  "pan": -0.5
}
```

**Validación:**
- `pan`: -1.0 (izq) a +1.0 (der)

#### `set_channel_mute`
Mutear/desmutear canal.

**Enviar:**
```json
{
  "channel_id": 0,
  "mute": true
}
```

#### `select_channel`
Seleccionar canal activo.

**Enviar:**
```json
{
  "channel_id": 0
}
```

#### `get_device_list`
Solicitar lista de dispositivos.

**Enviar:**
```json
{}
```

#### `get_server_stats`
Solicitar estadísticas del servidor.

**Enviar:**
```json
{}
```

### Cliente JavaScript Ejemplo

```javascript
const socket = io('http://localhost:5100');

// Conectar
socket.on('connect', () => {
  console.log('Conectado al servidor');
  
  // Solicitar datos iniciales
  socket.emit('get_device_list');
});

// Recibir estadísticas
socket.on('server_stats', (stats) => {
  console.log(`CPU: ${stats.cpu}%, Latencia: ${stats.latency}ms`);
  updateUI(stats);
});

// Cambiar volumen (slider)
document.getElementById('volume-slider').addEventListener('input', (e) => {
  const volume = parseFloat(e.target.value);
  socket.emit('set_channel_volume', {
    channel_id: 0,
    volume: volume
  });
});

// Recibir confirmación
socket.on('channel_volume_changed', (data) => {
  console.log(`Canal ${data.channel_id}: ${data.volume}`);
});

// Manejar desconexión
socket.on('disconnect', () => {
  console.log('Desconectado del servidor');
  startReconnectionTimer();
});
```

---

## 📦 Protocolo Nativo Binario

### Características

- **Base**: TCP binario personalizado
- **Formato**: Estructura binaria comprimida
- **Latencia**: ~10-30ms (según red)
- **Clientes**: Android, iOS, aplicaciones nativas
- **Puerto**: 5101
- **Compresión**: zlib nivel 1

### Estructura de Frame

#### Header (16 bytes obligatorios)

```
Offset  Tamaño  Campo         Descripción
──────────────────────────────────────────
0       4       Magic Number  0xA1D10A7C (identificador)
4       2       Version       2 (versión del protocolo)
6       2       Message Type  0x01=Audio, 0x02=Control
8       4       Flags         Bitmap de opciones
12      4       Payload Size  Tamaño del payload en bytes
```

**Decodificación (Python):**
```python
import struct

data = receive(16)  # Recibir 16 bytes de header
magic, version, msg_type, flags, payload_size = struct.unpack(
    '!IHHII',  # Network byte order (big-endian)
    data
)

# Validar
assert magic == 0xA1D10A7C, "Invalid magic number"
assert version == 2, "Unsupported protocol version"
```

#### Message Type (MSG_TYPE)

```
Tipo    Valor   Descripción
──────────────────────────────
AUDIO   0x01    Stream de audio comprimido
CONTROL 0x02    Comandos de control (volumen, etc)
SYNC    0x03    Sincronización de estado
```

#### Flags (Bitmap)

```
Bit  Descripción           Notas
─────────────────────────────────────────
0    FLAG_FLOAT32          Datos float 32-bit
1    FLAG_INT16            Datos int 16-bit (PCM)
2    FLAG_COMPRESSED       Payload comprimido con zlib
7    FLAG_RF_MODE          Modo RF habilitado
```

**Ejemplo:**
```python
flags = 0x01 | 0x04  # Float32 + Comprimido = 0x05
```

### Audio Payload Format

Para `MSG_TYPE_AUDIO` (0x01):

```
Offset  Tamaño  Campo           Descripción
──────────────────────────────────────────
0       1       Num Channels    Número de canales
1       2       Num Samples     Número de muestras
3       N       Audio Data      Datos de audio

Audio Data (si no comprimido):
- Para cada muestra: [CH0_float32, CH1_float32, ...]
- Orden: Samples first, then channels
```

**Ejemplo con 2 canales, 32 muestras:**

```
┌─────────────────────────────────────┐
│ Num Channels: 2                     │ 1 byte
├─────────────────────────────────────┤
│ Num Samples: 32                     │ 2 bytes
├─────────────────────────────────────┤
│ Sample 0:                           │
│   CH0: float32 (4 bytes)            │
│   CH1: float32 (4 bytes)            │
├─────────────────────────────────────┤
│ Sample 1:                           │
│   CH0: float32 (4 bytes)            │ × 32
│   CH1: float32 (4 bytes)            │
├─────────────────────────────────────┤
│ ...                                 │
├─────────────────────────────────────┤
│ Total Payload: 1 + 2 + (32×2×4) = 259 bytes
│ Comprimido:   ~100-150 bytes (60% reducción)
└─────────────────────────────────────┘
```

### Codificación del Frame

```python
def encode_audio_frame(channels_data):
    """
    Entrada: Dict[int, np.ndarray]
    {
      0: array([0.1, 0.2, ...]) shape (32,),
      1: array([0.05, 0.15, ...]) shape (32,)
    }
    
    Salida: bytes (header + payload comprimido)
    """
    
    # 1. Construir payload
    payload = bytearray()
    payload.append(len(channels_data))  # Num channels
    
    # Num samples (de primer canal)
    first_ch = next(iter(channels_data.values()))
    num_samples = len(first_ch)
    payload.extend(struct.pack('!H', num_samples))
    
    # Interleave: muestra 0 todos canales, muestra 1 todos canales...
    for sample_idx in range(num_samples):
        for ch_id in sorted(channels_data.keys()):
            ch_data = channels_data[ch_id]
            value = ch_data[sample_idx]
            payload.extend(struct.pack('!f', float(value)))  # Float32
    
    # 2. Comprimir payload
    compressed_payload = zlib.compress(bytes(payload), level=1)
    
    # 3. Construir header
    MAGIC = 0xA1D10A7C
    VERSION = 2
    MSG_TYPE = 0x01  # Audio
    FLAGS = 0x01 | 0x04  # Float32 + Compressed
    PAYLOAD_SIZE = len(compressed_payload)
    
    header = struct.pack(
        '!IHHII',
        MAGIC,
        VERSION,
        MSG_TYPE,
        FLAGS,
        PAYLOAD_SIZE
    )
    
    return header + compressed_payload
```

### Decodificación del Frame

```python
def decode_audio_frame(data):
    """
    Entrada: bytes (header + payload)
    Salida: Dict[int, np.ndarray]
    """
    
    # 1. Parsear header
    header = data[:16]
    magic, version, msg_type, flags, payload_size = struct.unpack(
        '!IHHII',
        header
    )
    
    # Validaciones
    assert magic == 0xA1D10A7C
    assert version == 2
    assert msg_type == 0x01  # Audio
    
    # 2. Extraer payload
    payload = data[16:16 + payload_size]
    
    # 3. Descomprimir si es necesario
    if flags & 0x04:  # Compressed
        payload = zlib.decompress(payload)
    
    # 4. Parsear payload
    num_channels = struct.unpack('!B', payload[0:1])[0]
    num_samples = struct.unpack('!H', payload[1:3])[0]
    
    audio_data = payload[3:]
    
    # 5. Desinterleave samples
    channels_data = {}
    sample_size = num_channels * 4  # 4 bytes per float32
    
    for sample_idx in range(num_samples):
        offset = sample_idx * sample_size
        for ch_id in range(num_channels):
            ch_offset = offset + ch_id * 4
            value = struct.unpack('!f', audio_data[ch_offset:ch_offset+4])[0]
            
            if ch_id not in channels_data:
                channels_data[ch_id] = []
            channels_data[ch_id].append(value)
    
    # 6. Convertir a numpy
    for ch_id in channels_data:
        channels_data[ch_id] = np.array(channels_data[ch_id], dtype=np.float32)
    
    return channels_data
```

### Control Payload Format

Para `MSG_TYPE_CONTROL` (0x02):

```json
{
  "command": "set_channel_volume",
  "channel_id": 0,
  "value": 0.85
}
```

**Codificación:**
```python
def encode_control(command, params):
    """Codificar comando de control como JSON"""
    control_data = {"command": command}
    control_data.update(params)
    json_str = json.dumps(control_data)
    return json_str.encode('utf-8')
```

---

## 🔄 Modo RF (Reconexión Automática)

### ¿Qué es RF Mode?

**RF (Reconnect + Failover)** es un modo que proporciona:

1. **Reconexión automática**: Cliente se reconecta automáticamente
2. **Caché de estado**: Servidor preserva estado del cliente
3. **Sincronización**: Sincronización de estado después de reconexión
4. **Persistencia**: Estados persisten entre sesiones (opcional)

### Habilitación

```python
# En config.py
RF_AUTO_RECONNECT = True              # Habilitar reconexión
RF_RECONNECT_DELAY_MS = 1000          # Esperar 1s antes de reconectar
RF_MAX_RECONNECT_ATTEMPTS = 10        # Max 10 intentos
RF_STATE_CACHE_TIMEOUT = 0            # 0 = no expira
RF_MAX_PERSISTENT_STATES = 50         # Guardar max 50 estados
```

### Flujo de Reconexión

```
1. CONEXIÓN INICIAL
   ┌──────────────┐         ┌──────────────┐
   │   Cliente    │         │   Servidor   │
   └──────┬───────┘         └──────┬───────┘
          │ TCP Connect :5101       │
          ├────────────────────────→│
          │ Send device_id          │
          ├────────────────────────→│
          │                Accept, Crear estado
          │ OK                      │
          │←────────────────────────┤
          │ Streaming audio...      │
          │←────────────────────────┤

2. DESCONEXIÓN (WiFi cae)
   ┌──────────────┐         ┌──────────────┐
   │   Cliente    │         │   Servidor   │
   └──────┬───────┘         └──────┬───────┘
          │ Socket timeout          │
          │ Detecta error           │ Detecta timeout
          │                         │ Guardar estado en caché
          │                    [Estado guardado]

3. RECONEXIÓN AUTOMÁTICA
   ┌──────────────┐         ┌──────────────┐
   │   Cliente    │         │   Servidor   │
   └──────┬───────┘         └──────┬───────┘
          │ [Espera RF_RECONNECT_DELAY_MS]
          │ TCP Connect :5101       │
          ├────────────────────────→│
          │ Send device_id + state_id
          ├────────────────────────→│
          │                Buscar estado en caché
          │ Sync [volumen, pan, ...] │
          │←────────────────────────┤
          │ OK, Streaming reanudado │
          │←────────────────────────┤
```

### Device ID y State Tracking

```python
# Cliente: Generar device_id único
import uuid

class NativeClient:
    def __init__(self):
        self.device_id = str(uuid.uuid4())  # Único por dispositivo
        self.state_id = None                # Asignado por servidor
        self.last_state = {}

def connect_to_server(host, port):
    """Conectarse con device_id"""
    socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket.connect((host, port))
    
    # Enviar device_id en handshake
    handshake = json.dumps({
        "device_id": self.device_id,
        "protocol_version": 2,
        "rf_mode": True  # Habilitar RF Mode
    })
    socket.sendall(handshake.encode())
    
    # Recibir confirmación
    response = json.loads(socket.recv(1024).decode())
    self.state_id = response['state_id']  # Servidor asigna state_id
```

### State Cache (Servidor)

```python
class StateCache:
    """
    Caché de estados de clientes para reconexión rápida.
    """
    def __init__(self, timeout=0, max_states=50):
        self.states = {}  # {state_id: state}
        self.timeout = timeout
        self.max_states = max_states
    
    def save_state(self, device_id):
        """Guardar estado de cliente"""
        state_id = str(uuid.uuid4())
        self.states[state_id] = {
            'device_id': device_id,
            'channels': get_channel_state(),
            'timestamp': time.time(),
            'device_info': get_device_info()
        }
        
        # Limpiar si excede máximo
        if len(self.states) > self.max_states:
            oldest_id = min(self.states, key=lambda x: self.states[x]['timestamp'])
            del self.states[oldest_id]
        
        return state_id
    
    def restore_state(self, state_id):
        """Restaurar estado previamente guardado"""
        if state_id not in self.states:
            return None
        
        state = self.states[state_id]
        
        # Verificar expiración
        if self.timeout > 0:
            age = time.time() - state['timestamp']
            if age > self.timeout:
                del self.states[state_id]
                return None
        
        return state
    
    def cleanup_expired(self):
        """Limpiar estados expirados"""
        if self.timeout <= 0:
            return  # No expiran
        
        now = time.time()
        expired = [
            sid for sid, state in self.states.items()
            if now - state['timestamp'] > self.timeout
        ]
        
        for sid in expired:
            del self.states[sid]
```

### Sync de Estado Post-Reconexión

```python
def sync_after_reconnect(client_id, old_state_id):
    """
    Sincronizar cliente después de reconexión.
    """
    # 1. Obtener estado guardado
    old_state = state_cache.restore_state(old_state_id)
    
    if not old_state:
        # Estado expirado o no encontrado
        send_full_state_update(client_id)
        return
    
    # 2. Comparar con estado actual
    current_state = get_channel_state()
    changes = compute_state_diff(old_state['channels'], current_state)
    
    # 3. Enviar solo cambios
    for change in changes:
        send_update(client_id, change)
    
    # 4. Crear nuevo state_id
    new_state_id = state_cache.save_state(client_id)
    send_sync_complete(client_id, new_state_id)
```

---

## 🔄 Comparativa de Protocolos

| Característica | WebSocket | Protocolo Nativo |
|---|---|---|
| **Base** | HTTP + WS | TCP binario |
| **Formato** | JSON + texto | Binario comprimido |
| **Latencia** | 20-50ms | 10-30ms |
| **Overhead** | ~40% | ~5% |
| **Compresión** | Opcional | zlib obligatorio |
| **Debugging** | Fácil (JSON) | Difícil (binario) |
| **Browsers** | ✅ Sí | ❌ No |
| **Android/iOS** | ⚠️ Posible | ✅ Óptimo |
| **Bandwidth** | 2.5Mbps/cliente | 1.8Mbps/cliente |
| **CPU Server** | 8% | 5% |
| **CPU Cliente** | 15% | 10% |
| **Firewall** | Más permisivo | Puede requerir config |

---

## 📝 Ejemplos de Implementación

### Cliente JavaScript (WebSocket)

```javascript
class AudioMonitorClient {
  constructor(host = 'localhost', port = 5100) {
    this.socket = io(`http://${host}:${port}`);
    this.setupEventListeners();
  }
  
  setupEventListeners() {
    // Conectar
    this.socket.on('connect', () => {
      console.log('Conectado');
      this.requestInitialData();
    });
    
    // Estadísticas
    this.socket.on('server_stats', (stats) => {
      this.updateStats(stats);
    });
    
    // Audio
    this.socket.on('audio_data', (frame) => {
      this.processAudioFrame(frame);
    });
    
    // Cambios
    this.socket.on('channel_volume_changed', (data) => {
      this.updateChannelUI(data.channel_id, data.volume);
    });
  }
  
  setChannelVolume(channelId, volume) {
    this.socket.emit('set_channel_volume', {
      channel_id: channelId,
      volume: Math.max(0, Math.min(2, volume))
    });
  }
  
  processAudioFrame(frame) {
    // Decodificar Base64
    const binaryData = atob(frame.data);
    const bytes = new Uint8Array(binaryData.length);
    for (let i = 0; i < binaryData.length; i++) {
      bytes[i] = binaryData.charCodeAt(i);
    }
    
    // Descomprimir (pako library)
    const decompressed = pako.inflate(bytes);
    
    // Procesar samples
    const view = new DataView(decompressed.buffer);
    const samples = [];
    for (let i = 0; i < decompressed.length; i += 4) {
      samples.push(view.getFloat32(i, false));  // Network byte order
    }
    
    // Renderizar
    this.renderAudio(samples, frame.shape);
  }
}

// Uso
const client = new AudioMonitorClient();
```

### Cliente Android (Protocolo Nativo)

```kotlin
class AudioMonitorClient(private val host: String, 
                         private val port: Int = 5101) {
  private var socket: Socket? = null
  private var isConnected = false
  
  fun connect(): Boolean {
    return try {
      socket = Socket(host, port)
      
      // Enviar handshake
      val deviceId = UUID.randomUUID().toString()
      val handshake = """{"device_id":"$deviceId","protocol_version":2}"""
      socket!!.outputStream.write(handshake.toByteArray())
      
      // Iniciar reader thread
      Thread { readAudioFrames() }.start()
      
      isConnected = true
      true
    } catch (e: Exception) {
      Log.e("AudioClient", "Connection failed", e)
      false
    }
  }
  
  private fun readAudioFrames() {
    val buffer = ByteArray(4096)
    val input = socket!!.inputStream
    
    try {
      while (isConnected) {
        // Leer header (16 bytes)
        input.readFully(buffer, 0, 16)
        
        val magic = ByteBuffer.wrap(buffer, 0, 4)
          .getInt(0)  // Network byte order
        assert(magic == 0xA1D10A7C.toInt())
        
        val payloadSize = ByteBuffer.wrap(buffer, 12, 4)
          .getInt(0)
        
        // Leer payload
        input.readFully(buffer, 16, payloadSize)
        
        // Descomprimir
        val decompressed = decompress(buffer, 16, payloadSize)
        
        // Procesar audio
        processAudioFrame(decompressed)
      }
    } catch (e: Exception) {
      Log.e("AudioClient", "Read error", e)
      handleDisconnection()
    }
  }
  
  private fun decompress(data: ByteArray, offset: Int, 
                        size: Int): ByteArray {
    return try {
      val inflater = Inflater()
      inflater.setInput(data, offset, size)
      val output = ByteArray(2048)
      val resultSize = inflater.inflate(output)
      output.copyOf(resultSize)
    } catch (e: DataFormatException) {
      ByteArray(0)
    }
  }
  
  fun setChannelVolume(channelId: Int, volume: Float) {
    val command = """
      {
        "command": "set_channel_volume",
        "channel_id": $channelId,
        "value": $volume
      }
    """
    socket?.outputStream?.write(command.toByteArray())
  }
  
  fun disconnect() {
    isConnected = false
    socket?.close()
  }
}

// Uso
val client = AudioMonitorClient("192.168.1.100")
if (client.connect()) {
  client.setChannelVolume(0, 0.85f)
}
```

---

## 🔧 Troubleshooting de Protocolo

### WebSocket No Conecta

**Síntomas**: "Cannot connect to server"

**Checklist:**
```javascript
// 1. Verificar servidor corriendo
fetch('http://localhost:5100/').then(r => console.log(r))

// 2. Verificar CORS
// El servidor debe tener cors_allowed_origins="*"

// 3. Probar con curl
// curl -i http://localhost:5100/

// 4. Aumentar logging
localStorage.debug = 'socket.io-client:socket'
```

### Protocolo Nativo: Frames Corruptos

**Síntomas**: "Invalid magic number" frecuente

**Causas:**
- Desconexión durante transmisión
- Datos del stream overlapping
- Compresión/descompresión incorrecta

**Solución:**
```python
def receive_frame(socket):
    """Recibir frame con reintentos"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            header = socket.recv(16)
            if len(header) < 16:
                continue
            
            magic = struct.unpack('!I', header[0:4])[0]
            if magic != 0xA1D10A7C:
                logger.warning(f"Bad magic: {hex(magic)}")
                continue
            
            # ... resto del parsing
            return frame
        
        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {e}")
            socket.close()
            time.sleep(0.1)
    
    raise ConnectionError("Cannot receive valid frame")
```

### Reconexión RF No Funciona

**Síntomas**: Se reconecta pero pierde estado

**Verificar:**
```python
# 1. RF_MODE habilitado en cliente
print(config.RF_AUTO_RECONNECT)  # Debe ser True

# 2. State cache funcionando
print(f"Cached states: {len(state_cache.states)}")

# 3. Device ID consistente
print(device_id)  # Debe ser mismo entre reconexiones
```

---

**Última actualización**: Enero 2026  
**Versión Protocolos**: 1.0
