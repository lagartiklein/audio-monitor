# ✅ Sistema de Persistencia Permanente de Configuración

## 📋 Resumen

Se ha implementado un **sistema de persistencia permanente** que mantiene la configuración de clientes (canales activos, ganancias, panoramas, etc.) incluso después de:
- Reiniciar el servidor
- Desconectar y reconectar clientes
- Cambios en la red o interfaz de audio

## 🔑 Características Principales

### 1. **Almacenamiento Persistente en Disco**
- Ubicación: `config/devices.json`
- Formato: JSON con estructura jerárquica por UUID de dispositivo
- Cada dispositivo tiene su configuración guardada permanentemente

### 2. **Identificación Única de Dispositivos**
```
Web Client:     UUID generado en localStorage (fichatech_web_device_uuid)
Android/iOS:    UUID del dispositivo + app
```

### 3. **Configuración Persistida**
```json
{
  "device_uuid": {
    "channels": [0, 1, 2, 3, 4],
    "gains": { "0": 1.0, "1": 0.8, "2": 1.2 },
    "pans": { "0": 0.0, "1": -0.5, "2": 0.25 },
    "mutes": { "0": false, "1": true },
    "solos": [],
    "pre_listen": null,
    "master_gain": 1.0,
    "custom_name": "Tablet Sala",
    "timestamp": 1672531200000
  }
}
```

## 🔄 Flujo de Persistencia

### Conectar Cliente (Primera Vez)
```
1. Cliente se conecta con device_uuid
2. Servidor busca en device_registry (devices.json)
3. Si existe configuración guardada → Se restaura automáticamente
4. Si no existe → Se crea nuevo registro
5. Cliente recibe configuración en evento 'auto_resubscribed'
```

### Actualizar Configuración
```
1. Usuario cambia canales/ganancias/panoramas en la UI
2. Frontend emite 'update_client_mix' al servidor
3. Servidor actualiza en memoria (channel_manager)
4. ✅ AUTOMÁTICO: Se guarda en device_registry (devices.json)
5. Se emite a todos los clientes el cambio
```

### Reconectar Cliente (Después de Reinicio)
```
1. Servidor reinicia
2. Cliente se reconecta con device_uuid
3. Servidor busca en device_registry
4. ✅ Configuración se restaura PERMANENTEMENTE
5. Cliente recupera canales activos, ganancias, panoramas, etc.
6. Audio vuelve a funcionar con la misma configuración
```

## 📍 Ubicaciones de Almacenamiento

| Componente | Ubicación | Persistencia | Duración |
|-----------|-----------|--------------|----------|
| **Config Permanente** | `config/devices.json` | Disco | Permanente (hasta editar archivo) |
| **Cache en Memoria** | `persistent_state[device_uuid]` | RAM | Hasta reinicio servidor |
| **Web localStorage** | localStorage del navegador | LocalStorage | Hasta limpiar datos navegador |
| **Android SharedPrefs** | Android system storage | Persistente | Hasta desinstalar app |

## 🛠️ Archivos Modificados

### 1. `audio_server/channel_manager.py` (línea ~445)
**Cambio**: Removido restricción de `session_id` en `update_configuration()`
- Antes: Se guardaba config solo si session_id coincidía (no persistía entre reinicios)
- Después: Se guarda config permanentemente sin restricción de sesión

```python
# Antes (NO persistía entre reinicios):
self.device_registry.update_configuration(device_uuid, config, session_id=self.server_session_id)

# Después (SÍ persiste permanentemente):
self.device_registry.update_configuration(device_uuid, config)  # Sin session_id
```

### 2. `audio_server/native_server.py` (línea ~560)
**Cambio**: Mejorado restauración desde device_registry para clientes Android
- Removido restricción de `session_id`
- Ahora restaura configuración permanentemente

```python
# Antes:
disk_state = device_registry.get_configuration(persistent_id, session_id=session_id)

# Después:
disk_state = device_registry.get_configuration(persistent_id)  # Sin session_id
```

### 3. `audio_server/websocket_server.py` (línea ~354)
**Cambio**: Mejorado `handle_subscribe()` para restaurar automáticamente
- Al suscribir cliente web, intenta restaurar config desde device_registry
- Si no hay canales especificados, carga los guardados

```python
# ✅ NUEVO: Si no hay canales, restaurar desde device_registry
if not channels and web_device_uuid:
    saved_config = channel_manager.device_registry.get_configuration(web_device_uuid)
    if saved_config and saved_config.get('channels'):
        channels = saved_config.get('channels', [])
        gains_int = saved_config.get('gains', {})
        pans_int = saved_config.get('pans', {})
```

### 4. `audio_server/device_registry.py`
**Ya implementado**: Métodos para persistencia
- `set_custom_name()`: Guardar nombre personalizado
- `get_configuration()`: Obtener config guardada
- `update_configuration()`: Guardar config
- Auto-guardado en `devices.json`

## ✅ Casos de Uso

### Caso 1: Cliente Web Recarga Página
```
Antes: Se perdía configuración de canales
Después: Se restauran automáticamente los canales guardados
```

### Caso 2: Servidor Reinicia
```
Antes: Clientes pierden configuración
Después: Al conectarse, restauran automáticamente su configuración guardada
```

### Caso 3: Usuario Cambiar Nombre Personalizado
```
Antes: Se guardaba en localStorage (volátil)
Después: Se guarda en device_registry permanentemente
```

### Caso 4: Múltiples Dispositivos Conectados
```
Cada dispositivo tiene su propia configuración guardada por UUID
No hay conflictos entre dispositivos
```

## 🔍 Cómo Verificar Persistencia

### 1. Ver archivo devices.json
```bash
cat config/devices.json
```

### 2. Ver logs del servidor
```
[Device Registry] 💾 Config guardada: device-uuid
[ChannelManager] 💾 Config persistida para device-uuid
[WebSocket] 📂 Configuración restaurada desde device_registry
```

### 3. Debugger del Navegador
```javascript
// Web client
localStorage.getItem('fichatech_web_device_uuid')
```

## 🚀 Mejoras Futuras

1. **Sincronización en Tiempo Real**: Actualizar config en otros dispositivos conectados
2. **Historial de Configuración**: Guardar versiones anteriores
3. **Exportar/Importar**: Compartir configuraciones entre dispositivos
4. **Presets**: Guardar varias configuraciones con nombre

## 📝 Notas Técnicas

- **Thread-safe**: Usa locks para acceso concurrente a device_registry
- **Auto-cleanup**: Limpia dispositivos inactivos cada 7 días
- **Límite de dispositivos**: Máximo 500 dispositivos almacenados
- **Tamaño archivo**: devices.json crece con cada dispositivo nuevo (~1KB por dispositivo)

---

**Última actualización**: 2026-01-03
**Versión**: 2.5.1
