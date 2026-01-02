# 📻 ANÁLISIS EXHAUSTIVO - FICHATECH MONITOR

## 🎯 OBJETIVO DEL PROYECTO

**Fichatech Monitor** es un sistema de **monitoreo de audio multicanal en tiempo real** diseñado para:

1. **Capturar audio** desde interfaces de audio profesional (hasta 48 canales)
2. **Transmitir** con ultra-baja latencia a clientes Android (nativos) y Web
3. **Permitir mezclas personalizadas** para cada músico/técnico (In-Ear Monitoring)
4. **Usar como sistema RF (Radio Frecuencia)** para monitoreo inalámbrico en vivo

### Casos de Uso Principal:
- **Músicos en escenario**: Reciben mezcla personalizada en sus dispositivos Android
- **Técnicos de sonido**: Monitorean desde interfaz web con control de mezcla
- **Transmisiones en vivo**: Audio de baja latencia para broadcasting

---

## 🏗️ ARQUITECTURA DEL SISTEMA

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SERVIDOR (Python)                            │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐   │
│  │ AudioCapture │───▶│ ChannelManager  │───▶│ NativeServer TCP │   │
│  │  (sounddev)  │    │   (mezclas)     │    │   (Puerto 5101)  │   │
│  └──────────────┘    └────────┬────────┘    └────────┬─────────┘   │
│                               │                       │            │
│                               ▼                       │            │
│                      ┌─────────────────┐              │            │
│                      │ WebSocket Flask │              │            │
│                      │  (Puerto 5100)  │              │            │
│                      └────────┬────────┘              │            │
└───────────────────────────────┼───────────────────────┼────────────┘
                                │                       │
        ┌───────────────────────┼───────────────────────┤
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌────────────────────┐
│   Frontend    │     │ Android Client  │     │  UDP (No funcional)│
│   (Browser)   │     │  (TCP + Oboe)   │     │   UDPAudioClient   │
│   Control UI  │     │  Ultra-Low Lat  │     │                    │
└───────────────┘     └─────────────────┘     └────────────────────┘
```

---

## ⚙️ CONFIGURACIÓN Y PARÁMETROS CLAVE

### Audio Core ([config.py](config.py)):
| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `SAMPLE_RATE` | 48000 Hz | Estándar profesional |
| `BLOCKSIZE` | 128 samples | ~2.67ms latencia teórica |
| `USE_INT16_ENCODING` | True | -50% ancho de banda vs Float32 |

### Red:
| Puerto | Protocolo | Uso |
|--------|-----------|-----|
| 5100 | HTTP/WebSocket | Frontend web + control |
| 5101 | TCP | Clientes Android nativos |

### Socket Optimizations:
```python
SOCKET_SNDBUF = 65536      # Buffer de envío
SOCKET_RCVBUF = 32768      # Buffer de recepción
SOCKET_NODELAY = True      # Deshabilita Nagle (reduce latencia)
TCP_KEEPALIVE = True       # Detecta clientes muertos
```

---

## 📊 ANÁLISIS DE LATENCIA

### Cadena de Latencia Completa:

```
Micrófono → ADC (0.5-1ms) → Driver (1-2ms) → Captura Python (2.67ms)
    → Procesamiento (0.1ms) → TCP Send (variable) → Android Receive
    → Jitter Buffer (2-5ms) → Oboe Decode (1.33ms) → DAC (0.5-1ms)
```

### Desglose por Componente:

| Componente | Latencia | Notas |
|------------|----------|-------|
| **Servidor** |
| AudioCapture | ~2.67ms | `BLOCKSIZE=128 @ 48kHz` |
| Queue Web | ~0.1ms | `WEB_QUEUE_SIZE=2` |
| Queue RF | ~0ms | `NATIVE_QUEUE_SIZE=0` (directo) |
| **Red** |
| TCP/WiFi | 1-10ms | Variable según condiciones |
| **Android** |
| OboeAudioRenderer | ~1.33ms | `OPTIMAL_BUFFER_SIZE=64 frames` |
| Buffer Size | 2x burst | Típico: 128-256 frames |

### **Latencia Total Estimada: 8-20ms** (condiciones óptimas WiFi)

### Optimizaciones de Latencia Implementadas (Android):

1. **MMAP Mode**: Acceso directo a hardware (si soportado)
2. **Exclusive Sharing**: Sin mezcla con otras apps
3. **Thread Priority**: `THREAD_PRIORITY_URGENT_AUDIO`
4. **DirectByteBuffer**: Evita copias JVM→Nativo
5. **Buffer Pool**: Reduce pausas de GC
6. **LUT para soft clipping**: Evita condicionales en hot path

```kotlin
// native_audio_engine.cpp
builder.setPerformanceMode(oboe::PerformanceMode::LowLatency)
       .setSharingMode(oboe::SharingMode::Exclusive);  // Activa MMAP
