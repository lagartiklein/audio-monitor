# 🎯 Guía Rápida de Referencia

Resumen ejecutivo y cheatsheet para desarrollo rápido.

---

## ⚡ Instalación en 1 Minuto

```bash
# Clonar + configurar
git clone <repo>
cd audio-monitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Ejecutar
python main.py
```

**Resultado**: Servidor corriendo en `http://localhost:5100`

---

## 🎙️ Especificaciones de Audio

```
Frecuencia:        48 kHz
Formato:           32-bit float
Blocksize:         32 muestras (0.67ms latencia)
Canales:           Hasta 32
Compresión:        zlib nivel 1
Bandwidth/cliente: 1.8-2.3 Mbps
```

---

## 🌐 Puertos de Escucha

```
5100  → WebSocket (Web UI + clientes JavaScript)
5101  → Protocolo Nativo (Android/iOS)
```

---

## 📡 WebSocket: Eventos Rápidos

### Servidor → Cliente
```javascript
// Estadísticas
socket.on('server_stats', {cpu, memory, latency, active_clients})

// Estado de canales
socket.on('channel_list', [{id, volume, pan, mute, ...}])

// Cambios
socket.on('channel_volume_changed', {channel_id, volume})
socket.on('channel_pan_changed', {channel_id, pan})
socket.on('channel_mute_changed', {channel_id, mute})

// Audio
socket.on('audio_data', {data, shape, timestamp})
```

### Cliente → Servidor
```javascript
socket.emit('set_channel_volume', {channel_id, volume})     // 0-2
socket.emit('set_channel_pan', {channel_id, pan})            // -1 a +1
socket.emit('set_channel_mute', {channel_id, mute})          // true/false
socket.emit('select_channel', {channel_id})
socket.emit('get_device_list', {})
socket.emit('get_server_stats', {})
```

---

## 📦 Protocolo Nativo: Frame Format

```
Header (16 bytes):
┌─────────────────────────────────┐
│ Magic:    0xA1D10A7C (4 bytes)  │
│ Version:  2 (2 bytes)           │
│ Type:     0x01=Audio (2 bytes)  │
│ Flags:    0x01=Float, 0x04=Zip  │
│ Size:     Payload length (4 bytes)
└─────────────────────────────────┘

Audio Payload:
Num Channels (1) + Num Samples (2) + [CH0 float32, CH1 float32, ...]
```

---

## 🔧 Configuración Principal (config.py)

```python
# Audio
BLOCKSIZE = 32                    # ← Más pequeño = menos latencia
DEFAULT_SAMPLE_RATE = 48000

# Red
WEB_PORT = 5100
NATIVE_PORT = 5101
NATIVE_MAX_CLIENTS = 10

# Optimización
AUDIO_SEND_POOL_SIZE = 6          # Threads de envío
SOCKET_NODELAY = True             # Deshabilitar Nagle
SOCKET_TIMEOUT = 3.0

# RF Mode
RF_AUTO_RECONNECT = True
RF_RECONNECT_DELAY_MS = 1000
RF_STATE_CACHE_TIMEOUT = 0        # 0 = permanente
```

---

## 🏗️ Componentes Clave

### AudioCapture
```python
from audio_server.audio_capture import AudioCapture
capture = AudioCapture()
capture.start()
capture.register_callback(my_callback)
```

### ChannelManager
```python
from audio_server.channel_manager import ChannelManager
manager = ChannelManager()
manager.set_channel_volume(channel_id=0, volume=0.85)
manager.set_channel_pan(channel_id=0, pan=-0.5)
manager.set_channel_mute(channel_id=0, mute=False)
```

### WebSocket Server
```python
from audio_server.websocket_server import app, socketio
socketio.run(app, host='0.0.0.0', port=5100)
```

### Native Server
```python
from audio_server.native_server import NativeAudioServer
native = NativeAudioServer()
native.start()
```

---

## 🐛 Troubleshooting Rápido

| Problema | Solución |
|----------|----------|
| **No hay audio** | Verificar dispositivo: `sd.query_devices()` |
| **Alta latencia** | Reducir `BLOCKSIZE = 16`, aumentar `AUDIO_SEND_POOL_SIZE` |
| **CPU alto** | Deshabilitar logs, reducir procesamiento |
| **Clientes no conectan** | Verificar firewall puerto 5100-5101 |
| **Audio cortado** | Aumentar buffer: `WEB_QUEUE_SIZE = 4` |
| **Memoria crece** | Limpiar cache: `RF_MAX_PERSISTENT_STATES = 20` |

---

## 💻 Cliente JavaScript (WebSocket)

```javascript
const socket = io('http://localhost:5100');

socket.on('connect', () => {
  console.log('Conectado');
});

socket.on('server_stats', (stats) => {
  console.log(`Latencia: ${stats.latency}ms`);
});

// Cambiar volumen
document.getElementById('volume').addEventListener('input', (e) => {
  socket.emit('set_channel_volume', {
    channel_id: 0,
    volume: parseFloat(e.target.value)
  });
});

// Escuchar cambios
socket.on('channel_volume_changed', (data) => {
  console.log(`Vol: ${data.volume}`);
});
```

---

## 📱 Cliente Android (Protocolo Nativo)

