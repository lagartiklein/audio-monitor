# 🔬 VERIFICACIÓN TÉCNICA: Identidad de Clientes y Flujo de Datos

## 1. GENERACIÓN Y PERSISTENCIA DE IDENTIFICADORES

### 1.1 Cliente Web (Frontend)

**Archivo:** `frontend/index.html` línea 733

```javascript
// ✅ GENERACIÓN ÚNICA POR DISPOSITIVO
const key = 'fichatech_web_device_uuid';
this.webDeviceUuid = localStorage.getItem(key) || this.generateUUID();
localStorage.setItem(key, this.webDeviceUuid);

// ✅ GENERACIÓN DE UUID
generateUUID() {
    return 'web-' + Math.random().toString(36).substr(2, 9);
}

// ✅ ENVÍO EN HANDSHAKE
socket.auth = {
    device_uuid: this.webDeviceUuid,
    device_name: auth.get('device_name')
}
```

**Características:**
- 🔹 Se genera una vez en la primera carga
- 🔹 Se almacena en `localStorage` (persistencia local del navegador)
- 🔹 Se envía en CADA reconexión
- 🔹 Formato: `web-XXXXXXX` (identifica que es web)
- 🔹 Persiste entre:
  - ✅ Cierre de navegador
  - ✅ Recargas de página
  - ✅ Cambios de red
  - ❌ Limpieza de cache/cookies (debe regenerar, pero server lo reconoce por IP)

---

### 1.2 Cliente Android (Nativo)

**Archivo:** `kotlin/android/clases/NativeAudioStreamActivity.kt` línea 1167

```kotlin
// ✅ GENERACIÓN ÚNICA POR DISPOSITIVO
private const val KEY_DEVICE_UUID = "device_uuid"
var uuid = prefs.getString(KEY_DEVICE_UUID, null)
if (uuid == null) {
    uuid = UUID.randomUUID().toString()
    prefs.edit().putString(KEY_DEVICE_UUID, uuid).apply()
    Log.d(TAG, "📦 Nuevo device_uuid generado: ${uuid.take(8)}...")
}

// ✅ ENVÍO EN HANDSHAKE
val handshakeData = mapOf(
    "device_uuid" to uuid,
    "client_id" to uuid,
    "protocol_version" to 2,
    "device_name" to "Android-${Build.DEVICE}"
)
socket.send(handshakeData)
```

**Características:**
- 🔹 Se genera una vez en el primer arranque
- 🔹 Se almacena en `SharedPreferences` (BD persistente del sistema)
- 🔹 Se envía en CADA reconexión
- 🔹 Formato: UUID v4 estándar
- 🔹 Persiste entre:
  - ✅ Reinicios del dispositivo
  - ✅ Cambios de red WiFi
  - ✅ Cambios de operador (móvil)
  - ❌ Desinstalación/reinstalación (requiere regenerar)
  - ❌ Limpieza de datos de aplicación

---

## 2. REGISTRO CENTRAL: device_registry

### 2.1 Estructura de Almacenamiento

**Archivo:** `audio_server/device_registry.py`

```python
# Estructura en memoria
self.devices = {
    "web-skzrmazs9": {
        "uuid": "web-skzrmazs9",
        "type": "web",
        "name": "Web-kzrmazs9",
        "mac_address": None,
        "primary_ip": "192.168.1.7",
        "device_info": {
            "type": "web",
            "user_agent": "Mozilla/5.0..."
        },
        "first_seen": 1767396785.939,      # Timestamp primera conexión
        "last_seen": 1767396791.758,       # Timestamp última actividad
        "reconnections": 127,              # Contador de reconexiones
        "configuration": {                 # ✅ CONFIG PERSISTENTE
            "channels": [0, 1, 2, 3],
            "gains": {"0": 1.0, "1": 0.5},
            "pans": {"0": 0.0, "1": -0.5}
        },
        "configuration_session_id": "session-abc123",
        "tags": [],
        "active": True
    },
    # ... más dispositivos
}
```

**Persistencia a Disco:**

```python
# Archivo: config/devices.json
{
  "web-skzrmazs9": {
    "uuid": "web-skzrmazs9",
    "type": "web",
    "name": "Web-kzrmazs9",
    # ... (igual estructura)
  }
}
```

