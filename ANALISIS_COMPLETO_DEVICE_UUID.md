# ✅ Análisis Completo: Flujo de Audio y Persistencia de Dispositivos

## 📋 Resumen Ejecutivo

Se ha implementado un sistema de **identidad única y persistencia de dispositivos** que funciona así:

- **Android se identifica con un UUID único** que se persiste en `SharedPreferences` del teléfono
- **El servidor Python mantiene ese UUID** e identifica al dispositivo incluso si desconecta/reconecta
- **La web (control center) también tiene UUID único** almacenado en `localStorage`
- **Los cambios de mezcla (canales/gains/pans) se persisten por dispositivo**, no por cliente TCP temporal
- **Al reconectar, el dispositivo restaura automáticamente su estado** (canales activos + mezcla)
- **Si reinicias el servidor, el estado NO se restaura** (pero si desconectas y reconectas SIN reiniciar, SÍ se restaura)

---

## 🔄 Flujo: Desde Arranque Servidor hasta Audio a Android

### 1️⃣ **Arranque del Servidor Python** (`main.py`)

```
AudioServerApp.start_server_with_device(device_id)
  ├─ Crea DeviceRegistry (persiste en config/devices.json)
  ├─ Genera server_session_id (cambia cada arranque del servidor)
  ├─ Inyecta session_id en DeviceRegistry y ChannelManager
  ├─ Crea ChannelManager (8 canales, gestiona suscripciones por cliente)
  ├─ Crea NativeAudioServer en puerto TCP 5101 (escucha conexiones RF)
  └─ Crea WebSocket server en puerto 5100 (controla desde web)
```

**Relevancia de `server_session_id`**: Asegura que los dispositivos NO restauren estado si el servidor se reinicia, pero SÍ lo restauran si es una desconexión temporal.

### 2️⃣ **Cliente Android (Kotlin) Conecta**

#### Generación de UUID en la Activity:
```kotlin
// NativeAudioStreamActivity.kt
private fun getDeviceUUID(): String {
    val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    var uuid = prefs.getString(KEY_DEVICE_UUID, null)
    if (uuid == null) {
        uuid = UUID.randomUUID().toString()
        prefs.edit().putString(KEY_DEVICE_UUID, uuid).apply()
    }
    return uuid
}
```

**Primera ejecución**: Genera un UUID y lo guarda.
**Ejecutaciones posteriores**: Recupera el mismo UUID de SharedPreferences.

#### Creación de Clientes con UUID:
```kotlin
// NativeAudioStreamActivity.kt (línea ~720)
val deviceUUID = getDeviceUUID()
val nativeClient = NativeAudioClient(deviceUUID = deviceUUID)  // Pasa UUID
val udpClient = UDPAudioClient()  // Para UDP

// Se conectan al servidor
nativeClient.connect(serverIP, 5101)
udpClient.connect(serverIP, 5102, handshakeJson, channels)
```

### 3️⃣ **Handshake TCP (RF Mode)**

Android envía a servidor en TCP 5101:

```json
{
  "type": "handshake",
  "client_id": "550e8400-e29b-41d4-a716-446655440000",    // UUID persistente
  "device_uuid": "550e8400-e29b-41d4-a716-446655440000",   // ✅ NUEVO
  "device_type": "android",
  "protocol_version": 2,
  "rf_mode": true,
  "persistent": true,
  "auto_reconnect": true
}
```

**¿Qué sucede en el servidor?** (`native_server.py`, línea ~465)

```python
def _handle_control_message(self, client: NativeClient, message: dict):
    if msg_type == 'handshake':
        # ✅ Preferir device_uuid si viene; fallback a client_id
        persistent_id = message.get('device_uuid') or message.get('client_id')
        
        # ✅ Registrar dispositivo en DeviceRegistry
        if self.channel_manager.device_registry:
            self.channel_manager.device_registry.register_device(persistent_id, {
                'type': 'android',
                'name': message.get('device_name'),
                'primary_ip': client.address[0],
                'client_id': message.get('client_id'),
                ...
            })
        
        # ✅ Buscar estado persistente (canales + mezcla)
        restored_state = None
        if message.get('auto_reconnect'):
            # Primero: búsqueda en cache de memoria
            if persistent_id in self.persistent_state:
                restored_state = self.persistent_state[persistent_id]
            
            # Fallback: búsqueda en DeviceRegistry (si otra sesión)
            if restored_state is None and self.channel_manager.device_registry:
                session_id = self.channel_manager.server_session_id
                restored_state = self.channel_manager.device_registry.get_configuration(
                    persistent_id,
                    session_id=session_id
                )
        
        # ✅ Suscribir cliente (con estado restaurado si existe)
        self.channel_manager.subscribe_client(
            persistent_id,
            restored_state['channels'] if restored_state else [],
            client_type="native",
            device_uuid=persistent_id  # ✅ Registra el UUID
        )
```

