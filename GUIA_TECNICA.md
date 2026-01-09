# 🔧 Guía Técnica - Motor de Audio y Servidor

Documentación técnica profunda sobre el motor de audio, servidor, optimizaciones y gestión de latencia en Fichatech Audio Monitor.

---

## 📋 Tabla de Contenidos

- [Motor de Audio](#motor-de-audio)
- [Captura de Audio](#captura-de-audio)
- [Procesamiento de Canales](#procesamiento-de-canales)
- [Mezcla de Audio](#mezcla-de-audio)
- [Compresión y Streaming](#compresión-y-streaming)
- [Servidor WebSocket](#servidor-websocket)
- [Servidor Nativo](#servidor-nativo)
- [Optimizaciones de Latencia](#optimizaciones-de-latencia)
- [Gestión de Recursos](#gestión-de-recursos)
- [Troubleshooting Avanzado](#troubleshooting-avanzado)

---

## 🔊 Motor de Audio

### Especificaciones de Audio

```
Parámetro               Valor       Notas
─────────────────────────────────────────────────
Frecuencia de muestreo  48 kHz      Estándar profesional
Formato de bits         32-bit float IEEE 754
Canales máximos         32           (según dispositivo)
Blocksize (latencia)    32 muestras  ≈ 0.67ms
Buffer total            ~10ms        3-4 bloques
Compresión             zlib Level 1  ~50-70% reducción
```

### Arquitectura del Motor

```
Sounddevice (WASAPI en Windows)
        ↓
    Callback Handler
        ↓
    Channel Manager
        ↓
    Audio Mixer
        ↓
    Compression
        ↓
    Streaming Distribution
```

### Inicialización del Motor

```python
# En audio_capture.py
class AudioCapture:
    def __init__(self):
        # Detectar dispositivo de audio predeterminado
        default_device = sd.default.device
        
        # Obtener información del dispositivo
        device_info = sd.query_devices(default_device)
        channels = device_info['max_input_channels']
        sample_rate = device_info['default_samplerate']
        
    def start(self):
        # Crear stream WASAPI con blocksize pequeño
        self.stream = sd.RawInputStream(
            device=device_id,
            samplerate=48000,
            channels=channels,
            blocksize=32,  # ← Latencia ultra-baja
            dtype=np.float32,
            callback=self.audio_callback,
            latency='low'  # ← Prioridad WASAPI
        )
        
        # Configurar prioridad real-time
        self.set_rt_priority()
```

---

## 🎤 Captura de Audio

### Flujo de Captura

```
Hardware Device
      ↓
WASAPI Driver
      ↓
Sounddevice RawInputStream
      ↓
Callback Thread (RT Priority)
      ↓
AudioCapture.audio_callback()
      ↓
np.float32 array [blocksize, channels]
      ↓
Distribuir a callbacks registrados
```

### Callback de Captura

```python
def audio_callback(indata, frames, time, status):
    """
    Callback del stream de Sounddevice.
    
    Args:
        indata: np.ndarray [32, channels] de float32
        frames: int (32)
        time: objeto de timing
        status: error status
    
    Returns:
        None (actualiza en-place)
    """
    if status:
        logger.warning(f"Audio callback status: {status}")
    
    # Copiar datos para evitar race conditions
    audio_data = indata.copy()
    
    # Llamar todos los callbacks registrados
    for callback in self.callbacks:
        try:
            callback(audio_data)
        except Exception as e:
            logger.error(f"Callback failed: {e}")
```

### Prioridad Real-Time

```python
def set_rt_priority(self):
    """
    Elevar prioridad del thread de captura a THREAD_PRIORITY_TIME_CRITICAL.
    Solo funciona si el proceso tiene privilegios suficientes.
    """
    import ctypes
    import threading
    
    # Constantes Windows
    THREAD_PRIORITY_TIME_CRITICAL = 15
    
    # Obtener handle del thread actual
    thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
    thread_handle = ctypes.windll.kernel32.OpenThread(
        0x0020,  # THREAD_SET_INFORMATION
        False,
        thread_id
    )
    
    # Intentar elevar prioridad
    try:
        ctypes.windll.kernel32.SetThreadPriority(
            thread_handle,
            THREAD_PRIORITY_TIME_CRITICAL
        )
        self.rt_priority_set = True
        logger.info("RT priority set successfully")
    except Exception as e:
        logger.warning(f"Could not set RT priority: {e}")
```

### Validación de Audio

```python
# En AudioCapture
def validate_audio_data(self, data):
    """Validar que los datos de audio sean válidos"""
    
    # Verificar NaN
    if np.isnan(data).any():
        logger.error("NaN detected in audio data")
        return False
    
    # Verificar clipping (valores > 1.0 o < -1.0)
    if np.abs(data).max() > 1.1:
        logger.warning(f"Clipping detected: {np.abs(data).max()}")
    
    # Verificar silencio completo (posible problema de hardware)
    if np.abs(data).max() < 0.0001:
        self.silence_counter += 1
        if self.silence_counter > 100:  # ~1 segundo
            logger.warning("Audio input appears to be silent")
    else:
        self.silence_counter = 0
    
    return True
```

---

## 🎚️ Procesamiento de Canales

### ChannelManager

El `ChannelManager` es responsable de mantener el estado y parámetros de cada canal.

```python
class ChannelManager:
    def __init__(self):
        self.channels: Dict[int, Channel] = {}
        self.lock = threading.RLock()
    
    class Channel:
        def __init__(self, channel_id: int):
            self.id = channel_id
            self.volume = 1.0        # 0-1
            self.pan = 0.0           # -1 (L) a +1 (R)
            self.mute = False
            self.selected = False
            self.monitor = False
            self.fx_chain = []       # Efectos aplicados
```

### Procesamiento Por Canal

```python
def process_channel_audio(self, channel_id: int, 
                         audio_data: np.ndarray) -> np.ndarray:
    """
    Procesa audio de un canal individual.
    
    Flujo:
    1. Aplicar volumen
    2. Aplicar pan (stereo)
    3. Aplicar mute
    4. Aplicar cadena de FX
    5. Retornar datos procesados
    """
    with self.lock:
        channel = self.channels.get(channel_id)
        if not channel:
            return audio_data
    
    # 1. Volumen
    audio_data = audio_data * channel.volume
    
    # 2. Pan (si es necesario estéreo)
    if audio_data.shape[1] == 2:  # Stereo output
        pan = channel.pan
        left_gain = np.sqrt(max(0, 1 - pan)) if pan > 0 else 1.0
        right_gain = np.sqrt(max(0, 1 + pan)) if pan < 0 else 1.0
        audio_data[:, 0] *= left_gain
        audio_data[:, 1] *= right_gain
    
    # 3. Mute
    if channel.mute:
        audio_data *= 0
    
    # 4. FX Chain (opcional)
    for effect in channel.fx_chain:
        audio_data = effect.process(audio_data)
    
    return audio_data
```

### Actualización de Parámetros

```python
def set_channel_volume(self, channel_id: int, volume: float):
    """Cambiar volumen de un canal"""
    with self.lock:
        if channel_id in self.channels:
            # Clamp al rango [0, 2] (permitir boost)
            self.channels[channel_id].volume = np.clip(volume, 0, 2)
            
            # Notificar cambio
            self.broadcast_channel_update(channel_id)
            
            # Log con debouncing
            self._log_parameter_change(
                f"Volume ch{channel_id}: {volume:.2f}"
            )
```

### Enrutamiento de Canales

```python
class ChannelRouter:
    """
    Determina qué clientes reciben qué canales.
    """
    def __init__(self, channel_manager):
        self.routes = {}  # {client_id: [channel_ids]}
    
    def can_client_access_channel(self, 
                                  client_id: str,
                                  channel_id: int) -> bool:
        """Verificar permisos de acceso"""
        if client_id not in self.routes:
            # Acceso por defecto: todos los canales
            return True
        
        return channel_id in self.routes[client_id]
```

---

## 🎵 Mezcla de Audio

### AudioMixer

```python
class AudioMixer:
    """
    Mezcla múltiples canales en un stream maestro.
    """
    def __init__(self, channel_manager, num_output_channels=2):
        self.channel_manager = channel_manager
        self.num_output_channels = num_output_channels
        self.master_volume = 1.0
        self.master_limiter = SimpleLimiter(threshold=0.95)

def mix_audio(self, audio_data_by_channel: Dict[int, np.ndarray]) 
              -> np.ndarray:
    """
    Entrada:
      {
        0: array [32, 1],
        1: array [32, 1],
        2: array [32, 1],
        ...
      }
    
    Salida:
      array [32, 2] (stereo mixto)
    """
    
    # 1. Obtener número de muestras
    num_samples = next(iter(audio_data_by_channel.values())).shape[0]
    
    # 2. Inicializar buffer de mezcla (stereo)
    mix_buffer = np.zeros((num_samples, 2), dtype=np.float32)
    
    # 3. Mezclar cada canal
    for ch_id, ch_data in audio_data_by_channel.items():
        # Expandir mono a stereo si es necesario
        if ch_data.shape[1] == 1:
            ch_stereo = np.repeat(ch_data, 2, axis=1)
        else:
            ch_stereo = ch_data
        
        # Aplicar volumen del canal
        channel = self.channel_manager.channels.get(ch_id)
        if channel and not channel.mute:
            ch_stereo *= channel.volume
        
        # Sumar a buffer de mezcla
        mix_buffer += ch_stereo[:, :2]
    
    # 4. Aplicar volumen maestro
    mix_buffer *= self.master_volume
    
    # 5. Limitador (prevenir clipping)
    mix_buffer = self.master_limiter.process(mix_buffer)
    
    # 6. Soft clipping (suavizar picos extremos)
    mix_buffer = np.tanh(mix_buffer)
    
    return mix_buffer
```

### Simple Limiter

```python
class SimpleLimiter:
    """
    Limitador suave para prevenir clipping.
    """
    def __init__(self, threshold=0.9, attack=0.001, release=0.01):
        self.threshold = threshold
        self.attack = attack
        self.release = release
        self.envelope = 0.0
    
    def process(self, audio):
        """Aplicar limitador"""
        # Detección de picos
        peak = np.max(np.abs(audio))
        
        # Seguidor de envolvente (attack/release)
        if peak > self.envelope:
            # Attack rápido
            self.envelope += (peak - self.envelope) * self.attack
        else:
            # Release lento
            self.envelope += (peak - self.envelope) * self.release
        
        # Calcular ganancia de limitador
        if self.envelope > self.threshold:
            gain = self.threshold / self.envelope
        else:
            gain = 1.0
        
        return audio * gain
```

---

## 📦 Compresión y Streaming

### Compresión de Audio

```python
import zlib

class AudioCompressor:
    """
    Comprime audio con zlib para streaming eficiente.
    """
    def __init__(self, level=1):  # level 1 = rápido, 9 = máxima compresión
        self.level = level
        self.compressor = zlib.compressobj(level)
    
    def compress_audio(self, audio: np.ndarray) -> bytes:
        """
        Comprimir array de audio a bytes.
        
        Entrada: [32, 2] float32 stereo
        Salida: ~200-400 bytes (50-70% compresión)
        """
        # 1. Convertir a bytes
        audio_bytes = audio.astype(np.float32).tobytes()
        
        # 2. Comprimir con zlib
        compressed = zlib.compress(audio_bytes, self.level)
        
        # 3. Retornar
        return compressed
    
    def decompress_audio(self, compressed: bytes, 
                        shape: tuple) -> np.ndarray:
        """
        Descomprimir bytes a array de audio.
        """
        # 1. Descomprimir
        audio_bytes = zlib.decompress(compressed)
        
        # 2. Convertir a numpy
        audio = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # 3. Reshape
        return audio.reshape(shape)
```

### Tamaño de Payload

```
Audio sin comprimir:
  32 muestras × 2 canales × 4 bytes (float32) = 256 bytes

Audio comprimido:
  zlib level 1: ~100-150 bytes (50-60% compresión)
  zlib level 6: ~80-100 bytes (70% compresión)
  
Overhead de red:
  Header TCP: 20 bytes
  Header IP: 20 bytes
  Total: ~150-200 bytes transmitidos por bloque
  
Bandwidth @ 48kHz:
  150 bytes × (48000/32) = 225 KB/s por cliente
  ~1.8 Mbps @ 16 clientes
```

---

## 🌐 Servidor WebSocket

### Inicialización

```python
# En websocket_server.py
from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__, static_folder='frontend')
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   ping_timeout=60,
                   ping_interval=25)

@app.route('/')
def index():
    """Servir interfaz web"""
    return send_from_directory('frontend', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """Servir assets estáticos"""
    return send_from_directory('frontend', filename)
```

### Ciclo de Vida de Cliente WebSocket

```python
@socketio.on('connect')
def on_connect(auth):
    """Cliente web se conecta"""
    client_id = request.sid
    logger.info(f"Client connected: {client_id}")
    
    # Registrar cliente
    active_clients[client_id] = {
        'type': 'web',
        'connected_at': time.time(),
        'channels': set(range(16))  # Acceso a todos los canales
    }
    
    # Enviar estado inicial
    emit('server_stats', get_server_stats())
    emit('device_list', get_devices())
    emit('channel_list', get_channels())

@socketio.on('disconnect')
def on_disconnect():
    """Cliente se desconecta"""
    client_id = request.sid
    logger.info(f"Client disconnected: {client_id}")
    
    if client_id in active_clients:
        del active_clients[client_id]

@socketio.on('set_channel_volume')
def on_set_channel_volume(data):
    """Comando: cambiar volumen"""
    channel_id = data['channel_id']
    volume = data['volume']
    
    # Validar rango
    volume = np.clip(float(volume), 0, 2)
    
    # Actualizar
    channel_manager.set_channel_volume(channel_id, volume)
    
    # Broadcast a todos (excepto remitente)
    socketio.emit('channel_volume_changed',
                 {'channel_id': channel_id, 'volume': volume},
                 skip_sid=request.sid)
```

### Broadcast de Audio

```python
def broadcast_audio_chunk(audio_data: np.ndarray):
    """
    Enviar audio a todos los clientes WebSocket.
    
    Ejecutado desde AudioCapture callback (10ms × 100 = 1s)
    """
    
    # Comprimir audio
    compressed = compressor.compress(audio_data)
    
    # Broadcast a todos los clientes web conectados
    socketio.emit('audio_data', {
        'data': base64.b64encode(compressed).decode(),
        'shape': audio_data.shape,
        'timestamp': time.time()
    })
```

---

## 🔌 Servidor Nativo

### Flujo de Conexión Nativa

```
Cliente nativo conecta a :5101 (TCP)
            ↓
    Handshake nativo
            ↓
    Envío de audio frames
            ↓
    Sincronización de estado
            ↓
    Reconexión automática (RF Mode)
```

### Protocolo Binario

```python
class NativeAndroidProtocol:
    """
    Protocolo binario compacto para clientes nativos.
    """
    
    HEADER_SIZE = 16
    MAGIC_NUMBER = 0xA1D10A7C
    PROTOCOL_VERSION = 2
    
    # Tipos de mensaje
    MSG_TYPE_AUDIO = 0x01
    MSG_TYPE_CONTROL = 0x02
    MSG_TYPE_SYNC = 0x03
    
    # Flags
    FLAG_FLOAT32 = 0x01
    FLAG_INT16 = 0x02
    FLAG_COMPRESSED = 0x04
    FLAG_RF_MODE = 0x80

def encode_audio_frame(channels_data: Dict[int, np.ndarray],
                      compressed: bool = True) -> bytes:
    """
    Codificar frame de audio.
    
    Formato:
    - Header (16 bytes)
    - Número de canales (1 byte)
    - Datos de audio (variable)
    """
    
    # Construir header
    flags = FLAG_FLOAT32 | FLAG_COMPRESSED if compressed else FLAG_FLOAT32
    payload_size = sum(ch.nbytes for ch in channels_data.values())
    
    header = struct.pack(
        '!IHHII',  # Network byte order (big-endian)
        MAGIC_NUMBER,
        PROTOCOL_VERSION,
        MSG_TYPE_AUDIO,
        flags,
        payload_size
    )
    
    # Construir payload
    payload = struct.pack('B', len(channels_data))  # Num channels
    for ch_data in channels_data.values():
        payload += ch_data.tobytes()
    
    # Comprimir si es necesario
    if compressed:
        payload = zlib.compress(payload, 1)
        # Actualizar header con tamaño real
        header = struct.pack(
            '!IHHII',
            MAGIC_NUMBER,
            PROTOCOL_VERSION,
            MSG_TYPE_AUDIO,
            flags,
            len(payload)
        )
    
    return header + payload
```

### Manejo de Conexiones Nativas

```python
class NativeAudioServer:
    def __init__(self):
        self.clients = {}  # {socket: ClientHandler}
        self.listen_socket = None
    
    def accept_connections(self):
        """Loop de aceptación de conexiones"""
        while self.running:
            try:
                client_socket, addr = self.listen_socket.accept()
                logger.info(f"Native client connected from {addr}")
                
                # Crear handler en thread
                handler = ClientHandler(
                    client_socket,
                    addr,
                    self.channel_manager
                )
                self.clients[client_socket] = handler
                
                threading.Thread(
                    target=handler.handle_client,
                    daemon=True
                ).start()
                
            except Exception as e:
                logger.error(f"Accept error: {e}")

class ClientHandler:
    def __init__(self, socket, addr, channel_manager):
        self.socket = socket
        self.addr = addr
        self.channel_manager = channel_manager
        self.running = True
    
    def handle_client(self):
        """Manejar cliente nativo individual"""
        # Configurar socket
        self.socket.setsockopt(socket.IPPROTO_TCP, 
                              socket.TCP_NODELAY, 1)
        self.socket.settimeout(config.SOCKET_TIMEOUT)
        
        try:
            while self.running:
                # Recibir comando del cliente
                header = self.socket.recv(16)
                if not header:
                    break  # Cliente desconectó
                
                # Parsear header
                magic, version, msg_type, flags, payload_size = \
                    struct.unpack('!IHHII', header)
                
                if magic != MAGIC_NUMBER:
                    logger.error(f"Invalid magic: {magic}")
                    break
                
                # Recibir payload
                payload = self.socket.recv(payload_size)
                
                # Procesar comando
                self.process_command(msg_type, flags, payload)
        
        except socket.timeout:
            logger.warning(f"Client {self.addr} timeout")
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            self.running = False
            self.socket.close()
```

---

## ⚡ Optimizaciones de Latencia

### Medición de Latencia

```python
class LatencyMonitor:
    """
    Medir latencia end-to-end.
    """
    def __init__(self):
        self.timestamps = {}  # {block_id: timestamp}
        self.latencies = deque(maxlen=100)
    
    def mark_capture(self, block_id):
        """Marcar tiempo de captura"""
        self.timestamps[block_id] = time.time()
    
    def mark_delivery(self, block_id):
        """Marcar tiempo de entrega"""
        if block_id in self.timestamps:
            latency = (time.time() - self.timestamps[block_id]) * 1000
            self.latencies.append(latency)
    
    def get_stats(self):
        """Obtener estadísticas de latencia"""
        if not self.latencies:
            return None
        
        return {
            'avg': np.mean(self.latencies),
            'min': np.min(self.latencies),
            'max': np.max(self.latencies),
            'p99': np.percentile(self.latencies, 99)
        }
```

### Reducción de Latencia: Checklist

| Factor | Original | Optimizado | Ganancia |
|--------|----------|-----------|----------|
| Blocksize | 512 | 32 | 15ms |
| Callbacks | Colas | Directos | 5ms |
| Compresión | zlib L9 | zlib L1 | 2ms |
| TCP Nagle | Habilitado | Deshabilitado | 1ms |
| Buffer Cliente | 4 bloques | 1-2 bloques | 10ms |
| **TOTAL** | ~150ms | ~50ms | **100ms** ✅ |

### Optimizaciones en config.py

```python
# ============ CAPTURA ============
BLOCKSIZE = 32  # ← Ultra-pequeño para baja latencia

# ============ WEBSOCKET ============
WEBSOCKET_PARAM_DEBOUNCE_MS = 50  # Agrupar updates
WEBSOCKET_LATENCY_LOG = False     # Desactivar logging

# ============ SOCKET ============
SOCKET_NODELAY = True             # Deshabilitar Nagle
SOCKET_TIMEOUT = 3.0              # Detección rápida

# ============ RF MODE ============
RF_RECONNECT_DELAY_MS = 1000      # Reconexión rápida
RF_STATE_CACHE_TIMEOUT = 0        # Caché persistente
```

---

## 💾 Gestión de Recursos

### Monitoreo de Memoria

```python
import psutil

class MemoryMonitor:
    def __init__(self):
        self.process = psutil.Process()
        self.initial_memory = self.get_memory_usage()
    
    def get_memory_usage(self):
        """Obtener uso de memoria en MB"""
        return self.process.memory_info().rss / 1024 / 1024
    
    def get_memory_percent(self):
        """Obtener porcentaje de memoria del sistema"""
        return self.process.memory_percent()
    
    def detect_leak(self):
        """Detectar posible leak de memoria"""
        current = self.get_memory_usage()
        # Si crece > 500MB en 1 hora, posible leak
        if current - self.initial_memory > 500:
            logger.warning("Possible memory leak detected")
```

### Gestión de Conexiones

```python
class ConnectionPool:
    """
    Gestiona pool de conexiones con timeout.
    """
    def __init__(self, max_connections=100, timeout=300):
        self.max_connections = max_connections
        self.timeout = timeout
        self.connections = {}
        self.lock = threading.Lock()
    
    def add_connection(self, client_id, socket):
        """Agregar conexión al pool"""
        with self.lock:
            if len(self.connections) >= self.max_connections:
                # Evitar saturación
                oldest = min(self.connections.items(),
                           key=lambda x: x[1]['created_at'])
                self.remove_connection(oldest[0])
            
            self.connections[client_id] = {
                'socket': socket,
                'created_at': time.time(),
                'last_activity': time.time()
            }
    
    def cleanup_idle_connections(self):
        """Limpiar conexiones inactivas"""
        with self.lock:
            now = time.time()
            idle = [cid for cid, conn in self.connections.items()
                   if now - conn['last_activity'] > self.timeout]
            
            for cid in idle:
                logger.info(f"Closing idle connection: {cid}")
                self.remove_connection(cid)
```

### ThreadPool para Envío

```python
from concurrent.futures import ThreadPoolExecutor

class AudioDistributor:
    """
    Distribuye audio a múltiples clientes en paralelo.
    """
    def __init__(self, num_threads=6):
        self.executor = ThreadPoolExecutor(max_workers=num_threads)
        self.clients = []
    
    def distribute_audio(self, audio_data):
        """Enviar audio a todos los clientes en paralelo"""
        futures = []
        
        for client in self.clients:
            # Enviar en thread pool, no bloquea
            future = self.executor.submit(
                self._send_to_client,
                client,
                audio_data
            )
            futures.append(future)
        
        # Esperar a que terminen (con timeout)
        for future in futures:
            try:
                future.result(timeout=0.005)  # 5ms max
            except TimeoutError:
                logger.warning("Send timeout")
    
    def _send_to_client(self, client, audio_data):
        """Enviar audio a un cliente"""
        try:
            client.send(audio_data)
        except Exception as e:
            logger.error(f"Send error: {e}")
```

---

## 🔍 Troubleshooting Avanzado

### Problema: Alta Latencia

**Síntomas**: Delay perceptible entre entrada y salida

**Diagnóstico**:
```python
# Habilitar logging de latencia
config.WEBSOCKET_LATENCY_LOG = True

# Ver logs de timestamps
grep "latency" logs/*.log | tail -100
```

**Soluciones**:
1. Reducir blocksize: `BLOCKSIZE = 16`
2. Aumentar ThreadPool: `AUDIO_SEND_POOL_SIZE = 8`
3. Verificar WiFi: Cambiar a Ethernet
4. Reducir compresión: zlib level 0-1

### Problema: CPU Alto

**Síntomas**: > 30% CPU con 4 canales

**Diagnóstico**:
```python
import cProfile

# Perfilar en desarrollo
cProfile.run('main()', sort='cumtime')
# Ver qué función consume más CPU
```

**Causas Comunes**:
- Compresión muy alta (zlib level 9)
- AudioMixer procesando demasiados canales
- Logging excesivo

**Soluciones**:
```python
# Sin compresión (Opus removido)
# Disminuir frecuencia de logging
logger.setLevel(logging.WARNING)
# Limitar número de canales activos
CHANNEL_LIMIT = 8
```

### Problema: Clientes No Conectan

**Síntomas**: "Connection refused" en cliente nativo

**Verificar**:
```powershell
# Puerto 5101 disponible
netstat -ano | findstr 5101

# Firewall permite conexión
netsh advfirewall firewall show rule name="audio-monitor"

# Servidor escuchando
Get-NetTCPConnection | findstr 5101
```

**Soluciones**:
```python
# En config.py
NATIVE_HOST = '0.0.0.0'  # Escuchar en todos los interfaces
NATIVE_PORT = 5101

# Verificar en logs
grep "listening" logs/*.log
```

### Problema: Audio Cortado

**Síntomas**: Clicks, pops, discontinuidades

**Causas**:
- Buffer insuficiente
- CPU saturado
- Reconexión de cliente

**Debug**:
```python
# Activar detección de gaps
class AudioGapDetector:
    def __init__(self):
        self.last_block_id = -1
    
    def detect_gap(self, block_id):
        if block_id != self.last_block_id + 1:
            logger.error(f"Gap detected: {self.last_block_id} → {block_id}")
        self.last_block_id = block_id
```

---

## 📊 Benchmarks

### Especificaciones de Performance

```
Condición: 4 canales @ 48kHz, 16 clientes WebSocket

Métrica              Valor       Límite
─────────────────────────────────────
CPU total           8-12%        < 30%
Memoria             150MB        < 500MB
Latencia promedio   55ms         < 100ms
Latencia P99        90ms         < 150ms
Jitter              ± 10ms       < ± 50ms
Conexiones/s        100          Completa en 5s
Throughput          28Mbps       Sustentable
Clientes simultáneos 50+         Teórico
```

---

**Última actualización**: Enero 2026  
**Versión Guía Técnica**: 1.0