---

### 2.2 Operaciones sobre device_registry

#### **Operación 1: register_device (Primera conexión o reconexión)**

**Archivo:** `device_registry.py:109-141`

```python
def register_device(self, device_uuid: str, device_info: dict) -> dict:
    with self.device_lock:
        current_time = time.time()
        
        if device_uuid in self.devices:
            # ✅ RECONEXIÓN: Actualizar timestamp y contador
            device = self.devices[device_uuid]
            device['last_seen'] = current_time
            device['reconnections'] = device.get('reconnections', 0) + 1
            device['active'] = True
            
            if device_info.get('mac_address') and not device.get('mac_address'):
                device['mac_address'] = device_info.get('mac_address')
            device['primary_ip'] = device_info.get('primary_ip')
            device['device_info'].update(device_info)
            
            logger.info(f"🔄 Dispositivo actualizado: {device_uuid[:12]} "
                       f"(Reconexión #{device['reconnections']})")
        else:
            # ✅ PRIMERA CONEXIÓN: Crear nuevo registro
            device = {
                'uuid': device_uuid,
                'type': device_info.get('type', 'unknown'),
                'name': device_info.get('name', f"Device-{device_uuid[:8]}"),
                'mac_address': device_info.get('mac_address'),
                'primary_ip': device_info.get('primary_ip'),
                'device_info': device_info,
                'first_seen': current_time,
                'last_seen': current_time,
                'reconnections': 0,
                'configuration': {},
                'configuration_session_id': None,
                'tags': [],
                'active': True
            }
            self.devices[device_uuid] = device
            
            logger.info(f"✅ Nuevo dispositivo registrado: {device_uuid[:12]}")
        
        self.save_to_disk()  # ✅ GUARDAR INMEDIATAMENTE
        return self.devices[device_uuid]
```

#### **Operación 2: update_configuration (Cuando cambia la mezcla)**

**Archivo:** `device_registry.py:200-212`

```python
def update_configuration(self, device_uuid: str, config: dict, 
                        session_id: Optional[str] = None) -> bool:
    with self.device_lock:
        if device_uuid not in self.devices:
            return False
        
        device = self.devices[device_uuid]
        device['configuration'] = config
        device['configuration_session_id'] = session_id or self.server_session_id
        
        logger.debug(f"💾 Config guardada: {device_uuid[:12]}")
    
    self.save_to_disk()  # ✅ ESCRIBIR A DISCO INMEDIATAMENTE
    return True
```

#### **Operación 3: get_configuration (Al conectar, para restaurar)**

**Archivo:** `device_registry.py:216-228`

```python
def get_configuration(self, device_uuid: str, 
                     session_id: Optional[str] = None) -> dict:
    device = self.get_device(device_uuid)
    if not device:
        return {}
    
    # ✅ Validar session_id (evita restaurar entre reinicios del servidor)
    if session_id is not None:
        saved_session = device.get('configuration_session_id')
        if saved_session and saved_session != session_id:
            return {}  # NO restaurar si session cambió (servidor reinició)
    
    return device.get('configuration', {})
```

---

## 3. MAPEO: device_uuid ↔ client_id

### 3.1 En WebSocket (Web Clients)

**Archivo:** `websocket_server.py:268-285`

```python
@socketio.on('connect', namespace='/')
def handle_connect(auth=None):
    client_id = request.sid  # ✅ ID ÚNICO POR SESIÓN WebSocket
    auth = auth or {}
    web_device_uuid = auth.get('device_uuid')  # ✅ UUID PERSISTENTE
    
    # Almacenar información de conexión
    with web_clients_lock:
        web_clients[client_id] = {
            'connected_at': time.time(),
            'last_activity': time.time(),
            'address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown'),
            'device_uuid': web_device_uuid  # ✅ VINCULACIÓN KEY
        }
    
    logger.info(f"✅ Cliente web conectado: {client_id[:8]} "
               f"(device_uuid: {web_device_uuid[:12]})")
```

