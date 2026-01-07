# 📊 ANÁLISIS - Fichatech Audio Monitor

## 🎯 Propósito General

**Fichatech Audio Monitor** es un servidor de audio profesional multiplataforma que permite:

- **Captura de audio** en tiempo real desde dispositivos de entrada (micrófono, interfaz de audio)
- **Transmisión de audio** a múltiples clientes simultáneamente (aplicaciones Android nativas, navegadores web)
- **Control remoto centralizado** de parámetros de audio (ganancia, pan, mute) desde una interfaz web
- **Monitoreo visual** en tiempo real con medidores VU y estadísticas de latencia
- **Ultra-baja latencia** optimizada para aplicaciones profesionales RF (radiofrecuencia)

---

## 🏗️ Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                    FICHATECH MONITOR                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          CAPA DE CAPTURA DE AUDIO                    │   │
│  │  (audio_capture.py)                                  │   │
│  │  - Captura: sounddevice (PortAudio)                  │   │
│  │  - Rate: 48kHz, BlockSize: 64 samples (10.67ms)    │   │
│  │  - Canales: 2 (estéreo) o mono configurable          │   │
│  │  - Callbacks VU meters y análisis de latencia        │   │
│  └──────────────────────────────────────────────────────┘   │
│                           ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         CAPA DE PROCESAMIENTO DE AUDIO               │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ Channel Manager (control de canales)          │   │   │
│  │  │ - Ganancia, pan, mute por cliente            │   │   │
│  │  │ - Subscripciones selectivas de canales       │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ Audio Mixer (mezcla por cliente maestro)      │   │   │
│  │  │ - Mezcla personalizada para sonidista         │   │   │
│  │  │ - Monitor vía web de mezcla final             │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ Audio Compression (zlib)                      │   │   │
│  │  │ - Compresión sin pérdida (Opus deshabilitado)│   │   │
│  │  │ - Reducción ancho de banda                    │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ Device Registry & Latency Optimizer            │   │   │
│  │  │ - ID persistente de dispositivos              │   │   │
│  │  │ - Optimización automática de latencia         │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                           ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           CAPA DE TRANSMISIÓN DE RED                 │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ WebSocket Server (Flask-SocketIO)             │   │   │
│  │  │ - Control web desde navegador                 │   │   │
│  │  │ - Broadcast de estado de canales              │   │   │
│  │  │ - Streaming de audio (cliente maestro)        │   │   │
│  │  │ - Puerto: 5000 (configurable)                │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ Native Protocol Server (TCP/UDP)              │   │   │
│  │  │ - Protocolo binario personalizado             │   │   │
│  │  │ - Recepción de audio desde Android nativo     │   │   │
│  │  │ - Transmisión de control a dispositivos       │   │   │
│  │  │ - Puerto: 9999 (configurable)                │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                           ↓                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              CAPA DE PRESENTACIÓN                    │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ GUI Desktop (customtkinter)                   │   │   │
│  │  │ - Monitor local de estadísticas              │   │   │
│  │  │ - Inicio/parada del servidor                 │   │   │
│  │  │ - Visualización de clientes conectados       │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │ Web UI (PWA - Aplicación Web Progresiva)     │   │   │
│  │  │ - Frontend: HTML/CSS/JS en 'frontend/'       │   │   │
│  │  │ - Control de canales en tiempo real          │   │   │
│  │  │ - Monitor maestro de mezcla                  │   │   │
│  │  │ - Compatible con móvil (iOS/Android browser) │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📱 Tipos de Clientes

### 1️⃣ **Clientes Android Nativos**
- **Conexión**: TCP/UDP con protocolo binario personalizado
- **Rol**: Receptores de audio (dispositivos RF remotos)
- **Datos enviados**: 
  - Audio capturado (48kHz, 16-bit o 32-bit float comprimido)
  - Controles de ganancia y panorama
- **Uso**: Transmisión de audio a equipos remotos vía RF

### 2️⃣ **Web UI (navegador)**
- **Conexión**: WebSocket (Socket.IO)
- **Rol**: Control remoto y monitoreo
- **Funciones**:
  - Ajustar ganancia, pan, mute de canales
  - Visualizar VU meters en tiempo real
  - Ver estado de clientes conectados
  - Acceso desde PC/Tablet/Móvil

### 3️⃣ **Cliente Maestro (Sonidista)**
- **Conexión**: WebSocket + Streaming de audio
- **Rol**: Monitor profesional del audio mezclado
- **Funciones**:
  - Escuchar mezcla final en tiempo real
  - Crear mezclas personalizadas por canal
  - Control centralizado de todos los parámetros

