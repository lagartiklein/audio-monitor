# 🚀 GUÍA DE USO Y FLUJOS DE TRABAJO

## 📋 Tabla de Contenidos
1. [Inicio Rápido](#inicio-rápido)
2. [Inicio del Servidor](#inicio-del-servidor)
3. [Conexión de Clientes](#conexión-de-clientes)
4. [Flujos de Trabajo Comunes](#flujos-de-trabajo-comunes)
5. [Troubleshooting](#troubleshooting)
6. [Configuración Avanzada](#configuración-avanzada)

---

## 🟢 Inicio Rápido

### Requisitos
- Python 3.9 - 3.13
- Interfaz de audio (micrófono/línea de entrada)
- Red TCP/IP (para conectar dispositivos)

### 1. Instalación

```bash
# Clonar o descargar proyecto
cd c:\audio-monitor

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Iniciar Servidor

```bash
# Opción A: Con GUI Desktop
python main.py

# Opción B: Sin GUI (servidor puro, en producción)
python main.py --no-gui
```

### 3. Acceder a Web UI

Abrir navegador en: **http://localhost:5000**

### 4. Conectar Cliente Android

1. Abrir app Android Fichatech
2. Ingresar dirección IP de servidor (ej: 192.168.1.100)
3. Puerto: 9999
4. Conectar

---

## 🖥️ Inicio del Servidor

### Opción 1: Línea de Comandos

```bash
# Inicio normal
python main.py

# Con parámetros específicos
python main.py --port 5000 --native-port 9999 --no-gui

# Modo verbose (más logs)
python main.py --verbose

# Usar dispositivo de audio específico
python main.py --device "Interfaz MOTU"
```

### Opción 2: GUI Desktop

```bash
# Ejecutar GUI
python gui_monitor.py
```

**Interfaz GUI muestra**:
- 🟢 Estado del servidor (Iniciado/Detenido)
- 📊 Monitoreo en tiempo real
  - CPU usage
  - Memoria
  - Latencia
  - Clientes conectados
- 🎙️ Dispositivo de audio seleccionado
- 📱 Lista de clientes conectados
- 🌐 Botón para abrir Web UI

### Opción 3: Como Servicio (Windows)

```bash
# Compilar a exe
pyinstaller main.spec

# Ejecutar exe
dist\main.exe

# Instalar como servicio Windows (requiere admin)
sc create FichatechMonitor binPath="C:\ruta\a\main.exe"
```

---

## 📱 Conexión de Clientes

### Cliente Web (Navegador)

#### Conexión Local
1. Abrir: `http://localhost:5000`
2. Ver lista de canales inmediatamente
3. Ajustar sliders de ganancia/pan
4. Ver VU meters en tiempo real

#### Conexión Remota
1. Descubrir IP del servidor:
   ```bash
   # En terminal del servidor
   ipconfig  # Windows
   ifconfig  # Linux/Mac
   # Notar: 192.168.1.100 (ejemplo)
   ```

2. En cliente remoto:
   - Abrir: `http://192.168.1.100:5000`
   - Permite control desde cualquier dispositivo en la red

#### PWA (Instalar como App)

**En Chrome/Edge**:
1. Abrir: `http://localhost:5000`
2. Menú ⋮ → "Instalar aplicación"
3. Ejecutar offline

**En Safari (iPhone/iPad)**:
1. Abrir: `http://servidor:5000`
2. Botón Compartir → "Añadir a pantalla de inicio"

### Cliente Android Nativo

#### Primer Arranque

```
App Android Fichatech
    ↓
Pantalla de conexión
    ↓
Ingresar: 192.168.1.100:9999
    ↓
Tocar "Conectar"
    ↓
    ├─ Si OK: Pantalla de audio
    │  ├─ VU meters
    │  ├─ Control de canales
    │  └─ Comienza streaming
    │
    └─ Si error: Mostrar mensaje
       ├─ Red no disponible
       ├─ Servidor no responde
       └─ Puerto incorrecto
```

#### Configuración del Dispositivo

En app Android:

1. **Dirección servidor**: 192.168.1.100 (IP actual del servidor)
2. **Puerto**: 9999 (por defecto, configurable)
3. **Seleccionar canales**: Qué canales recibir
   - [ ] Canal 0 (Micrófono principal)
   - [ ] Canal 1 (Micrófono secundario)
4. **Opciones de audio**:
   - Formato: Int16 (eficiencia RF) / Float32 (calidad)
   - Sample rate: 48000 Hz (recomendado)
5. **Modo RF**: Activar si conexión débil

#### Control Remoto desde Web

Una vez conectado el dispositivo Android:

1. En Web UI (`http://localhost:5000`):
   - Aparece card con nombre del dispositivo
   - Sliders para ganancia/pan/mute
   - VU meter en tiempo real

2. Ajustar parámetros:
   - **Ganancia**: 0.0 (silencio) a 2.0 (+6dB)
   - **Panorama**: -1.0 (izq) a +1.0 (der)
   - **Mute**: On/Off

3. Los cambios se envían automáticamente al dispositivo

---

## 🎯 Flujos de Trabajo Comunes

### Workflow 1: Monitoreo Remoto en Vivo

**Escenario**: Sonidista remoto necesita monitorear en tiempo real

```
Paso 1: Iniciar servidor (GUI Desktop)
        ├─ Seleccionar micrófono
        ├─ Verificar status: 🟢 Iniciado
        └─ Anotar IP del servidor

Paso 2: Abrir Web UI en navegador
        ├─ http://192.168.1.100:5000 (desde otra máquina)
        ├─ Ver lista de canales
        └─ Habilitar cliente maestro (sonidista)

Paso 3: Activar streaming de mezcla
        ├─ En Web: Seleccionar "Modo Maestro"
        ├─ Escuchar mezcla personalizada
        └─ Ajustar ganancias según necesidad

Paso 4: Monitoreo en vivo
        ├─ VU meters actualizados cada ~50ms
        ├─ Latencia < 100ms (visible en UI)
        └─ Control centralizado de parámetros
```

### Workflow 2: Distribución a Múltiples Dispositivos Android

**Escenario**: 5 transmisores RF remotos recibiendo audio

```
Paso 1: Configurar servidor
        ├─ Audio source: Consola Behringer
        ├─ Canales: 16 (estéreo × 8)
        └─ Sample rate: 48kHz

Paso 2: Conectar dispositivos Android
        Device 1: Transmisor RF #1 (canal 0-1)
        Device 2: Transmisor RF #2 (canal 2-3)
        Device 3: Transmisor RF #3 (canal 4-5)
        Device 4: Transmisor RF #4 (canal 6-7)
        Device 5: Transmisor RF #5 (canal 8-9)

Paso 3: Configurar suscripciones
        ├─ Device 1: recibe solo canales 0-1
        ├─ Device 2: recibe solo canales 2-3
        ├─ (etc.)
        └─ Ahorro: 75% ancho de banda vs todas

Paso 4: Controlar desde Web UI
        ├─ Card por dispositivo
        ├─ Ajustar ganancia/pan de cada uno
        └─ Monitor en tiempo real

Paso 5: Monitor de latencia
        ├─ Ver latencia por dispositivo
        ├─ Detectar problemas RF
        └─ Optimizar automáticamente si es necesario
```

### Workflow 3: Grabación Local + Streaming

**Escenario**: Grabar audio localmente y transmitir simultáneamente

```
Paso 1: Iniciar servidor
        └─ Grabación automática en: recordings/

Paso 2: Conectar clientes
        ├─ Android devices (transmisión)
        └─ Web UI (monitoreo)

Paso 3: Grabar en background
        ├─ Audio local: recordings/TIMESTAMP.wav
        ├─ Streaming: simultáneamente a clientes
        └─ Sin afectar latencia

Paso 4: Acceder a grabación después
        ├─ Archivo: recordings/2024-01-06_14-32-15.wav
        ├─ Formato: WAV 48kHz estéreo
        └─ Editable en DAW (Reaper, Ableton, etc.)
```

---

## 🔧 Troubleshooting

### Problema: "No se conecta a dispositivo de audio"

**Síntoma**: Al iniciar, muestra error en logs

```
[ERROR] audio_capture: No default audio device found
```

**Solución**:

```bash
# 1. Ver dispositivos disponibles
python -c "import sounddevice; print(sounddevice.query_devices())"

# 2. Especificar dispositivo al iniciar
python main.py --device "Nombre Interfaz"

# 3. En config.py, si es persistente:
AUDIO_DEVICE_INDEX = 2  # Número de dispositivo
```

### Problema: Cliente Android no se conecta

**Síntoma**: 
- "Conexión rechazada" en app Android
- Timeout al conectar

**Soluciones**:

```bash
# 1. Verificar que el servidor está corriendo
# En terminal del servidor: debe aparecer "[NativeServer] Escuchando en 0.0.0.0:9999"

# 2. Verificar firewall Windows
# PowerShell (admin):
netsh advfirewall firewall add rule name="Fichatech" dir=in action=allow protocol=tcp localport=9999

# 3. Verificar IP correcta
ipconfig

# 4. Probar conectividad desde otro dispositivo
# PowerShell:
Test-NetConnection 192.168.1.100 -Port 9999

# 5. Si aún no funciona, revisar logs
# En GUI Desktop: Ver "Logs" para más detalles
```

### Problema: Latencia muy alta (> 50ms)

**Síntomas**:
- VU meters lentos
- Retraso al ajustar controles

**Causas y soluciones**:

```python
# 1. CPU sobrecargada
# Solución: Reducir número de clientes o calidad de audio

# 2. Red congestionada (WiFi débil)
# Solución: Activar modo RF (compresión máxima)
# En config.py:
ENABLE_RF_MODE = True

# 3. Blocksize muy pequeño (ya optimizado en 64)
# No cambiar a menos que sea necesario

# 4. Socket buffers insuficientes
# Aumentar en config.py:
SOCKET_SEND_BUFFER = 65536  # 64KB
```

### Problema: Conexión inestable (clientes se desconectan)

**Síntomas**:
- Android dice "Desconectado" aleatoriamente
- WebSocket desconecta ocasionalmente

**Soluciones**:

```python
# En config.py, ajustar timeouts:

# Para clientes nativos:
NATIVE_HEARTBEAT_INTERVAL = 5      # segundos
NATIVE_HEARTBEAT_TIMEOUT = 15      # segundos (aumentar si red débil)
NATIVE_ZOMBIE_TIMEOUT = 30         # segundos

# Para WebSocket:
SOCKETIO_PING_INTERVAL = 60        # segundos
SOCKETIO_PING_TIMEOUT = 120        # segundos
```

---

## ⚙️ Configuración Avanzada

### Configuración de Audio (config.py)

```python
# ═══════════════════════════════════════════════════════
# AUDIO CORE
# ═══════════════════════════════════════════════════════

SAMPLE_RATE = 48000        # Hz (44100, 48000, 96000)
BLOCKSIZE = 64             # muestras (10.67ms @ 48kHz)
DEFAULT_NUM_CHANNELS = 2   # Estéreo (cambiar automáticamente)

# ═══════════════════════════════════════════════════════
# COMPRESIÓN
# ═══════════════════════════════════════════════════════

ENABLE_OPUS_COMPRESSION = False    # Usar zlib (mejor para RF)
COMPRESSION_LEVEL = 6              # zlib 1-9 (6 = balance)

# ═══════════════════════════════════════════════════════
# CLIENTES
# ═══════════════════════════════════════════════════════

NATIVE_SERVER_PORT = 9999          # Android/RF
WEBSOCKET_PORT = 5000              # Web UI
WEBSOCKET_PARAM_DEBOUNCE_MS = 50   # Agrupar cambios

# ═══════════════════════════════════════════════════════
# PERFORMANCE
# ═══════════════════════════════════════════════════════

AUDIO_SEND_POOL_SIZE = 6           # Hilos de envío paralelo
SEND_QUEUE_SIZE = 8                # Máximo paquetes en cola
WEB_QUEUE_SIZE = 2                 # Máximo WebSocket queue

# ═══════════════════════════════════════════════════════
# MASTER CLIENT (Sonidista)
# ═══════════════════════════════════════════════════════

MASTER_CLIENT_ENABLED = True       # Habilitar streaming para sonidista
MASTER_AUDIO_SEND_INTERVAL = 100   # ms entre updates
```

### Rutas de Configuración

```
config/
├── devices.json          # Registro de dispositivos
├── channels_state.json   # Estado de canales (ganancia, pan, mute)
├── client_states.json    # Historial de clientes
└── web_ui_state.json     # Orden de clientes en UI
```

**Ejemplo devices.json**:
```json
{
  "abc-123-xyz": {
    "device_name": "Samsung Galaxy Tab S7",
    "device_id": "Android123",
    "last_seen": 1704547200,
    "first_seen": 1704460800,
    "connection_count": 15
  }
}
```

### Logging

**Niveles de Log**:
```python
import logging

# En cualquier módulo:
logger = logging.getLogger(__name__)

logger.info("Mensaje informativo")        # Azul
logger.warning("Advertencia")              # Amarillo
logger.error("Error")                      # Rojo
logger.debug("Debug (verbose)")            # Gris
```

**Ver logs en tiempo real**:
```bash
# En terminal mientras corre servidor
# Los logs aparecen con timestamps y colores

# O guardar en archivo:
python main.py > logs/server.log 2>&1
```

---

## 📊 Monitoreo del Sistema

### Metrics Disponibles

**Via Web UI** (`http://localhost:5000/api/metrics`):
```json
{
  "server": {
    "uptime_seconds": 3600,
    "cpu_percent": 5.2,
    "memory_mb": 150.5
  },
  "audio": {
    "sample_rate": 48000,
    "blocksize": 64,
    "latency_ms": 18.5
  },
  "clients": {
    "native": 3,
    "web": 2,
    "master": 1
  },
  "network": {
    "bytes_sent_per_sec": 25000,
    "compression_ratio": 0.1
  }
}
```

### Gráficos en Tiempo Real

En Web UI:
- **Latencia**: Gráfico de línea (últimas 60s)
- **CPU/Memoria**: Barras actualizadas cada segundo
- **VU Meters**: Medidores por canal (RMS + picos)

---

## 🔐 Seguridad

### Configuración Recomendada

```python
# En config.py

# 1. Firewall: Solo permitir puertos específicos
NATIVE_SERVER_PORT = 9999
WEBSOCKET_PORT = 5000

# 2. Autenticación (opcional)
# REQUIRE_API_KEY = True
# API_KEY = "tu-clave-secreta-aqui"

# 3. CORS (Control de origen)
ALLOWED_ORIGINS = [
    "http://localhost:5000",
    "http://192.168.1.*"  # Red local
]
```

### Desplegar en Producción

```bash
# 1. Usar HTTPS (certificado SSL)
# Recomendado: Let's Encrypt

# 2. Ejecutar como servicio no-root
# No ejecutar como admin/root

# 3. Configurar reverse proxy (nginx)
# Para enrutamiento y seguridad

# 4. Monitoreo
# Usar systemd/supervisord para auto-restart
```