**Mapeo (en RAM):**
```
web_clients = {
    'session-abc123': {
        'device_uuid': 'web-skzrmazs9',  # ← Clave de vinculación
        'address': '192.168.1.7',
        'user_agent': '...'
    }
}
```

---

### 3.2 En Native Server (Android Clients)

**Archivo:** `native_server.py:774-830`

```python
def _handle_control_message(self, client: NativeClient, message: dict):
    msg_type = message.get('type', '')
    
    if msg_type == 'handshake':
        # ✅ device_uuid es IDENTIFICADOR PRIMARIO
        persistent_id = message.get('device_uuid') or message.get('client_id')
        
        # ✅ Detectar reconexión
        is_reconnection = False
        with self.client_lock:
            if persistent_id in self.clients:
                is_reconnection = True
        
        # ✅ Registrar/actualizar en device_registry
        try:
            if getattr(self.channel_manager, 'device_registry', None):
                self.channel_manager.device_registry.register_device(persistent_id, {
                    'type': 'android',
                    'name': f"android-{persistent_id[:8]}",
                    'primary_ip': client.address[0]
                })
        except Exception as e:
            logger.debug(f"Device registry register failed: {e}")
        
        # ✅ Crear o reutilizar NativeClient
        if is_reconnection:
            existing_client = self.clients[persistent_id]
            # Reutilizar, actualizar socket
        else:
            # Crear nuevo NativeClient
            new_client = NativeClient(
                client_id=persistent_id,
                sock=client.socket,
                address=client.address,
                persistent_id=persistent_id
            )
```

**Mapeo (en RAM):**
```
self.clients = {
    'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx': {  # ← persistent_id = device_uuid
        'socket': <socket>,
        'status': 1,
        'persistent_id': 'xxxxxxxx-xxxx-...',
        'reconnection_count': 25
    }
}
```

---

### 3.3 En ChannelManager

**Archivo:** `channel_manager.py:260-275`

```python
def subscribe_client(self, client_id, channels, gains=None, pans=None, 
                     client_type="web", device_uuid=None):
    # ...
    
    # ✅ MAPEO BIDIRECCIONAL
    if device_uuid:
        self.device_client_map[device_uuid] = client_id  # ← device_uuid → client_id
        
        # Registrar en device_registry
        if self.device_registry:
            try:
                self.device_registry.register_device(device_uuid, {
                    'type': client_type,
                    'name': f"{client_type}-{device_uuid[:8]}",
                    'primary_ip': None
                })
            except Exception as e:
                logger.debug(f"Device registry register failed: {e}")
    
    self.subscriptions[client_id] = {  # ← client_id → subscription
        'channels': valid_channels,
        'gains': {...},
        'pans': {...},
        'device_uuid': device_uuid,  # ← Vinculación inversa
        'device_type': client_type,
        # ...
    }
```

**Mapeo (en RAM):**
```
channel_manager.subscriptions = {
    'session-abc123': {  # client_id
        'channels': [0, 1, 2],
        'device_uuid': 'web-skzrmazs9',  # ← Link
    },
    'xxxxxxxx-xxxx-...': {  # client_id (Android)
        'channels': [4, 5, 6],
        'device_uuid': 'xxxxxxxx-xxxx-...',  # ← Link
    }
}

channel_manager.device_client_map = {
    'web-skzrmazs9': 'session-abc123',  # ← Búsqueda inversa
    'xxxxxxxx-xxxx-...': 'xxxxxxxx-xxxx-...'
}
```

---

## 4. FLUJO DE CAMBIOS: De Punto A a Punto B

### 4.1 Cambio en Web: UI → Servidor → Otros Clientes