```

---

## 📱 POLÍTICAS DE GOOGLE PLAY

El proyecto implementa correctamente las políticas para servicios de audio en segundo plano:

### 1. **Foreground Service** ([AudioStreamForegroundService.kt](kotlin android/AudioStreamForegroundService.kt)):

```kotlin
// ✅ CUMPLE: Tipo específico para Android 14+
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
    startForeground(
        NOTIFICATION_ID,
        notification,
        ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK  // ✅ Obligatorio
    )
}
```

### 2. **Notificación Persistente**:
- Canal: `audio_stream_channel`
- Acciones: Start, Stop, Disconnect
- ✅ Visible mientras el servicio corre

### 3. **WakeLock y WifiLock**:
```kotlin
// ✅ Timeout de 5 minutos (cumple políticas)
private const val LOCK_TIMEOUT_MS = 5 * 60 * 1000L
private const val RENEWAL_INTERVAL_MS = 4 * 60 * 1000L  // Renueva antes de expirar
```

### 4. **Permisos Requeridos** (AndroidManifest.xml):
```xml
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />  <!-- Android 13+ -->
<uses-permission android:name="android.permission.WAKE_LOCK" />
<uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />
```

---

## 🔌 PROTOCOLO NATIVO (TCP)

### Header (16 bytes):
```
┌────────────┬─────────────┬──────────────┬───────────────┬───────────────┐
│  Magic (4) │ Version (2) │ Type+Flags(2)│ Timestamp (4) │ PayloadLen (4)│
│ 0xA1D10A7C │     2       │  0x01/0x02   │    ms offset  │    bytes      │
└────────────┴─────────────┴──────────────┴───────────────┴───────────────┘
```

### Tipos de Mensaje:
- `0x01`: Audio Data
- `0x02`: Control (handshake, subscribe, gains, etc.)

### Flags:
- `0x01`: Float32 encoding
- `0x02`: Int16 encoding (50% menos datos)
- `0x80`: RF Mode (auto-reconexión)

### Payload de Audio:
```
┌─────────────────┬──────────────────┬──────────────────────────────────┐
│ Sample Pos (8B) │ Channel Mask (4B)│ Audio Data (interleaved samples) │
└─────────────────┴──────────────────┴──────────────────────────────────┘
```

---

## 🌐 INTERFAZ WEB (Control Center)

### Funcionalidades:
- **Lista de clientes**: Nativos (RF) y Web
- **Mixer por cliente**: Selección de canales, gains, pans
- **VU Meters**: Monitoreo visual de niveles
- **Auto-reconexión**: Estado persistente de sesiones

### Comunicación:
```javascript
// Socket.IO para tiempo real
const socket = io();
socket.on('connect', () => {...});
socket.emit('subscribe', {channels: [0, 1, 2]});
```

---

## 🚨 PROBLEMA: UDP NO IMPLEMENTADO EN SERVIDOR

### Estado Actual:

El cliente Android tiene `UDPAudioClient.kt` completo, pero el servidor **NO tiene soporte UDP**:

1. **`native_server.py`**: Solo TCP (`SOCK_STREAM`)
2. **No existe**: `udp_server.py` o handler UDP
3. **Protocolo diferente**: UDP usa `MAGIC_NUMBER = 0xA1D10A7D` vs TCP usa `0xA1D10A7C`

### Diferencias del Protocolo UDP (cliente):

| Característica | TCP | UDP |
|----------------|-----|-----|
| Magic Number | `0xA1D10A7C` | `0xA1D10A7D` |
| Header Size | 16 bytes | 32 bytes |
| Packet Types | Audio, Control | Audio, Control, Heartbeat, Sync |
| Max Packet | ~2MB | 1472 bytes (MTU) |
| Jitter Buffer | No | Sí (10 paquetes) |
| Ordering | Garantizado | Reordenamiento manual |

### Funcionalidades UDP en Cliente (sin servidor):

```kotlin
// UDPAudioClient.kt - línea 26
private const val PACKET_TYPE_AUDIO = 0x01
private const val PACKET_TYPE_CONTROL = 0x02
private const val PACKET_TYPE_HEARTBEAT = 0x03  // ✅ Extra
private const val PACKET_TYPE_SYNC = 0x04       // ✅ Extra
```

- **Jitter Buffer**: 10 paquetes para reordenamiento
- **Heartbeat**: Cada 10 segundos
- **Sync**: Cada 20 segundos para estadísticas
- **Estadísticas**: Paquetes perdidos, out-of-order, latencia, jitter

---

## 🔧 SOLUCIÓN PROPUESTA PARA UDP

Para hacer funcional UDP, se necesita crear un servidor UDP en Python. A continuación el diseño:

### Nuevo Archivo: `audio_server/udp_server.py`

**Componentes necesarios:**

1. **Socket UDP** (`SOCK_DGRAM`)
2. **Protocolo compatible con cliente**:
   - Magic: `0xA1D10A7D`
   - Header: 32 bytes
   - Tipos: Audio, Control, Heartbeat, Sync
3. **Thread de recepción de control**
4. **Broadcast de audio** (sin garantía de orden)
5. **Heartbeat handling**

### Flujo de Comunicación UDP:

```
Cliente                          Servidor
   │                                │
   │──── Handshake (UDP) ──────────▶│
   │                                │
   │◀─── ServerInfo (UDP) ──────────│
   │                                │
   │──── Subscribe (UDP) ──────────▶│
   │                                │
   │◀─── Audio Packets (UDP) ───────│ (continuo)
   │                                │
   │──── Heartbeat (cada 10s) ─────▶│
   │◀─── Heartbeat ACK ─────────────│
   │                                │
   │──── Sync Request (cada 20s) ──▶│
   │◀─── Sync Response ─────────────│