### 4️⃣ **Flujo de Audio Multicanal**

```
AudioCapture (interfaz de audio del PC)
  └─ Emite bloques de audio (48kHz, float32, multicanal)
      ├─ NativeAudioServer.on_audio_data()
      │   └─ Para cada cliente TCP:
      │       ├─ Obtiene suscripción: qué canales tiene activos
      │       ├─ Arma paquete binario (magic + header + payload int16/float32)
      │       └─ Envía por TCP (1472 bytes típico)
      │
      └─ WebAudioHandler.on_audio_data()  (si hay clientes web suscritos)
          └─ Emite por Socket.IO
```

**Formato del paquete RF** (binario, muy eficiente):
- Magic number: 0xA1D10A7C (4 bytes)
- Version: 0x02 (2 bytes)
- Type | Flags: 0x01 | 0x02 (int16 encoding) | 0x80 (RF mode) (2 bytes)
- Timestamp: ms (4 bytes)
- Payload length: (4 bytes)
- **Payload**:
  - Sample position: 8 bytes (sincronización)
  - Channel mask: 4 bytes (qué canales están activos)
  - Audio data: sample_count × num_channels × 2 bytes (int16)

### 5️⃣ **Control desde la Web (Control Center)**

**Web se identifica con UUID** en `frontend/index.html`:

```javascript
getOrCreateWebDeviceUuid() {
    const key = 'fichatech_web_device_uuid';
    let v = localStorage.getItem(key);
    if (v) return v;
    
    v = crypto.randomUUID ? crypto.randomUUID() : 'web-' + Math.random().toString(16).slice(2);
    localStorage.setItem(key, v);
    return v;
}
```

**Conecta con auth**:
```javascript
this.socket = io({
    auth: {
        device_uuid: this.webDeviceUuid,
        device_name: 'control-center'
    }
});
```

**Control**: web envía eventos para cambiar mezcla de Android:

```javascript
socket.emit('update_client_mix', {
    target_client_id: androidUUID,  // UUID de Android
    channels: [0, 1, 2],             // Canales a activar
    gains: {0: 1.0, 1: 0.8},        // Ganancias
    pans: {0: 0.0, 1: -0.5}         // Panoramas
});
```

**Servidor actualiza** (`channel_manager.py`, línea ~304):

```python
def update_client_mix(self, client_id, channels=None, gains=None, ...):
    # Actualiza suscripción en memory
    sub = self.subscriptions[client_id]
    sub['channels'] = channels
    sub['gains'] = gains
    ...
    
    # ✅ Persiste en DeviceRegistry (por device_uuid)
    device_uuid = sub.get('device_uuid')
    if device_uuid and self.device_registry:
        self.device_registry.update_configuration(
            device_uuid,
            {
                'channels': channels,
                'gains': gains,
                'pans': pans,
                ...
            },
            session_id=self.server_session_id
        )
```

### 6️⃣ **Reconexión: Android se Desconecta y Vuelve**

```
Android desconecta (red perdida, cierra app, etc.)
  └─ NativeAudioServer detecta que el socket está muerto
      ├─ Obtiene la suscripción actual (canales activos + mezcla)
      ├─ Guarda en cache en memoria: persistent_state[device_uuid]
      └─ Guarda en disco: DeviceRegistry (si timeout>0)

Android reconecta (sin reiniciar servidor)
  ├─ Genera mismo device_uuid (estaba en SharedPreferences)
  ├─ Envía handshake con device_uuid
  ├─ Servidor busca en cache: persistent_state[device_uuid] ✅ ENCONTRÓ
  ├─ Restaura canales + mezcla automáticamente
  └─ Cliente recibe audio en los mismos canales
```

### 7️⃣ **Reinicio del Servidor**

```
Servidor se reinicia
  ├─ Genera nuevo server_session_id
  ├─ Borra todo el persistent_state en memoria
  ├─ Lee DeviceRegistry desde disco
  │   └─ Pero la configuración tiene session_id_old, no session_id_new
  │
  Android reconecta (después del reinicio)
  ├─ Envía handshake con device_uuid
  ├─ Servidor NO encuentra en cache
  ├─ Busca en DeviceRegistry, pero session_id NO coincide
  └─ Resultado: cliente conecta CON CERO CANALES (limpio)
```

---

## 📊 Tablas de Estado

### Tabla 1: Persistencia de Dispositivos

| Ubicación | Tipo | Clave | Duración | Ejemplo |
|-----------|------|-------|----------|---------|
| **Android SharedPreferences** | Persistente | `device_uuid` | Hasta desinstalar app | `550e8400-e29b-41d4...` |
| **Web localStorage** | Persistente | `fichatech_web_device_uuid` | Hasta limpiar datos | `550e8400-e29b-41d4...` |
| **Servidor memoria** | Cache | `persistent_state[device_uuid]` | Hasta reinicio servidor | Canales + mezcla |
| **Servidor disco** | Persistente | `config/devices.json` | Permanente | Device info + config |