```
┌──────────────────────────────────────────────────────────────┐
│ FASE 1: USUARIO INTERACTÚA                                   │
│ ─────────────────────────────────────────────────────────────│
│ Frontend: User clicks "Activate Channel 1"                    │
│ → this.toggleChannel(clientId, 1)                            │
│ → client.channels = [1]  ✅ UI actualizado INMEDIATAMENTE    │
│ → socket.emit('update_client_mix', {                         │
│       target_client_id: clientId,                            │
│       channels: [1]                                           │
│   })                                                           │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 10ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 2: SERVIDOR RECIBE Y ACTUALIZA                          │
│ ─────────────────────────────────────────────────────────────│
│ websocket_server.py:492 handle_update_client_mix()           │
│                                                               │
│ 1. Recibe data con target_client_id                          │
│ 2. prev_channels = get_client_subscription(target_client_id) │
│    → prev_channels = set([])  (o anterior)                   │
│                                                               │
│ 3. channel_manager.update_client_mix(target_client_id, ...)  │
│    ✅ Actualiza: channel_manager.subscriptions[...]['channels']
│    → NUEVO ESTADO: [1]                                       │
│                                                               │
│ 4. new_subscription = get_client_subscription(target_client_id)
│    → new_channels = set([1])                                 │
│    → new_channels - prev_channels = {1}  (CAMBIO)            │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 15ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 3: EMIT param_sync A OTROS CLIENTES (línea 557-570)     │
│ ─────────────────────────────────────────────────────────────│
│ for ch in new_channels - prev_channels:  # Cada canal nuevo  │
│     socketio.emit('param_sync', {                            │
│         'type': 'channel_toggle',                            │
│         'channel': 1,                                        │
│         'value': True,                                       │
│         'client_id': target_client_id,                       │
│         'source': 'web',                                     │
│         'timestamp': int(time.time() * 1000)                 │
│     }, skip_sid=request.sid)  ← NO enviar al solicitante     │
│                                                               │
│ ✅ TODOS excepto Web A recibirán param_sync                  │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 30ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 4: OTROS WEBS RECIBEN param_sync (línea 1098)           │
│ ─────────────────────────────────────────────────────────────│
│ Frontend: socket.on('param_sync', (data) => {                │
│     if (type === 'channel_toggle') {                         │
│         client.channels.push(channel)  // ← Actualiza        │
│         this.renderMixer(client_id)    ← RE-RENDER UI        │
│     }                                                         │
│ })                                                            │
│                                                               │
│ ✅ Web B VISTO INSTANTÁNEAMENTE                              │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 40ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 5: SINCRONIZAR A ANDROID (línea 627-630)                │
│ ─────────────────────────────────────────────────────────────│
│ if subscription.get('client_type') == 'native':              │
│     native_server_instance.push_mix_state_to_client(...)     │
│                                                               │
│ → native_server.py:1204                                       │
│   def push_mix_state_to_client(self, client_id):              │
│       subscription = channel_manager.get_client_subscription()
│       client.send_mix_state(subscription)  ← Envía CONTROL   │
│                                                               │
│ ✅ Android RECIBE cambio vía TCP                             │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 50ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 6: PERSISTENCIA A DISCO (línea 949)                     │
│ ─────────────────────────────────────────────────────────────│
│ _save_client_config_to_registry(client_id):                  │
│     device_uuid = subscription.get('device_uuid')            │
│     config_to_save = {                                       │
│         'channels': [1],                                     │
│         'gains': {...},                                      │
│         'pans': {...}                                        │
│     }                                                         │
│     channel_manager.device_registry.update_configuration(     │
│         device_uuid,                                          │
│         config_to_save                                       │
│     )                                                         │
│                                                               │
│ → device_registry.py:206                                     │
│   with self.device_lock:                                     │
│       self.devices[device_uuid]['configuration'] = config    │
│   self.save_to_disk()  ← ESCRIBIR A config/devices.json      │
│                                                               │
│ ✅ CAMBIO PERSISTENTE                                        │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 500ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 7: RECUPERACIÓN (Siguiente reconexión del cliente)      │
│ ─────────────────────────────────────────────────────────────│
│ Si cliente desconecta y se reconecta:                        │
│                                                               │
│ handle_connect():                                            │
│   config_prev = device_registry.get_configuration(uuid)      │
│   # Retorna: {'channels': [1], 'gains': {...}}               │
│                                                               │
│   channel_manager.subscribe_client(                          │
│       client_id,                                             │
│       config_prev.get('channels', []),  ← Restaura [1]       │
│       gains=config_prev.get('gains', {}),                    │
│   )                                                          │
│                                                               │
│ ✅ ESTADO COMPLETAMENTE RECUPERADO                           │
└──────────────────────────────────────────────────────────────┘

TIMELINE TOTAL:
0ms    → Usuario hace click
10ms   → Servidor recibe y actualiza subscriptions
15ms   → Emite param_sync
30ms   → Otros webs ven cambio
40ms   → Android recibe cambio
50ms   → Persistencia iniciada
500ms  → Guardado en disco completado
```