```

---

## 📈 COMPARATIVA TCP vs UDP

| Aspecto | TCP (Actual) | UDP (Propuesto) |
|---------|--------------|-----------------|
| **Latencia** | ~5-15ms | ~2-8ms |
| **Confiabilidad** | Garantizada | Puede perder paquetes |
| **Overhead** | Alto (ACKs, retransmisiones) | Bajo |
| **Orden** | Garantizado | Manual (seq numbers) |
| **Caso de uso** | WiFi estable | Baja latencia crítica |
| **Complejidad servidor** | Media | Alta (jitter buffer, sync) |

---

## ✅ RESUMEN DE FUNCIONALIDADES

| Componente | Estado | Notas |
|------------|--------|-------|
| Servidor Python | ✅ Funcional | TCP + WebSocket |
| GUI Monitor | ✅ Funcional | CustomTkinter |
| Frontend Web | ✅ Funcional | Control de mezclas |
| Android TCP | ✅ Funcional | NativeAudioClient + Oboe |
| Android UDP | ⚠️ Cliente listo | Servidor no implementado |
| Auto-reconexión RF | ✅ Funcional | Estado persistente |
| Int16 Encoding | ✅ Funcional | -50% bandwidth |
| Foreground Service | ✅ Cumple políticas | Media Playback type |
| MMAP/Low Latency | ✅ Automático | Oboe detecta soporte |

---

## 🎯 PRÓXIMOS PASOS RECOMENDADOS

1. **Implementar UDP Server** en Python para activar `UDPAudioClient.kt`
2. **Agregar Jitter Buffer** en servidor para compensar variabilidad
3. **Implementar FEC** (Forward Error Correction) para recuperar paquetes perdidos
4. **Considerar hybrid mode**: TCP para control, UDP para audio

---

¿Deseas que proceda con la implementación del servidor UDP para completar la funcionalidad?
