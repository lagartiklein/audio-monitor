# Mejoras de Sincronización Android-Server-Web

## Resumen de Cambios Implementados

Este documento describe las mejoras realizadas para lograr una sincronización correcta entre:
- **Cliente Android nativo** (Kotlin/Oboe)
- **Servidor Python** (native_server.py + websocket_server.py)
- **Aplicación Web** (frontend)

---

## 1. NativeAudioClient.kt - Mejoras Críticas

### 1.1 Singleton Thread-Safe
```kotlin
companion object {
    @Volatile private var instance: NativeAudioClient? = null
    private val instanceLock = Any()
    
    fun getInstance(deviceUUID: String): NativeAudioClient {
        instance?.let { 
            if (it.deviceUUID == deviceUUID) return it 
        }
        return synchronized(instanceLock) {
            // ...
        }
    }
}
```

### 1.2 Heartbeat Keep-Alive (API 36)
- **Intervalo**: 5 segundos
- **Timeout**: 15 segundos sin respuesta = desconexión detectada
- Permite detección rápida de pérdida de conexión

### 1.3 Estado Persistente Completo
```kotlin
private var persistentChannels = emptyList<Int>()
private var persistentGains = emptyMap<Int, Float>()
private var persistentPans = emptyMap<Int, Float>()
private var persistentMutes = emptyMap<Int, Boolean>()
```

### 1.4 Nuevo Callback de Sincronización
```kotlin
var onControlSync: ((ControlUpdate) -> Unit)? = null

data class ControlUpdate(
    val source: String,
    val channel: Int,
    val gain: Float?,
    val pan: Float?,
    val active: Boolean?,
    val mute: Boolean?
)
```

---

## 2. ChannelView.kt - Sincronización Bidireccional

### 2.1 Flag para Evitar Loops
```kotlin
private var isUpdatingFromServer = false
```

### 2.2 Métodos con Parámetro `fromServer`
```kotlin
fun setGainDb(gainDb: Float, fromServer: Boolean = false)
fun setPanValue(pan: Float, fromServer: Boolean = false)
fun activateChannel(active: Boolean, fromServer: Boolean = false)
```

### 2.3 Actualización desde Servidor
```kotlin
fun updateFromServerState(active: Boolean, gainDb: Float?, pan: Float?) {
    isUpdatingFromServer = true
    // actualizar UI sin disparar callbacks
    isUpdatingFromServer = false
}
```

---

## 3. NativeAudioStreamActivity.kt - Manejo de Sincronización

### 3.1 Nuevo Handler de Control Sync
```kotlin
private fun handleControlSync(update: NativeAudioClient.ControlUpdate) {
    runOnUiThread {
        val view = channelViews[update.channel] ?: return@runOnUiThread
        
        update.active?.let { view.activateChannel(it, fromServer = true) }
        update.gain?.let { view.setGainDb(it, fromServer = true) }
        update.pan?.let { view.setPanValue(it, fromServer = true) }
    }
}
```

### 3.2 MixState Aplicado con fromServer=true
```kotlin
private fun applyMixState(mixState: MixState) {
    runOnUiThread {
        channelViews.forEach { (ch, view) ->
            view.activateChannel(isActive, fromServer = true)
            view.setGainDb(gainDb, fromServer = true)
            view.setPanValue(pan, fromServer = true)
        }
    }
}
```

---

## 4. native_server.py - Propagación de Controles

### 4.1 Nueva Función broadcast_control_update
```python
def broadcast_control_update(self, channel, source, gain=None, pan=None, active=None, mute=None):
    """Propagar cambio de control a todos los clientes nativos"""
    control_data = {
        'type': 'control_update',
        'source': source,
        'channel': channel,
        # ... gain, pan, active, mute si están definidos
    }
    packet = NativeAndroidProtocol.create_control_packet('control_update', control_data, True)
    
    with self.client_lock:
        for client in self.clients.values():
            client.send_bytes_direct(packet)
```

---

## 5. AndroidManifest.xml - API 36

### 5.1 Permisos Actualizados
```xml
<!-- Audio de baja latencia (opcionales) -->
<uses-feature android:name="android.hardware.audio.low_latency" android:required="false" />
<uses-feature android:name="android.hardware.audio.pro" android:required="false" />

<!-- API 36: Servicios especiales -->
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />
```

### 5.2 Configuración de Application
```xml
<application
    android:hardwareAccelerated="true"
    android:usesCleartextTraffic="true"
    android:enableOnBackInvokedCallback="true"
    tools:targetApi="36">
```

---

## 6. Flujo de Sincronización

### 6.1 Cambio desde Android → Web
1. Usuario mueve slider en Android
2. `ChannelView.onGainDbChanged` dispara con debounce
3. `NativeAudioClient.sendMixUpdate()` envía al servidor
4. Servidor actualiza `channel_manager`
5. Servidor notifica web via `socketio.emit('mix_updated')`
6. Web actualiza UI

### 6.2 Cambio desde Web → Android
1. Usuario mueve slider en Web
2. Web envía `update_client_mix` via SocketIO
3. Servidor actualiza `channel_manager`
4. Servidor llama `native_server.push_mix_state_to_client()`
5. Android recibe `mix_state` y aplica con `fromServer=true`
6. UI actualizada sin disparar callbacks

### 6.3 Reconexión
1. Android pierde conexión
2. Heartbeat timeout (15s) dispara `handleConnectionLost()`
3. Auto-reconexión con backoff exponencial
4. Al reconectar, envía `subscribe` con estado completo
5. Servidor restaura de `device_registry`
6. Servidor envía `mix_state` actualizado
7. Android aplica estado y UI sincronizada

---

## 7. Buenas Prácticas Implementadas

1. **Thread-Safety**: AtomicBoolean/AtomicLong para estados compartidos
2. **Debounce**: Evita spam de red en cambios rápidos de sliders
3. **Backoff Exponencial**: Reconexión progresiva (1s → 8s máx)
4. **Persistencia**: device_registry guarda estado permanente
5. **Detección de Zombies**: Servidor elimina clientes inactivos
6. **Edge-to-Edge**: Compatible con API 36 y pantallas con notch

---

## 8. Archivos Modificados

| Archivo | Descripción |
|---------|-------------|
| `NativeAudioClient.kt` | Nuevo cliente v3 con heartbeat y estado completo |
| `ChannelView.kt` | Sincronización bidireccional con fromServer |
| `NativeAudioStreamActivity.kt` | Handler de control sync |
| `AndroidManifest.xml` | Permisos API 36 |
| `native_server.py` | broadcast_control_update |
| `channel_manager.py` | Persistencia mejorada |

---

## 9. Testing Recomendado

1. **Conexión inicial**: Verificar que canales se suscriben correctamente
2. **Cambio desde Web**: Mover slider en web, verificar que Android actualiza
3. **Cambio desde Android**: Mover slider en Android, verificar que Web actualiza
4. **Reconexión**: Desconectar WiFi, reconectar, verificar estado restaurado
5. **Multicliente**: Conectar 2+ dispositivos, verificar sincronización
6. **Latencia**: Medir tiempo de propagación de cambios (target: <100ms)