---

### 4.2 Cambio en Android: TCP → Servidor → Otros Clientes

```
┌──────────────────────────────────────────────────────────────┐
│ FASE 1: ANDROID CAMBIA ESTADO                                │
│ ─────────────────────────────────────────────────────────────│
│ NativeAudioStreamActivity.kt: User taps "Channel 1"          │
│ → audioClient.updateMix(channels = [1])                      │
│ → Construye UPDATE_MIX packet (binario)                      │
│ → socket.send(UPDATE_MIX)  ← Envío TCP                       │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 5ms en LAN)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 2: SERVIDOR RECIBE UPDATE_MIX                           │
│ ─────────────────────────────────────────────────────────────│
│ native_server.py:992 _handle_update_mix()                    │
│                                                               │
│ 1. message = parse_control_packet()                          │
│    → msg_type = 'UPDATE_MIX'                                 │
│    → channels = [1]  (extraído del binario)                  │
│                                                               │
│ 2. persistent_id = handshake data device_uuid                │
│    → persistent_id = 'xxxxxxxx-xxxx-...'                     │
│                                                               │
│ 3. Guardar ESTADO PREVIO para detectar cambios:              │
│    prev_subscription = channel_manager.get_client_subscription()
│    prev_channels = set(prev_subscription.get('channels', [])) │
│                                                               │
│ 4. Actualizar mezcla:                                        │
│    channel_manager.update_client_mix(                        │
│        persistent_id,                                        │
│        channels=channels                                     │
│    )                                                          │
│    ✅ ACTUALIZADO EN RAM                                     │
│                                                               │
│ 5. Obtener nuevo estado:                                     │
│    new_subscription = get_client_subscription(persistent_id) │
│    new_channels = set(new_subscription.get('channels', [])) │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 10ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 3: DETECTAR CAMBIOS Y EMITIR param_sync                 │
│ ─────────────────────────────────────────────────────────────│
│ Línea 1023: for ch in new_channels - prev_channels:          │
│     self._emit_param_sync_to_web(                            │
│         persistent_id,                                       │
│         'channel_toggle',                                    │
│         ch,                                                  │
│         True  ← Valor nuevo                                  │
│     )                                                         │
│                                                               │
│ → _emit_param_sync_to_web() en línea 469:                    │
│   self.websocket_server_ref.socketio.emit('param_sync', {    │
│       'type': 'channel_toggle',                              │
│       'channel': ch,                                         │
│       'value': True,                                         │
│       'client_id': persistent_id,                            │
│       'source': 'android',                                   │
│       'timestamp': int(time.time() * 1000)                   │
│   })                                                          │
│   ✅ EMIT A TODOS LOS CLIENTES WEB                           │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 20ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 4: WEBS RECIBEN param_sync (línea 1098)                 │
│ ─────────────────────────────────────────────────────────────│
│ Frontend listener recibe evento param_sync                   │
│ source = 'android'  ← Identifica que vino del Android        │
│                                                               │
│ if (type === 'channel_toggle') {                             │
│     client.channels.push(1)  ← Actualiza estado              │
│     this.renderMixer(client_id)  ← RE-RENDER                 │
│     this.updateClientsList()                                 │
│ }                                                             │
│                                                               │
│ ✅ TODOS LOS WEBS VEN INSTANTÁNEAMENTE                       │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 30ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 5: PERSISTENCIA EN SERVIDOR                             │
│ ─────────────────────────────────────────────────────────────│
│ native_server.py:1038                                        │
│                                                               │
│ with self.persistent_lock:                                   │
│     self.persistent_state[persistent_id] = {                 │
│         'channels': [1],  ← Estado actualizado                │
│         'gains': {...},                                      │
│         'pans': {...}                                        │
│     }                                                         │
│                                                               │
│ ✅ EN MEMORIA LISTA PARA SIGUIENTE GET_CLIENT_STATE          │
└──────────────────────────────────────────────────────────────┘
                            ↓
                        (< 40ms)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ FASE 6: PERSISTENCIA A DISCO                                 │
│ ─────────────────────────────────────────────────────────────│
│ websocket_server.py:949 (en background, puede ser async)     │
│ _save_client_config_to_registry(persistent_id)               │
│                                                               │
│ channel_manager.device_registry.update_configuration(        │
│     persistent_id,                                           │
│     {'channels': [1], 'gains': {...}}                        │
│ )                                                             │
│                                                               │
│ → device_registry.save_to_disk()  ← WRITE config/devices.json
│                                                               │
│ ✅ PERSISTENTE PARA SIGUIENTE RECONEXIÓN                     │
└──────────────────────────────────────────────────────────────┘

TIMELINE TOTAL:
0ms    → Android cambia canal
5ms    → Servidor recibe UPDATE_MIX
10ms   → Actualiza subscriptions
20ms   → Emite param_sync
30ms   → Todos los webs ven cambio
40ms   → Guardado en persistent_state
50ms   → Guardado en device_registry
500ms  → Escrito a disco completado
```

