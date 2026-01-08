# 🏗️ Arquitectura - Fichatech Audio Monitor

Documentación técnica detallada de la arquitectura del sistema, componentes, flujos de datos y diseño de la aplicación.

---

## 📖 Tabla de Contenidos

- [Visión General](#visión-general)
- [Componentes Principales](#componentes-principales)
- [Capas del Sistema](#capas-del-sistema)
- [Flujo de Datos](#flujo-de-datos)
- [Gestión de Conexiones](#gestión-de-conexiones)
- [Patrón de Callbacks](#patrón-de-callbacks)
- [Escalabilidad](#escalabilidad)

---

## 🎯 Visión General

Fichatech Audio Monitor es una aplicación **multi-capas** que captura audio en tiempo real, lo procesa y lo distribuye a múltiples clientes a través de diferentes protocolos de comunicación:

```
┌─────────────────────────────────────────────────────────────┐
│                     CAPA PRESENTACIÓN                        │
│          GUI (CustomTkinter) + Web UI (HTML/JS)             │
└──────────────┬──────────────────────────────┬────────────────┘
               │                              │
        ┌──────▼────────┐          ┌──────────▼──────────┐
        │  GUI Monitor  │          │  WebSocket Server   │
        │  (Stats)      │          │  (Flask + Socket.IO)│
        └──────┬────────┘          └──────────┬──────────┘
               │                              │
        ┌──────▼───────────────────────────────▼──────────┐
        │       CAPA DE SERVICIOS (AudioServerApp)        │
        │  - Coordinación general                         │
        │  - Gestión de hilos y ciclo de vida             │
        └──────┬──────────────┬──────────────┬────────────┘
               │              │              │
    ┌──────────▼──┐  ┌────────▼────┐  ┌──────▼─────┐
    │   CAPTURA   │  │  GESTIÓN    │  │ PROTOCOLO  │
    │   DE AUDIO  │  │  DE CANALES │  │  NATIVO    │
    └─────────────┘  └─────────────┘  └────────────┘
               │              │              │
        ┌──────▼───────────────────────────────▼──────────┐
        │        CAPA DE TRANSPORTE (Red)                │
        │  - WebSocket (puerto 5100)                     │
        │  - Protocolo Binario (puerto 5101)            │
        └───────────────────────────────────────────────┘
               │              │              │
        ┌──────▼────┐  ┌──────▼────┐  ┌──────▼────┐
        │   Clientes│  │   Clientes│  │   Clientes│
        │    Web    │  │   Android │  │    iOS    │
        └───────────┘  └───────────┘  └───────────┘
```

---

## 🔧 Componentes Principales

### 1. **AudioCapture** (`audio_capture.py`)
Motor central de captura de audio.

**Responsabilidades:**
- Inicializar dispositivos de audio con sounddevice
- Capturar samples en tiempo real
- Gestionar prioridad en tiempo real (RT)
- Mantener callbacks directos sin colas
- Analizar niveles con VU meters

**Características Técnicas:**
```python
class AudioCapture:
    # Captura @ 48kHz, blocksize 32
    stream: sd.RawInputStream
    actual_channels: int  # Canales reales del dispositivo
    callbacks: List[Callable]  # Callbacks directos
    
    def callback(indata, frames, time, status):
        # Procesa samples recibidos
        # Llama todos los callbacks registrados
        # Análisis de niveles VU
```

**Flujo:**
1. Stream de Sounddevice dispara callback cada 32 muestras
2. AudioCapture procesa samples y llama callbacks
3. Channel Manager recibe samples
4. Mixer prepara para streaming
5. WebSocket + Protocolo Nativo distribuyen

---

### 2. **ChannelManager** (`channel_manager.py`)
Gestiona múltiples canales de audio de forma independiente.

**Responsabilidades:**
- Registrar/desregistrar canales
- Mantener estado de cada canal (volumen, pan, mute, etc)
- Procesar parámetros por canal
- Notificar cambios de estado
- Manejo de permisos por cliente

**Estructura de Datos:**
```python
class ChannelManager:
    channels: Dict[int, Channel]  # {channel_id: Channel}
    
    # Cada canal tiene:
    # - volume: float [0-1]
    # - pan: float [-1, 1]
    # - mute: bool
    # - selected: bool
    # - monitor: bool
```

---

### 3. **AudioMixer** (`audio_mixer.py`)
Mezcla multiple canales en flujo maestro.

**Responsabilidades:**
- Combinar múltiples canales en mono/estéreo
- Aplicar controles globales
- Resamplear si es necesario
- Preparar buffer final para transmisión

**Algoritmo:**
```
Para cada muestra:
  1. Obtener samples de todos los canales activos
  2. Aplicar volumen individual
  3. Aplicar pan
  4. Mezclar a estéreo/mono
  5. Aplicar compresión limitador
  6. Enviar a WebSocket/Native
```

---

### 4. **WebSocket Server** (`websocket_server.py`)
Servidor Flask + Socket.IO para comunicación web.

**Responsabilidades:**
- Servir interfaz web HTML/CSS/JS
- Mantener conexiones WebSocket con clientes
- Recibir comandos de control
- Broadcast de estado del servidor
- Envío de audio a clientes conectados

**Endpoints:**
```javascript
// Eventos Socket.IO
socket.on('connect')              // Cliente conectado
socket.on('set_channel_volume')   // Cambio de volumen
socket.on('set_channel_pan')      // Cambio de pan
socket.on('device_list')          // Solicita lista de devices
socket.on('server_stats')         // Solicita estadísticas
```

---

### 5. **Native Protocol Server** (`native_server.py` + `native_protocol.py`)
Servidor TCP binario para clientes nativos (Android/iOS).

**Responsabilidades:**
- Escuchar conexiones en puerto 5101
- Parsear protocolo binario nativo
- Enviar audio comprimido
- Sincronizar estado con clientes
- Implementar Modo RF (reconexión automática)

**Protocolo:**
```
Header (16 bytes):
┌──────────┬───────┬────────┬────────┬──────────┐
│  Magic   │Version│ Type   │ Flags  │ Payload  │
│  4 bytes │2 bytes│2 bytes │4 bytes │  size    │
│ 0xA1D1.  │  2    │ 0x01   │ 0x01   │ N bytes  │
│ 0xA7C    │       │(Audio) │(Float) │          │
└──────────┴───────┴────────┴────────┴──────────┘

Audio Payload (variable):
- Número de canales (1 byte)
- Número de muestras (2 bytes)
- Datos de audio (N * channels * 4 bytes)
```

---

### 6. **Device Registry** (`device_registry.py`)
Gestión de dispositivos de audio disponibles.

**Responsabilidades:**
- Enumerar dispositivos de entrada/salida
- Validar dispositivos soportados
- Caché de dispositivos
- Notificar cambios de dispositivos

**Datos Almacenados:**
```json
{
  "devices": [
    {
      "id": 0,
      "name": "Micrófono Builtin",
      "channels": 2,
      "sample_rate": 48000,
      "latency": "low"
    }
  ]
}
```

---

### 7. **AudioServerApp** (Orquestador Principal)
Coordinador central que inicializa y gestiona todos los componentes.

**Flujo de Inicialización:**
```python
def __init__():
    # 1. Inicializar registry de devices
    init_device_registry()
    
    # 2. Inicializar captura de audio
    self.audio_capture = AudioCapture()
    
    # 3. Inicializar gestor de canales
    self.channel_manager = ChannelManager()
    
    # 4. Inicializar mixer
    audio_mixer = init_audio_mixer()
    
    # 5. Inicializar WebSocket
    init_server()
    
    # 6. Inicializar servidor nativo
    self.native_server = NativeAudioServer()
    
    # 7. Inicializar GUI
    self.gui = AudioMonitorGUI()

def run():
    # 1. Iniciar captura de audio
    self.audio_capture.start()
    
    # 2. Iniciar servidor WebSocket en thread
    threading.Thread(target=run_web_server).start()
    
    # 3. Iniciar servidor nativo en thread
    self.native_server.start()
    
    # 4. Iniciar GUI (bloquea hasta cerrar)
    self.gui.run()
    
    # 5. Cleanup
    self.cleanup()
```

---

### 8. **GUI Monitor** (`gui_monitor.py`)
Interfaz gráfica de monitoreo con CustomTkinter.

**Componentes Visuales:**
- **Panel de Control**: Inicio/parada de servidor
- **Estadísticas en Vivo**: CPU, memoria, latencia
- **Información de Clientes**: Activos y conectados
- **Logs**: Eventos importantes del servidor
- **Control Web**: Botón para abrir interfaz web

---

## 🔄 Capas del Sistema

### Capa 1: Captura (Hardware)
- Dispositivo de audio → Sounddevice
- Callbacks de hardware directos
- Prioridad RT configurada

### Capa 2: Procesamiento (Audio)
- AudioCapture → ChannelManager
- ChannelManager → AudioMixer
- Aplicación de efectos/parámetros

### Capa 3: Servicios (Lógica)
- Gestión de conexiones
- Control de flujo
- Cache y persistencia (RF Mode)

### Capa 4: Transporte (Red)
- WebSocket (HTTP + WS)
- Protocolo Binario (TCP)
- Compresión zlib

### Capa 5: Presentación (Cliente)
- Web UI (HTML/CSS/JS)
- Apps Nativas (Android/iOS)

---

## 📊 Flujo de Datos

### Flujo de Audio (End-to-End)

```
1. CAPTURA
   ┌─────────────────┐
   │ Dispositivo Hw  │
   └────────┬────────┘
            │ 32 samples @ 48kHz
            ▼
   ┌─────────────────┐
   │ Sounddevice     │
   └────────┬────────┘
            │ Callback dispara
            ▼
2. PROCESAMIENTO PRIMARIO
   ┌─────────────────────┐
   │ AudioCapture        │
   │ - VU Analysis       │
   │ - Channel Dispatch  │
   └────────┬────────────┘
            │
            ▼
   ┌─────────────────────┐
   │ ChannelManager      │
   │ - Apply Volume      │
   │ - Apply Pan         │
   │ - Routing           │
   └────────┬────────────┘
            │
            ▼
3. MEZCLA
   ┌─────────────────────┐
   │ AudioMixer          │
   │ - Mix Channels      │
   │ - Apply Master Vol  │
   │ - Stereo/Mono Conv  │
   └────────┬────────────┘
            │
            ▼
4. COMPRESIÓN
   ┌─────────────────────┐
   │ Audio Compression   │
   │ - zlib Compress     │
   │ - 512→200 bytes     │
   └────────┬────────────┘
            │
            ▼
5. DISTRIBUCIÓN
   ├─────────────────┬──────────────┐
   │                 │              │
   ▼                 ▼              ▼
   WebSocket      Native Protocol  Local Monitor
   (Web Clients) (Android/iOS)     (Stats)
```

---

## 🔌 Gestión de Conexiones

### WebSocket Connections

```
Cliente Web conecta → /
                     ↓
              Socket.IO handshake
                     ↓
           Emitir eventos bidireccionales
                     ↓
    Servidor envía: server_stats, audio_data
    Cliente envía: commands, parameter_changes
                     ↓
         Cliente desconecta o timeout
```

### Native Protocol Connections

```
Cliente nativo conecta → :5101 (TCP)
                         ↓
                    Recibe header
                         ↓
                  Valida magic number
                         ↓
         Recibe payload de audio
                         ↓
         Descomprime y renderiza
                         ↓
     Reconnect automático en timeout
         (RF Mode habilitado)
```

---

## 🔄 Patrón de Callbacks

Fichatech usa un patrón de **callbacks directo** para máxima baja latencia:

```python
# Sin colas intermedias
AudioCapture → [callback1, callback2, ...] → ChannelManager
                                          → WebSocket
                                          → Native
```

**Ventajas:**
- ✅ Latencia mínima (sin buffering extra)
- ✅ Determinismo (predictable timing)
- ✅ CPU eficiente (sin thread switching)

**Desventajas:**
- ⚠️ Los callbacks deben ser rápidos
- ⚠️ No hay recuperación de fallos
- ⚠️ Una excepción rompe todo el pipeline

**Manejo de Errores:**
```python
def safe_callback_dispatch(sample_data):
    for callback in self.callbacks:
        try:
            callback(sample_data)
        except Exception as e:
            logger.error(f"Callback error: {e}")
            # Continua con siguiente callback
```

---

## 📈 Escalabilidad

### Soporte Multi-Cliente

**WebSocket:**
- Unlimited (limitado por memoria)
- Broadcast eficiente con Socket.IO

**Protocolo Nativo:**
- Configurable: `NATIVE_MAX_CLIENTS = 10`
- ThreadPool paralelo: `AUDIO_SEND_POOL_SIZE = 6`
- Cada cliente obtiene stream de audio individual

### Escalamiento de Canales

```
1 dispositivo → N canales → ChannelManager
                                ↓
                           N callbacks simultáneos
                                ↓
                           Mixer (combina a stereo)
                                ↓
                           1 stream de salida
```

### Optimizaciones Aplicadas

1. **ThreadPool para envío**: Paraleliza distribución de audio
2. **Debouncing**: Agrupa comandos en ventanas de 50ms
3. **Batch updates**: WebSocket envía lotes, no mensajes individuales
4. **Compresión selectiva**: Solo comprime si payload > threshold
5. **Detección de zombies**: Cierra conexiones muertas rápidamente

---

## 🔐 Seguridad

### Aislamiento de Componentes

```
┌─ Audio Capture (RT Priority)
├─ Channel Manager (Thread-safe)
├─ WebSocket (Async per client)
├─ Native Server (Per-client TCP)
└─ GUI (Main thread)

Sincronización:
- Locks para acceso compartido
- Queues para cross-thread communication
- Event flags para señales
```

### Validación de Datos

```python
# Protocolo nativo: Validar header
if header.magic != MAGIC_NUMBER:
    reject_connection()

# WebSocket: Validar JSON
try:
    data = json.loads(event_data)
except json.JSONDecodeError:
    reject_event()

# Parámetros: Validar rango
if not 0 <= volume <= 1:
    clamp_to_range()
```

---

## 🚀 Optimizaciones de Latencia

### Latencia Total = Captura + Procesamiento + Transmisión + Renderizado

```
Captura:       ~0.67ms  (32 samples @ 48kHz)
Procesamiento: ~1-2ms   (callback chain)
Transmisión:   ~20-50ms (red, depende del WiFi)
Renderizado:   ~10-20ms (buffer client)
─────────────────────────────────────
TOTAL:         ~50-100ms end-to-end
```

### Estrategias de Optimización

1. **Blocksize pequeño** (32 vs 512): -15ms latencia
2. **Callbacks directos** (sin queues): -5ms latencia
3. **Compresión mínima** (zlib level 1): -2ms latencia
4. **ThreadPool paralelo**: Reduce bottleneck de envío
5. **Sockets TCP_NODELAY**: Deshabilita Nagle algorithm

---

## 📝 Estructura de Directorios

```
audio-monitor/
├── main.py                  # Entry point
├── config.py               # Configuración global
├── gui_monitor.py          # GUI CustomTkinter
├── audio_server/           # Módulo principal
│   ├── __init__.py
│   ├── audio_capture.py    # Sounddevice capture
│   ├── channel_manager.py  # Gestión de canales
│   ├── audio_mixer.py      # Mezcla de audio
│   ├── device_registry.py  # Enum de dispositivos
│   ├── native_server.py    # Servidor TCP
│   ├── native_protocol.py  # Protocolo binario
│   ├── websocket_server.py # Flask + Socket.IO
│   ├── latency_optimizer.py # Optimizaciones RT
│   └── web_identity.py     # Client identification
├── frontend/               # Web UI
│   ├── index.html
│   ├── styles.css
│   ├── sw.js              # Service Worker
│   └── heartbeat-worker.js
├── config/                 # Datos persistentes
│   ├── channels_state.json
│   ├── client_states.json
│   └── devices.json
├── logs/                   # Logs de ejecución
└── recordings/            # Audio grabado
```

---

## 🔗 Interacciones Principales

### Inicio del Sistema
```
main.py
  ↓
AudioServerApp.__init__()
  ├→ init_device_registry()
  ├→ AudioCapture.start()
  │  └→ sounddevice stream callback registered
  ├→ ChannelManager()
  ├→ init_audio_mixer()
  ├→ init_server() [WebSocket]
  ├→ NativeAudioServer.start()
  └→ AudioMonitorGUI().run()
```

### Recepción de Audio
```
Sounddevice callback
  ↓
AudioCapture.callback()
  ├→ For each registered callback:
  │  ├→ ChannelManager.process_samples()
  │  │  ├→ For each active channel:
  │  │  │  └→ Apply volume, pan, effects
  │  │  └→ Queue para WebSocket
  │  └→ NativeServer.queue_audio()
  └→ Stats/VU update
```

### Comando de Control
```
Cliente Web emite: set_channel_volume(3, 0.75)
  ↓
WebSocket receive event
  ↓
ChannelManager.set_channel_volume(3, 0.75)
  ↓
Broadcast: volume_changed event
  ├→ Todos los clientes Web actualizados
  └→ Clientes Nativos notificados (next batch)
```

---

## 📌 Principios de Diseño

1. **Baja Latencia**: Callbacks directos, sin colas
2. **Escalabilidad**: ThreadPool para clientes, modular
3. **Robustez**: Manejo de errores, timeouts, reconexión
4. **Configurabilidad**: Todo en `config.py`
5. **Monitoreabilidad**: Logging, stats, GUI
6. **Compatibilidad**: Cross-platform (Win/Linux/Mac teórico)

---

**Última actualización**: Enero 2026  
**Versión Arquitectura**: 2.0
