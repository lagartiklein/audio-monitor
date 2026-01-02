# 📻 Fichatech Monitor

## 🎯 Descripción del Proyecto

**Fichatech Monitor** es un sistema profesional de **monitoreo de audio multicanal en tiempo real** diseñado para aplicaciones de audio en vivo, permitiendo transmisión de audio con ultra-baja latencia a múltiples dispositivos simultáneamente.

### Casos de Uso
- 🎸 **Músicos en escenario**: Mezclas personalizadas en dispositivos Android (In-Ear Monitoring)
- 🎚️ **Técnicos de sonido**: Control y monitoreo desde interfaz web
- 📡 **Transmisiones en vivo**: Sistema RF (Radio Frecuencia) para monitoreo inalámbrico
- 🎙️ **Broadcasting**: Audio de baja latencia para streaming

---

## ✨ Características Principales

### 🎵 Audio
- ✅ Captura de hasta **48 canales** simultáneos desde interfaces profesionales
- ✅ **Ultra-baja latencia**: 8-20ms end-to-end en condiciones óptimas
- ✅ Sample Rate: **48000 Hz** (estándar profesional)
- ✅ Blocksize: **128 samples** (~2.67ms de latencia teórica)
- ✅ Encoding eficiente: **Int16** (-50% ancho de banda vs Float32)

### 🌐 Conectividad
- ✅ **Servidor WebSocket** (Puerto 5100): Interfaz web y control
- ✅ **Servidor TCP Nativo** (Puerto 5101): Clientes Android con protocolo optimizado
- ✅ **Auto-reconexión RF**: Reconexión automática con persistencia de estado
- ✅ Soporte simultáneo para múltiples clientes

### 🎚️ Control y Mezclas
- ✅ **Mezclas personalizadas** por cliente
- ✅ Control individual de **ganancia** y **pan** por canal
- ✅ **VU Meters** en tiempo real
- ✅ Interfaz web moderna con controles intuitivos
- ✅ GUI de escritorio con **CustomTkinter** (tema oscuro)

### 📱 Cliente Android
- ✅ Implementación con **Oboe** (Audio de baja latencia de Google)
- ✅ **Foreground Service** compatible con políticas de Google Play
- ✅ **MMAP Mode** y **Exclusive Sharing** cuando están disponibles
- ✅ Optimizaciones de latencia: Thread Priority, Buffer Pool, DirectByteBuffer
- ✅ Cliente UDP implementado (servidor UDP pendiente)

---

## 🏗️ Arquitectura del Sistema

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
        ┌───────────────────────┼───────────────────────┘
        ▼                       ▼
┌───────────────┐     ┌─────────────────┐
│   Frontend    │     │ Android Client  │
│   (Browser)   │     │  (TCP + Oboe)   │
│   Control UI  │     │  Ultra-Low Lat  │
└───────────────┘     └─────────────────┘
```

---

## 📦 Instalación

### Requisitos Previos
- Python 3.8 o superior
- Interfaz de audio compatible (ASIO, WASAPI, CoreAudio, etc.)
- Para Android: Android Studio con NDK

### Instalación del Servidor

```bash
# Clonar el repositorio
git clone https://github.com/lagartiklein/audio-monitor.git
cd audio-monitor

# Crear entorno virtual (recomendado)
python -m venv .venv

# Activar entorno virtual
# En Windows:
.venv\Scripts\activate
# En Linux/Mac:
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Dependencias Principales
```
numpy>=1.24.0           # Procesamiento de audio
sounddevice>=0.4.6      # Captura de audio
flask>=3.0.0            # Servidor web
flask-socketio>=5.3.0   # WebSocket
customtkinter>=5.2.0    # GUI moderna
pyaudio>=0.2.13         # Backend de audio
```

---

## 🚀 Uso

### Iniciar el Servidor

#### Modo GUI (Recomendado)
```bash
python main.py
```

La interfaz gráfica permite:
1. **Seleccionar dispositivo de audio** de la lista
2. **Iniciar/Detener** el servidor con un clic
3. **Monitorear logs** en tiempo real con colores
4. **Ver estado** de clientes conectados