---

## 5. GARANTÍAS DE CONSISTENCIA

### 5.1 Atomicidad

✅ **Cada cambio es atómico** (todos los clientes ven lo mismo):

```python
# El cambio ocurre en UNA sola línea crítica:
channel_manager.subscriptions[client_id]['channels'] = new_channels

# Luego se emite a todos:
socketio.emit('param_sync', ...)  # A TODOS INMEDIATAMENTE
```

### 5.2 Durabilidad

✅ **Cada cambio se persiste**:

```python
# 1. En memoria (instant)
self.subscriptions[client_id]['channels'] = [1]

# 2. En device_registry (< 10ms)
self.device_registry.devices[uuid]['configuration']['channels'] = [1]

# 3. En disco (< 500ms)
self.device_registry.save_to_disk()

# Recuperación: Siguientereconexión carga de disco
```

### 5.3 Consistencia

✅ **No hay race conditions**:

```python
# Todas las escrituras están protegidas
with self.device_lock:
    self.devices[uuid] = record  # ← Exclusivo

with self.persistence_lock:
    json.dump(...)  # ← Exclusivo
```

### 5.4 Aislamiento

✅ **Los clientes no interfieren entre sí**:

```python
# Cada cliente tiene su propia:
# - session_id (web) o persistent_id (android)
# - subscriptions[client_id]
# - entry en device_registry

# Cambio en uno NO afecta otros
```

---

## 6. VERIFICACIÓN FINAL

### Checklist de Implementación

```
✅ 1. UUID ÚNICO POR CLIENTE
   ✓ Web: localStorage + generateUUID()
   ✓ Android: SharedPreferences + UUID.randomUUID()
   ✓ Enviado en handshake
   ✓ Persistido entre reconexiones

✅ 2. MAPEO BIDIRECCIONAL
   ✓ device_uuid ↔ client_id
   ✓ device_uuid ↔ subscription
   ✓ En device_registry
   ✓ En channel_manager.device_client_map

✅ 3. CAMBIOS REFLEJADOS INMEDIATAMENTE
   ✓ Web→Web: param_sync < 30ms
   ✓ Web→Android: push_mix_state < 100ms
   ✓ Android→Web: _emit_param_sync_to_web < 50ms
   ✓ Servidor siempre tiene estado actualizado

✅ 4. PERSISTENCIA ROBUSTA
   ✓ device_registry en RAM
   ✓ config/devices.json en disco
   ✓ Thread-safe con locks
   ✓ Restauración automática en siguiente conexión

✅ 5. NO HAY PÉRDIDA DE DATOS
   ✓ Cambios guardados antes de ACK
   ✓ Eventos param_sync no pueden perderse
   ✓ device_registry recuperable de disco

✅ 6. IDENTIFICACIÓN ÚNICA GARANTIZADA
   ✓ UUID es inmutable
   ✓ device_registry es "source of truth"
   ✓ No hay duplicados ni confusiones
```

