# ✅ Sistema de Persistencia de Estado de Canales

## Descripción
El servidor ahora **guarda y restaura automáticamente** el estado de los canales de TODOS los clientes. Si apagas o reiniciasel servidor, los canales volverán exactamente al estado en que estaban.

## ¿Qué se persiste?

Para cada cliente se guarda:
- **Canales activos** - Qué canales tiene seleccionados
- **Ganancia (Gain)** - El nivel de volumen de cada canal
- **Panorama (Pan)** - La posición estéreo de cada canal
- **Mutes** - Canales silenciados
- **Master Gain** - Ganancia maestra del cliente

## Cómo funciona

### 1. **Guardado automático**
Cada vez que un usuario:
- Mueve un **fader** de ganancia
- Ajusta el **pan**
- Activa/desactiva un **canal**
- **Silencia/activa** (mute) un canal
- Actualiza la **mezcla completa**

→ El estado se guarda automáticamente en `config/channels_state.json`

### 2. **Restauración al reiniciar**
Cuando el servidor reinicia:
1. Carga el archivo `config/channels_state.json`
2. Restaura automáticamente el estado de TODOS los clientes conocidos
3. Los clientes ven sus canales exactamente como los dejaron

### 3. **Restauración para nuevas conexiones**
Cuando un cliente web se conecta sin especificar canales:
1. El servidor busca su estado guardado
2. Restaura automáticamente sus canales, ganancias y pans
3. El cliente ve su configuración anterior sin hacer nada

## Archivos modificados

### `audio_server/device_registry.py`
- ✅ `load_channels_state()` - Carga estado desde disco al iniciar
- ✅ `save_channels_state()` - Guarda estado a disco (llamado automáticamente)
- ✅ `update_channels_state(client_id, state)` - Actualiza y persiste estado
- ✅ `get_channels_state(client_id)` - Obtiene estado guardado

### `audio_server/websocket_server.py`
- ✅ `_restore_client_channels_state()` - Restaura estado de un cliente
- ✅ `_restore_channels_state_on_startup()` - Restaura TODOS los clientes al iniciar
- ✅ `_save_client_config_to_registry()` - Guarda estado cuando cambia
- ✅ Modificados handlers: `update_gain`, `update_pan`, `toggle_mute`, `update_client_mix`
- ✅ Nuevos eventos: `get_saved_channels_state`, `clear_saved_channels_state`

## Eventos WebSocket para administración

### `get_saved_channels_state`
Obtiene el estado guardado de TODOS los clientes:
```javascript
socket.emit('get_saved_channels_state', {}, (data) => {
  console.log('Estados guardados:', data.data);
  console.log('Total clientes:', data.count);
});
```

Respuesta:
```json
{
  "status": "ok",
  "data": {
    "client_id_1": {
      "channels": [0, 1, 2],
      "gains": {"0": 1.0, "1": 0.8},
      "pans": {"0": 0.0, "1": -0.5},
      "mutes": {},
      "master_gain": 1.0,
      "timestamp": 1704528000000
    }
  },
  "count": 1,
  "timestamp": 1704528000000
}
```

### `clear_saved_channels_state`
Limpia el estado guardado (completo o por cliente):
```javascript
// Limpiar TODO
socket.emit('clear_saved_channels_state', {}, (data) => {
  console.log('Estado limpiado:', data.message);
});

// Limpiar un cliente específico
socket.emit('clear_saved_channels_state', { 'client_id': 'web-abc123' }, (data) => {
  console.log('Estado limpiado:', data.message);
});
```

## Archivo de persistencia

El estado se guarda en: `config/channels_state.json`

Formato:
```json
{
  "timestamp": 1704528000,
  "channels_state": {
    "client_id_1": {
      "channels": [0, 1, 2],
      "gains": {"0": 1.0, "1": 0.8},
      "pans": {"0": 0.0, "1": -0.5},
      "mutes": {},
      "master_gain": 1.0,
      "timestamp": 1704528000000
    }
  }
}
```

## Logs del sistema

Al iniciar, verás en la consola:
```
[WebSocket] 🔄 Iniciando restauración de estado de N clientes...
[WebSocket] ✅ Estado restaurado para client-id: X canales, ganancia: {...}, pan: {...}
[WebSocket] ✅ Restauración de estado completada
```

Cuando un cliente guarda cambios:
```
[WebSocket] 💾 Estado de canales guardado para client-id
```

## Ventajas

✅ **Persistencia automática** - Sin configuración manual
✅ **Recuperación completa** - Todos los parámetros se restauran
✅ **Sin impacto en rendimiento** - Se guarda en background
✅ **Compatible con múltiples clientes** - Cada uno tiene su propio estado
✅ **Fácil administración** - Puedes consultar y limpiar manualmente si lo necesitas

## Troubleshooting

Si algo no se restaura:
1. Verifica que `config/channels_state.json` existe
2. Comprueba los logs del servidor para errores
3. Limpia el estado con `clear_saved_channels_state`
4. Los cambios se guardan en tiempo real, sin demora

## Próximas mejoras posibles

- [ ] Exportar/importar configuración de canales
- [ ] Presets guardados por usuario
- [ ] Historial de cambios
- [ ] Sincronización entre dispositivos