#### Modo Consola
```bash
python main.py --no-gui
```

### Acceder a la Interfaz Web

Una vez iniciado el servidor:

1. **Abrir navegador** en: `http://localhost:5100`
2. **Conectar** cliente Android a la IP del servidor (puerto 5101)
3. **Configurar mezclas** desde la interfaz web

---

## ⚙️ Configuración

El archivo `config.py` contiene todos los parámetros configurables:

### Audio
```python
SAMPLE_RATE = 48000              # Hz
BLOCKSIZE = 128                  # samples (~2.67ms)
USE_INT16_ENCODING = True        # True = -50% datos
```

### Red
```python
WEB_PORT = 5100                  # Puerto WebSocket
NATIVE_PORT = 5101               # Puerto TCP nativo
NATIVE_MAX_CLIENTS = 5           # Clientes simultáneos
```

### Optimizaciones
```python
SOCKET_NODELAY = True            # Deshabilita Nagle
TCP_KEEPALIVE = True             # Detecta clientes muertos
RF_AUTO_RECONNECT = True         # Auto-reconexión RF
```

---

## 📱 Cliente Android

### Compilar la App

1. **Copiar archivos Kotlin** de `kotlin android/` a tu proyecto Android
2. **Agregar dependencias** en `build.gradle`:

```gradle
dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation "com.google.oboe:oboe:1.7.0"
}
```

3. **Configurar permisos** en `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.WAKE_LOCK" />
```

4. **Compilar** con NDK habilitado

### Conectar desde Android

1. Asegurarse de estar en la **misma red WiFi** que el servidor
2. Ingresar la **IP del servidor** y puerto **5101**
3. Seleccionar **canales** a monitorear
4. Ajustar **ganancias** individuales

---

## 🎚️ Protocolo Nativo (TCP)

### Header (16 bytes)
```
┌────────────┬─────────────┬──────────────┬───────────────┬───────────────┐
│  Magic (4) │ Version (2) │ Type+Flags(2)│ Timestamp (4) │ PayloadLen (4)│
│ 0xA1D10A7C │     2       │  0x01/0x02   │    ms offset  │    bytes      │
└────────────┴─────────────┴──────────────┴───────────────┴───────────────┘
```

### Tipos de Mensaje
- `0x01`: Audio Data (samples interleaved)
- `0x02`: Control (handshake, subscribe, gains)

### Flags
- `0x01`: Float32 encoding
- `0x02`: Int16 encoding (recomendado)
- `0x80`: RF Mode (auto-reconexión)

---

## 📊 Análisis de Latencia

### Desglose de Latencia

| Componente | Latencia | Descripción |
|------------|----------|-------------|
| ADC Hardware | 0.5-1ms | Conversión analógico-digital |
| Driver de Audio | 1-2ms | Buffer del sistema operativo |
| Captura Python | ~2.67ms | BLOCKSIZE=128 @ 48kHz |
| Procesamiento | ~0.1ms | Mezcla y encoding |
| Red TCP/WiFi | 1-10ms | Variable según condiciones |
| Oboe Renderer | ~1.33ms | Buffer de 64 frames |
| DAC Hardware | 0.5-1ms | Conversión digital-analógico |

**Latencia Total: 8-20ms** (en condiciones óptimas de WiFi)

---

## 🔧 Optimizaciones Implementadas

### Servidor
- ✅ **Colas de tamaño cero** para RF (envío directo)
- ✅ **TCP_NODELAY** (deshabilita algoritmo de Nagle)
- ✅ **Buffer pools** para reducir allocations
- ✅ **Int16 encoding** (-50% ancho de banda)
- ✅ **Thread priority** para captura de audio

### Android
- ✅ **MMAP Mode** (acceso directo a hardware)
- ✅ **Exclusive Sharing** (sin mezcla con otras apps)
- ✅ **Thread Priority URGENT_AUDIO**
- ✅ **DirectByteBuffer** (evita copias JVM↔Nativo)
- ✅ **Buffer Pool** (reduce pausas de GC)
- ✅ **LUT para soft clipping** (evita condicionales)

---

## 📁 Estructura del Proyecto