---

## 📂 Estructura de Directorios

```
audio-monitor/
├── main.py                          # ⭐ Punto de entrada principal
├── config.py                        # 🔧 Configuración global del sistema
├── gui_monitor.py                   # 🖥️ GUI Desktop (customtkinter)
│
├── audio_server/                    # 🎵 Núcleo de servidor de audio
│   ├── audio_capture.py             # Captura de audio (sounddevice)
│   ├── audio_compression.py         # Compresión zlib
│   ├── audio_mixer.py               # Mezcla de audio por cliente
│   ├── channel_manager.py           # Control centralizado de canales
│   ├── device_registry.py           # Registro persistente de dispositivos
│   ├── latency_optimizer.py         # Optimización automática de latencia
│   ├── native_protocol.py           # Protocolo binario personalizado
│   ├── native_server.py             # Servidor TCP/UDP para Android
│   └── websocket_server.py          # Servidor WebSocket (Flask-SocketIO)
│
├── frontend/                        # 🌐 UI Web (PWA)
│   ├── index.html                   # Interfaz principal
│   ├── styles.css                   # Estilos y tema
│   ├── sw.js                        # Service Worker
│   ├── manifest.json                # Manifiesto PWA
│   ├── heartbeat-worker.js          # Worker para mantener conexión
│   └── assets/                      # Iconos y recursos
│
├── config/                          # 📋 Estado persistente
│   ├── devices.json                 # Registro de dispositivos
│   ├── channels_state.json          # Estado de canales
│   ├── client_states.json           # Estado de clientes
│   └── web_ui_state.json            # Orden de clientes en UI
│
├── assets/                          # 🎨 Generación de recursos
│   ├── convert_to_ico.py            # Convertir PNG a ICO
│   └── generate_pwa_icons.py        # Generar iconos PWA
│
├── logs/                            # 📜 Archivos de log
├── recordings/                      # 🎙️ Grabaciones de audio
├── requirements.txt                 # 📦 Dependencias Python
├── FichatechMonitor.spec            # Especificación PyInstaller (GUI)
└── main.spec                        # Especificación PyInstaller (Servidor)
```

---

## 🔑 Características Clave

### ⚡ Ultra-Baja Latencia
- **BlockSize**: 64 samples @ 48kHz = **10.67ms** de latencia de captura
- **Optimización automática**: Ajuste dinámico de parámetros según carga
- **Prioridad real-time**: En Linux/macOS se habilita prioridad RT
- **Measurement**: Sistema de monitoreo de latencia en tiempo real

### 🎚️ Control de Canales
- **Ganancia**: +/- 12 dB por canal y cliente
- **Panorama (Pan)**: -1.0 (izquierda) a +1.0 (derecha)
- **Mute**: Silencio de canal individual
- **Subscripciones selectivas**: Cada cliente recibe solo los canales que necesita

### 📊 Monitoreo en Tiempo Real
- **VU Meters**: Medición de nivel por canal (RMS + Picos)
- **Decaimiento de picos**: Factor 0.95 para visualización suave
- **Estadísticas de latencia**: Promedio de últimas 100 mediciones
- **Monitor de recursos**: CPU, memoria, temperatura (en GUI)

### 🔐 Persistencia
- **Device Registry**: ID único por dispositivo (no cambia entre sesiones)
- **Channel State**: Guarda estado de ganancia, pan, mute
- **Client State**: Historial de clientes conectados
- **UI State**: Orden de clientes en interfaz web

### 🌐 Multiplataforma
- **Linux**: ✅ Full support con prioridad RT
- **Windows**: ✅ Full support
- **macOS**: ✅ Full support
- **Android**: ✅ Clientes nativos vía protocolo TCP/UDP
- **Web**: ✅ PWA (iOS Safari, Chrome, Firefox)

---

## 🔄 Flujo de Datos (Ejemplo: Captura → Transmisión)

```
1. AudioCapture callback (48kHz, 64 samples)
   ↓
2. Copiar buffer a numpy array
   ↓
3. ChannelManager procesa suscripciones
   ↓
4. Para cada cliente:
   - Si es Android: comprimir + enviar vía TCP (NativeProtocol)
   - Si es Web: procesar eventos WebSocket
   - Si es Maestro: enviar mezcla personalizada + streaming
   ↓
5. Paralelizar envío con ThreadPoolExecutor (6 hilos por defecto)
   ↓
6. Actualizar VU meters si es necesario
   ↓
7. Registrar latencia medida
```

