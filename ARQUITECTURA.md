# 🔧 ARQUITECTURA DEL SISTEMA - Componentes Detallados

## 📋 Tabla de Contenidos
1. [Audio Capture](#audio-capture)
2. [Channel Manager](#channel-manager)
3. [Audio Mixer](#audio-mixer)
4. [WebSocket Server](#websocket-server)
5. [Native Server](#native-server)
6. [Device Registry](#device-registry)
7. [Audio Compression](#audio-compression)
8. [Latency Optimizer](#latency-optimizer)

---

## 🎙️ Audio Capture
**Archivo**: [audio_server/audio_capture.py](audio_server/audio_capture.py)

### Responsabilidades
- Captura de audio en tiempo real usando `sounddevice` (PortAudio)
- Callback directo sin colas (optimización de latencia)
- Medición de VU meters (RMS + picos)
- Monitoreo de latencia

### Flujo Principal
```python
class AudioCapture:
    def __init__(self):
        self.stream = None           # Stream de sounddevice
        self.running = False         # Estado
        self.actual_channels = 0     # Canales del dispositivo
        self.callbacks = []          # Lista de callbacks directos
        self.audio_mixer = None      # Para mezcla del cliente maestro
        self.channel_manager = None  # Para manejo de suscripciones
        
        # VU Meters
        self.vu_callback = None
        self.vu_peak_hold = {}       # {channel: peak_value}
        
        # Latencia
        self.latency_measurements = [] # Últimas 100 mediciones
        self.stream_latency = 0.0
```

### Callback de Audio
```python
def audio_callback(indata, frames, time_info, status):
    """
    Llamada por PortAudio cada 10.67ms (64 samples @ 48kHz)
    - indata: ndarray de forma (64, 2) con datos de audio
    - frames: siempre 64
    - time_info: timestamp y latencia
    - status: flags de error/underrun
    """
    # 1. Copiar datos a numpy array local
    # 2. Medir latencia
    # 3. Invocar callbacks directos (sin encolado)
    # 4. Actualizar VU meters
```

### Características
- **Prioridad RT**: En Linux/macOS, eleva prioridad del thread
- **VU Meters**: Mide RMS + picos con decaimiento
- **Latencia**: Promedio dinámico de últimas 100 muestras
- **Flexibilidad**: Soporta mono/estéreo automáticamente

---

## 🎚️ Channel Manager
**Archivo**: [audio_server/channel_manager.py](audio_server/channel_manager.py)

### Responsabilidades
- Control centralizado de parámetros por canal (ganancia, pan, mute)
- Gestión de suscripciones de clientes
- Mapeo de dispositivos físicos a canales lógicos
- Cliente maestro para sonidista

### Estructura de Datos
```python
class ChannelManager:
    def __init__(self, num_channels):
        self.num_channels = num_channels  # Canales disponibles
        self.subscriptions = {}           # {client_id: {gains, pans, mutes}}
        self.client_types = {}            # {client_id: "native"|"web"|"master"}
        self.device_registry = None       # Mapeo de device_uuid -> client_id
```

### Parámetros por Canal
```python
CHANNEL_GAIN_MIN = 0.0      # -∞ dB (silencio)
CHANNEL_GAIN_MAX = 2.0      # +6 dB
CHANNEL_GAIN_DEFAULT = 1.0  # 0 dB
CHANNEL_PAN_MIN = -1.0      # Izquierda
CHANNEL_PAN_MAX = 1.0       # Derecha
```

### Métodos Principales
- `set_gain(client_id, channel, gain)`: Ajusta ganancia
- `set_pan(client_id, channel, pan)`: Panorama estéreo
- `set_mute(client_id, channel, mute)`: Silencia/desmuta
- `get_subscription(client_id)`: Obtiene parámetros del cliente
- `broadcast_state()`: Notifica cambios a todos los clientes

---

## 🎼 Audio Mixer
**Archivo**: [audio_server/audio_mixer.py](audio_server/audio_mixer.py)

### Responsabilidades
- Mezcla personalizada para cliente maestro
- Aplicación de ganancias y panoramas
- Envío de streaming de audio maestro vía WebSocket

### Caso de Uso
**Escenario**: Sonidista remoto quiere escuchar la mezcla final

```
Audio Input (48kHz, 2ch)
    ↓
Channel Manager aplica gains/pans por suscripción
    ↓
Audio Mixer combina canales según configuración maestro
    ↓
Comprime audio (zlib)
    ↓
Envía chunks vía WebSocket al cliente maestro
    ↓
Cliente maestro decodifica y reproduce en navegador
```

### Configuración
```python
MASTER_CLIENT_ENABLED = True         # Activar cliente maestro
MASTER_CLIENT_UUID = "__master_server_client__"
MASTER_AUDIO_SEND_INTERVAL = 100    # ms entre chunks enviados
MASTER_AUDIO_BUFFER_SIZE = 4800     # samples (100ms @ 48kHz)
```

---

## 🌐 WebSocket Server
**Archivo**: [audio_server/websocket_server.py](audio_server/websocket_server.py)

### Responsabilidades
- Servidor HTTP para servir UI web (Flask)
- Servidor WebSocket (SocketIO) para control en tiempo real
- Gestión de clientes web y maestro
- Broadcasting de estado de canales y VU meters

### Estructura
```python
app = Flask(__name__)                   # Servidor HTTP
socketio = SocketIO(app)               # WebSocket
ui_state = {                           # Estado global compartido
    'client_order': [],                # Orden de clientes en UI
    'updated_at': 0
}
```

### Eventos SocketIO

#### Cliente → Servidor
| Evento | Parámetros | Descripción |
|--------|-----------|-------------|
| `subscribe_channel` | `{channel_id, enabled}` | Suscribirse a canal |
| `set_gain` | `{channel, gain}` | Cambiar ganancia |
| `set_pan` | `{channel, pan}` | Cambiar panorama |
| `set_mute` | `{channel, mute}` | Silenciar/desmutear |
| `reorder_clients` | `{order: [ids]}` | Reordenar UI |

#### Servidor → Cliente
| Evento | Datos | Descripción |
|--------|-------|-------------|
| `channel_state` | Estado de todos los canales | Actualización batch |
| `vu_update` | `{channel, rms, peak}` | Medidores VU |
| `client_connected` | Datos de cliente conectado | Nuevo cliente registrado |
| `client_disconnected` | `client_id` | Cliente desconectado |
| `audio_chunk` | Buffer comprimido | Para cliente maestro |

### Rutas HTTP
- `GET /`: Sirve `frontend/index.html`
- `GET /assets/*`: Archivos estáticos (CSS, JS, iconos)
- `GET /manifest.json`: Manifiesto PWA
- `GET /sw.js`: Service Worker

---

## 📡 Native Server
**Archivo**: [audio_server/native_server.py](audio_server/native_server.py)

### Responsabilidades
- Servidor TCP/UDP para clientes Android nativos
- Recepción y envío de audio con protocolo binario
- Detección de clientes zombie
- Registro automático de nuevos dispositivos

### Flujo de Conexión
```
Android Device connects (TCP puerto 9999)
    ↓
Envía paquete "HELLO" con device_uuid
    ↓
Server registra en Device Registry
    ↓
Server envía config: num_channels, sample_rate, blocksize
    ↓
Audio streaming comienza (audio comprimido)
    ↓
Control events (gain/pan/mute) enviados vía UDP/TCP
    ↓
Si timeout sin datos: marcar como zombie
    ↓
Desconexión limpia
```

### Configuración
```python
NATIVE_SERVER_PORT = 9999              # Puerto TCP/UDP
NATIVE_HEARTBEAT_INTERVAL = 5          # segundos
NATIVE_HEARTBEAT_TIMEOUT = 15          # segundos
NATIVE_ZOMBIE_TIMEOUT = 30             # segundos
```

---

## 📋 Device Registry
**Archivo**: [audio_server/device_registry.py](audio_server/device_registry.py)

### Responsabilidades
- Mantener ID persistente para cada dispositivo
- Mapeo entre device_uuid (identificador único) y client_id (conexión actual)
- Persistencia en `config/devices.json`
- Historial de dispositivos conectados

### Estructura JSON (devices.json)
```json
{
  "device_uuid_example": {
    "device_name": "Samsung Galaxy Tab S7",
    "device_id": "Android_Device_001",
    "device_type": "native",
    "last_seen": 1704547200,
    "first_seen": 1704460800,
    "connection_count": 15
  }
}
```

### Flujo
```python
device_uuid = "ABC-123-XYZ"  # Enviado por cliente

if device_uuid in registry:
    # Dispositivo conocido
    device = registry[device_uuid]
    device['last_seen'] = now()
else:
    # Nuevo dispositivo
    device = create_new_device_entry(device_uuid)
    registry[device_uuid] = device
    
save_registry_to_disk()
```

---

## 🗜️ Audio Compression
**Archivo**: [audio_server/audio_compression.py](audio_server/audio_compression.py)

### Responsabilidades
- Compresión sin pérdida (zlib)
- Decompresión de audio recibido
- Medición de ratio de compresión

### Configuración
```python
ENABLE_OPUS_COMPRESSION = False    # Opus deshabilitado
COMPRESSION_LEVEL = 6              # zlib nivel 1-9 (balance velocidad/ratio)
```

### Métodos
```python
compress_audio(audio_buffer) -> bytes
    # Entrada: numpy array (samples, channels)
    # Salida: bytes comprimidos
    # zlib comprime ~10:1 típicamente

decompress_audio(compressed_data) -> ndarray
    # Entrada: bytes comprimidos
    # Salida: numpy array original
```

---

## ⚙️ Latency Optimizer
**Archivo**: [audio_server/latency_optimizer.py](audio_server/latency_optimizer.py)

### Responsabilidades
- Monitoreo automático de latencia
- Ajuste dinámico de parámetros
- Recomendaciones de configuración

### Métricas Monitoreadas
```python
LATENCY_METRICS = {
    'audio_callback_latency': float,      # ms de callback
    'socketio_broadcast_latency': float,  # ms de broadcast
    'native_send_latency': float,         # ms de envío a Android
    'overall_latency': float               # Total
}
```

### Estrategias de Optimización
1. **Si latencia > 50ms**:
   - Reducir queue sizes
   - Aumentar número de worker threads
   - Reducir buffer de VU meters

2. **Si latencia > 100ms**:
   - Desactivar broadcasts innecesarios
   - Aumentar debounce de cambios
   - Considerar reducir blocksize (si CPU permite)

---

## 🔗 Interconexión de Componentes

```
┌─────────────────────────────────────────────────────────┐
│                    MAIN LOOP                             │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Audio Input Stream (PortAudio)                          │
│         ↓                                                 │
│  AudioCapture.callback()                                 │
│         ↓                                                 │
│  ChannelManager.process_subscription()                   │
│         ├→ Aplica gains/pans/mutes                       │
│         └→ Determina qué enviar a qué cliente            │
│         ↓                                                 │
│  Para cada cliente:                                      │
│  ├→ Si Android native:                                   │
│  │  └→ NativeServer.send_audio() (comprimido)            │
│  ├→ Si Web UI:                                           │
│  │  └→ socketio.emit('channel_state')                    │
│  ├→ Si Master:                                           │
│  │  ├→ AudioMixer.mix_channels()                         │
│  │  └→ socketio.emit('audio_chunk') (streaming)          │
│  └→ Actualizar VU meters si interval vencido             │
│         ↓                                                 │
│  ThreadPoolExecutor paralleliza envíos (6 hilos)         │
│         ↓                                                 │
│  LatencyOptimizer registra tiempos                       │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Diagrama de Estados de Cliente

```
                    ┌──────────────────┐
                    │   DISCONNECTED   │
                    └────────┬─────────┘
                             │
                    Conexión recibida
                             │
                             ↓
                    ┌──────────────────┐
                    │  REGISTERING     │
                    │ (HelloPacket)    │
                    └────────┬─────────┘
                             │
                    Device Registry OK
                             │
                             ↓
                    ┌──────────────────┐
                    │   CONNECTED      │───→ Audio Streaming
                    │ (Activo)         │───→ Recibe control events
                    └────────┬─────────┘
                             │
                  Sin datos por 15s
                             │
                             ↓
                    ┌──────────────────┐
                    │   ZOMBIE         │
                    │ (Inactivo)       │
                    └────────┬─────────┘
                             │
                  Sin datos por 30s
                             │
                             ↓
                    ┌──────────────────┐
                    │  DISCONNECTED    │
                    └──────────────────┘
```

---

## 🔐 Persistencia de Estado

### Archivos de Configuración

1. **config/devices.json**
   - Registro de todos los dispositivos vistos
   - Actualizado en tiempo real cada vez que conecta un dispositivo

2. **config/channels_state.json**
   - Ganancia, pan, mute de cada canal
   - Restaurados al iniciar el servidor

3. **config/client_states.json**
   - Historial de clientes (para estadísticas)

4. **config/web_ui_state.json**
   - Orden de clientes en la interfaz web
   - Persistido cuando usuario reordena clientes

---

## ⚡ Optimizaciones Clave

1. **Callbacks directos**: Sin colas, invoke callbacks directamente
2. **ThreadPoolExecutor**: Paraleliza envío a múltiples clientes (6 hilos)
3. **Debouncing**: Agrupa cambios frecuentes (50ms por defecto)
4. **Streaming vs Control**: Canales separados para audio (stream) y control (eventos)
5. **Compresión**: zlib para reducir bandwidth ~10:1
6. **Prioridad RT**: En Linux, eleva priority del audio thread
7. **Medición dinámica**: Latency optimizer ajusta parámetros automáticamente