```kotlin
val socket = Socket("192.168.1.100", 5101)
val input = socket.inputStream

// Leer frame
val header = ByteArray(16)
input.read(header)

val magic = ByteBuffer.wrap(header, 0, 4).int
val version = ByteBuffer.wrap(header, 4, 2).short
val msgType = ByteBuffer.wrap(header, 6, 2).short
val flags = ByteBuffer.wrap(header, 8, 4).int
val payloadSize = ByteBuffer.wrap(header, 12, 4).int

// Leer payload
val payload = ByteArray(payloadSize)
input.read(payload)

// Descomprimir si es necesario
if (flags and 0x04 != 0) {
  val inflater = Inflater()
  inflater.setInput(payload)
  val decompressed = ByteArray(2048)
  val size = inflater.inflate(decompressed)
}
```

---

## 📊 Monitoreo

### Estadísticas en Vivo
```python
# Desde GUI
# Ver: CPU, Memoria, Latencia, Clientes activos

# Desde código
from audio_server.latency_optimizer import LatencyMonitor
monitor = LatencyMonitor()
stats = monitor.get_stats()  # {avg, min, max, p99}
```

### Logs
```
logs/
├─ audio_monitor.log      # General
├─ websocket.log          # WebSocket events
└─ native_protocol.log    # Protocolo nativo
```

---

## 🚀 Compilar a EXE

```bash
# Con spec file
python -m PyInstaller FichatechMonitor.spec

# O directo
python -m PyInstaller --onefile --name FichatechMonitor main.py
```

**Resultado**: `release/FichatechMonitor.exe`

---

## 🔐 Seguridad Básica

```python
# Firewall: Limitar acceso a puertos
# En Windows: netsh advfirewall firewall add rule ...

# SSL/TLS: Usar en producción
# Implementar con reverse proxy (nginx)

# Autenticación: Implementar token si es necesario
# En WebSocket: socket.on('connect', auth={token})
```

---

## 📚 Jerarquía de Archivos

```
audio-monitor/
├── main.py                 # Entry point
├── config.py              # Configuración
├── gui_monitor.py         # GUI
├── audio_server/
│   ├── audio_capture.py    # Captura
│   ├── channel_manager.py  # Canales
│   ├── audio_mixer.py      # Mezcla
│   ├── websocket_server.py # Web
│   ├── native_server.py    # Nativo
│   └── native_protocol.py  # Protocolo
├── frontend/              # HTML/CSS/JS
│   ├── index.html
│   └── manifest.json
└── config/
    ├── channels_state.json
    ├── client_states.json
    └── devices.json
```

---

## 🎯 Workflow Típico

### 1. Desarrollo Local
```bash
python main.py              # Inicia servidor + GUI
# Abre http://localhost:5100 en navegador
# Prueba cambios en tiempo real
```

### 2. Testing
```bash
# Conectar cliente Android/iOS al puerto 5101
# Verificar audio transmitido
# Monitorear latencia desde GUI
```

### 3. Producción
```bash
# Compilar EXE
python -m PyInstaller FichatechMonitor.spec

# Distribuir FichatechMonitor.exe
# Configurar firewall en servidor
# Documentar conexión de clientes
```

---

## ⚙️ Parámetros de Ajuste Fino

### Para Baja Latencia (Live)
```python
BLOCKSIZE = 16                   # Ultra-pequeño
AUDIO_SEND_POOL_SIZE = 8         # Más threads
SOCKET_NODELAY = True
WEBSOCKET_PARAM_DEBOUNCE_MS = 25  # Menos delay
```

### Para Estabilidad (Studio)
```python
BLOCKSIZE = 128                  # Más grande
AUDIO_SEND_POOL_SIZE = 4
WEB_QUEUE_SIZE = 4               # Más buffer
NATIVE_HEARTBEAT_TIMEOUT = 300   # Más tolerancia
```

### Para Bajo CPU
```python
# Sin compresión (Opus removido)
AUDIO_SEND_POOL_SIZE = 2
WEBSOCKET_LATENCY_LOG = False
logger.setLevel(logging.WARNING)
```

---

## 🔗 APIs Importantes

### AudioCapture
```python
start()                    # Iniciar captura
stop()                     # Detener
register_callback(func)    # Registrar callback
validate_audio_data(data)  # Validar
```

### ChannelManager
```python
set_channel_volume(id, vol)     # 0-2
set_channel_pan(id, pan)         # -1 a 1
set_channel_mute(id, mute)       # bool
get_channel_state(id)            # dict
broadcast_state_change()         # notificar todos
```

### WebSocket
```python
@socketio.on('connect')
@socketio.on('disconnect')
@socketio.on('event_name')
socketio.emit('event', data)     # enviar
socketio.emit('event', data, skip_sid=sid)  # broadcast
```

---

## 📊 Performance Targets

```
CPU:       < 15% (normal), < 30% (max)
Memory:    150-200 MB base
Latencia:  < 100ms (normal), < 50ms (optimizado)
Clientes:  50+ simultáneos
Throughput: 2.3 Mbps por cliente @ 48kHz 2ch
```

---

## 🆘 Contactos Rápidos

- **Issues**: GitHub repository
- **Documentación**: INDICE.md
- **Técnico Avanzado**: GUIA_TECNICA.md
- **Protocolos**: PROTOCOLOS.md
- **Legal**: POLITICAS.md

---

**Última actualización**: Enero 2026
**Versión**: 1.0