---

## 📡 Protocolos de Red

### WebSocket (Web UI + Master)
- **Framework**: Flask-SocketIO
- **Eventos principales**:
  - `subscribe_channel`: Cliente se suscribe a canales
  - `set_gain`, `set_pan`, `set_mute`: Control de parámetros
  - `channel_state`: Broadcast de estado actualizado
  - `vu_update`: Actualización de medidores
  - `audio_chunk`: Streaming para cliente maestro

### Native Protocol (Android)
- **Tipo**: TCP/UDP personalizado
- **Header**: 16 bytes (Magic, Version, MsgType, Flags, Payload Size)
- **Tipos de mensaje**:
  - `MSG_TYPE_AUDIO` (0x01): Datos de audio
  - `MSG_TYPE_CONTROL` (0x02): Control de parámetros
- **Formatos soportados**:
  - Float32 (FLAG_FLOAT32)
  - Int16 (FLAG_INT16)

---

## 🛠️ Tecnologías Utilizadas

| Componente | Tecnología | Versión |
|-----------|-----------|---------|
| Audio | sounddevice (PortAudio) | 0.4.6+ |
| Web Framework | Flask | 3.0.0+ |
| WebSockets | Flask-SocketIO | 5.3.5+ |
| GUI Desktop | customtkinter | 5.2.0+ |
| Análisis | numpy, scipy | 1.26.0+, 1.11.4+ |
| Compilación | PyInstaller | 6.3.0+ |
| Python | 3.9 - 3.13 | Multiplataforma |

---

## 🚀 Cómo Funciona el Sistema

### Inicio del Sistema
1. `main.py` inicia `AudioServerApp`
2. Se inicializa:
   - **Device Registry**: Carga dispositivos conocidos
   - **Audio Mixer**: Prepara mezcla para cliente maestro
   - **Audio Capture**: Abre stream de audio
   - **Native Server**: TCP/UDP escuchando en puerto 9999
   - **WebSocket Server**: Flask en puerto 5000
3. GUI Desktop muestra estado del servidor

### Conexión de Cliente Android
1. Cliente Android envía paquete "HELLO" con device_uuid
2. WebSocket Server registra cliente en Device Registry
3. Server envía configuración: num_channels, sample_rate
4. Comienza flujo de audio comprimido

### Conexión Web UI
1. Navegador se conecta a `http://localhost:5000`
2. Establece conexión WebSocket
3. Recibe lista de canales disponibles
4. Se suscribe a canales de interés
5. Recibe updates de VU meters en tiempo real

---

## ⚙️ Configuración Principal (config.py)

- **BLOCKSIZE**: 64 samples (10.67ms @ 48kHz)
- **SAMPLE_RATE**: 48000 Hz
- **DEFAULT_NUM_CHANNELS**: 2 (estéreo)
- **ENABLE_OPUS_COMPRESSION**: False (solo zlib)
- **WEBSOCKET_PARAM_DEBOUNCE_MS**: 50ms (agrupamiento de cambios)
- **AUDIO_SEND_POOL_SIZE**: 6 hilos para envío paralelo
- **MASTER_CLIENT_ENABLED**: True (cliente maestro disponible)

---

## 📊 Estado y Persistencia

### `devices.json`
```json
{
  "device_uuid_1": {
    "device_name": "Samsung Galaxy Tab",
    "device_id": "Android123",
    "last_seen": 1704547200,
    "client_type": "native"
  }
}
```

### `channels_state.json`
```json
{
  "channel_0": {
    "name": "Micrófono Principal",
    "gain": 0.8,
    "pan": 0.0,
    "mute": false
  }
}
```

---

## 🔍 Puntos Clave a Recordar

1. **Baja latencia es crítica**: Config de 64 samples permite ~10ms
2. **Múltiples clientes simultáneos**: Sistema diseñado para N clientes en paralelo
3. **Protocolo binario vs JSON**: Android usa protocolo comprimido, Web usa JSON
4. **Prioridad real-time**: En Linux, audio_capture intenta RT priority
5. **Streaming vs Control**: Distintos canales para audio (stream) y control (eventos)
6. **Mezcla personalizada**: Cada cliente puede tener mezcla diferente
7. **Persistencia inteligente**: Device UUID mantiene identidad entre sesiones

---

## 📞 Puntos de Entrada

- **main.py**: Servidor + CLI
- **gui_monitor.py**: GUI Desktop
- **frontend/index.html**: Web UI (acceder en http://localhost:5000)