```
audio-monitor/
│
├── main.py                      # Punto de entrada principal
├── gui_monitor.py               # Interfaz gráfica (CustomTkinter)
├── config.py                    # Configuración global
├── requirements.txt             # Dependencias Python
│
├── audio_server/                # Módulos del servidor
│   ├── audio_capture.py         # Captura de audio (sounddevice)
│   ├── channel_manager.py       # Gestión de canales y mezclas
│   ├── native_server.py         # Servidor TCP para Android
│   ├── native_protocol.py       # Protocolo binario
│   └── websocket_server.py      # Servidor WebSocket/Flask
│
├── frontend/                    # Interfaz web
│   ├── index.html              # UI de control
│   └── styles.css              # Estilos
│
├── kotlin android/              # Cliente Android
│   ├── NativeAudioClient.kt    # Cliente TCP
│   ├── OboeAudioRenderer.kt    # Renderer de audio (Oboe)
│   ├── AudioStreamForegroundService.kt  # Servicio en segundo plano
│   ├── UDPAudioClient.kt       # Cliente UDP (servidor pendiente)
│   └── native_audio_engine.cpp # Motor de audio nativo (C++)
│
├── assets/                      # Recursos
│   └── icono.ico               # Icono de la aplicación
│
└── docs/                        # Documentación técnica
    ├── ANALISIS_FICHATECH_MONITOR.md    # Análisis exhaustivo
    └── GUI_MODERNIZATION.md             # Cambios de GUI
```

---

## 🚨 Estado de Funcionalidades

| Componente | Estado | Notas |
|------------|--------|-------|
| Servidor Python | ✅ Funcional | TCP + WebSocket |
| GUI Monitor | ✅ Funcional | CustomTkinter moderna |
| Frontend Web | ✅ Funcional | Control de mezclas |
| Android TCP | ✅ Funcional | NativeAudioClient + Oboe |
| Android UDP | ⚠️ Cliente listo | **Servidor no implementado** |
| Auto-reconexión RF | ✅ Funcional | Estado persistente |
| Int16 Encoding | ✅ Funcional | -50% bandwidth |
| Foreground Service | ✅ Cumple políticas | Media Playback type |
| MMAP/Low Latency | ✅ Automático | Oboe detecta soporte |

---

## 🐛 Problemas Conocidos

1. **UDP Server no implementado**: El cliente Android tiene soporte UDP completo, pero el servidor Python solo implementa TCP. UDP podría ofrecer latencia aún menor (2-8ms vs 5-15ms).

2. **Limitación WiFi**: La latencia de red puede variar significativamente según la calidad de la conexión WiFi.

3. **Compatibilidad de dispositivos**: Algunos dispositivos Android no soportan MMAP mode o exclusive sharing.

---

## 🎯 Roadmap

### Corto Plazo
- [ ] Implementar servidor UDP en Python
- [ ] Agregar Jitter Buffer en servidor
- [ ] Mejorar manejo de errores de red

### Medio Plazo
- [ ] Forward Error Correction (FEC)
- [ ] Modo híbrido (TCP para control, UDP para audio)
- [ ] Compresión de audio opcional (Opus)
- [ ] Soporte para iOS

### Largo Plazo
- [ ] Sincronización de múltiples servidores
- [ ] Recording y playback de sesiones
- [ ] Plugin VST/AU para DAWs

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. **Fork** el repositorio
2. Crear una **rama** para tu feature (`git checkout -b feature/AmazingFeature`)
3. **Commit** tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. **Push** a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un **Pull Request**

---

## 📄 Licencia

Este proyecto está desarrollado para uso profesional en producción de audio en vivo.

---

## 📞 Soporte

Para reportar bugs o solicitar features, por favor abre un **issue** en GitHub.

---

## 🙏 Agradecimientos

- **sounddevice**: Captura de audio de alta calidad
- **Flask-SocketIO**: WebSocket confiable
- **CustomTkinter**: GUI moderna
- **Google Oboe**: Audio de baja latencia en Android

---

**Fichatech Monitor** - Sistema Profesional de Monitoreo de Audio en Tiempo Real 🎵