### Tabla 2: Escenarios de Reconexión

| Escenario | Estado en Memoria | Estado en Disco | Resultado |
|-----------|-------------------|-----------------|-----------|
| Desconexión < 3 min | ✅ Existe | Mismo session_id | **Restaura automáticamente** |
| Desconexión > 3 min (RF_STATE_CACHE_TIMEOUT) | ❌ Expirado | Mismo session_id | **Restaura desde disco** |
| Reinicio servidor | ❌ Limpiado | ❌ session_id cambia | **Conecta limpio** |
| App Android cierra/abre | ✅ UUID persiste | Mismo session_id | **Restaura (mismo UUID)** |

---

## 🔑 Claves de Implementación

### Python (Servidor)

1. **DeviceRegistry** (`audio_server/device_registry.py`):
   - Mantiene registro de dispositivos con UUID como clave
   - Persiste en `config/devices.json`
   - Soporta búsqueda por device_uuid, MAC, IP
   - Restauración por session_id (reinicio resetea)

2. **NativeAudioServer** (`audio_server/native_server.py`):
   - Usa `device_uuid` en lugar de `client_id` temporal
   - Mantiene `persistent_state[device_uuid]` en memoria
   - Fallback a DeviceRegistry si sesión coincide

3. **ChannelManager** (`audio_server/channel_manager.py`):
   - Mapeo `device_uuid → client_id` para búsqueda rápida
   - Persiste configuración en cada `update_client_mix()`
   - Incluye `device_uuid` en clients_info para control web

### Android (Cliente)

1. **NativeAudioStreamActivity**:
   - Genera/recupera UUID persistente: `getDeviceUUID()`
   - Construye handshake JSON con `device_uuid`
   - Pasa UUID a `NativeAudioClient` y `UDPAudioClient`

2. **NativeAudioClient** (TCP/RF):
   - Constructor: `NativeAudioClient(deviceUUID: String?)`
   - Usa deviceUUID como clientId si viene
   - Incluye `device_uuid` en handshake y subscribe

3. **UDPAudioClient**:
   - También soporta `device_uuid` en handshake personalizado

### Web (Frontend)

1. **Control Center** (`frontend/index.html`):
   - Genera UUID en localStorage: `getOrCreateWebDeviceUuid()`
   - Manda en auth al conectar socket.io
   - Controla dispositivos Android por su device_uuid

---

## ✅ Tests Ejecutados

### Python Server Tests (3/3 ✅)

```
✅ TEST 1: Handshake TCP con device_uuid
   - Verifica que el handshake JSON incluye device_uuid
   - Valida la estructura binaria del paquete TCP

✅ TEST 2: Device Registry persiste device_uuid
   - Registra dispositivo por UUID
   - Guarda/recupera configuración
   - Session ID bloquea restauración con sesión diferente

✅ TEST 3: ChannelManager usa device_uuid
   - Suscribe cliente con device_uuid
   - Recupera cliente por device_uuid
   - Incluye device_uuid en clients_info
```

### Android Kotlin Test (Disponible)

```kotlin
fun testNativeAudioClientUUID(context: Context)
   - Genera/recupera UUID en SharedPreferences
   - Crea NativeAudioClient con UUID
   - Verifica que clientId = UUID
   - Compara legacy (sin UUID) con persistente (con UUID)
```

---

## 🎯 Ventajas

✅ **Identidad Única**: Cada dispositivo (Android/Web) tiene UUID único e invariante
✅ **Restauración Automática**: Sin reinicio servidor = restaura canales + mezcla
✅ **Reinicio Limpio**: Reinicio del servidor = estado nuevo (seguridad)
✅ **Control Centralizado**: Web identifica y controla Android por UUID
✅ **Persistencia Disco**: Respaldo si server caído > 3 min
✅ **Sin Collisiones**: UUID es casi único, no hay conflictos por IP/UA

---

## 📝 Configuración Relevante

```python
# config.py
RF_STATE_CACHE_TIMEOUT = 0  # No expirar cache en memoria
RF_MAX_PERSISTENT_STATES = 50  # Máximo 50 dispositivos cached
```

**Nota**: Si quieres que expire después de N segundos, cambia el `0` a ese valor (ej: `180` = 3 min).

---

## 🚀 Próximos Pasos (Opcional)

1. **Sincronización de Ganancia en Tiempo Real**:
   - Web mueve fader → servidor emite evento → Android lo visualiza

2. **Estadísticas por Dispositivo**:
   - Mostrar latencia, paquetes perdidos, reconexiones por device_uuid

3. **Historial de Dispositivos**:
   - Registro de cuándo se conectó/desconectó cada dispositivo

4. **Multi-Android**:
   - Varios Android simultáneos, cada uno con su mezcla independiente

