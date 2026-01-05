# 🧪 Pruebas de Persistencia de Estado de Canales

## Cómo probar el nuevo sistema

### Requisito
- Servidor ejecutándose: `python main.py`
- Cliente web conectado en `http://localhost:8080`
- DevTools o herramienta de testing de WebSocket

---

## Test 1: Guardar y restaurar con refresh

### Pasos:
1. **Conectar cliente web** - Abre http://localhost:8080
2. **Configurar canales** 
   - Selecciona canales: [0, 1, 2]
   - Ajusta ganancia del canal 0: 0.8
   - Ajusta pan del canal 1: -0.5
3. **Verifica que se guardó** en `config/channels_state.json`:
   ```bash
   cat config/channels_state.json
   ```
   Debe mostrar tu configuración

4. **Refresh la página web** (F5)
5. **Resultado esperado**: 
   - Canales vuelven a [0, 1, 2]
   - Ganancia del canal 0 = 0.8
   - Pan del canal 1 = -0.5

---

## Test 2: Guardar y restaurar con reinicio del servidor

### Pasos:
1. **Configura canales** en el cliente web (ver Test 1)
2. **Verifica en `config/channels_state.json`**
3. **Detén el servidor** (Ctrl+C en terminal)
4. **Inicia el servidor de nuevo** (espera a que esté listo)
5. **Abre un nuevo cliente web** (sin especificar canales)
6. **Resultado esperado**: 
   - El cliente ve su configuración anterior automáticamente
   - Sin hacer nada, los canales se restauraron

---

## Test 3: Múltiples clientes

### Pasos:
1. **Abre cliente 1** en http://localhost:8080
   - Configura: canales [0, 1], ganancia CH0 = 0.7
2. **Abre cliente 2** en nueva ventana http://localhost:8080
   - Configura: canales [2, 3, 4], ganancia CH2 = 0.9
3. **Verifica en `config/channels_state.json`**
   - Debe tener 2 entradas con configs distintas
4. **Reinicia servidor**
5. **Resultado esperado**:
   - Cliente 1 ve [0, 1] con ganancia 0.7
   - Cliente 2 ve [2, 3, 4] con ganancia 0.9

---

## Test 4: Cambios en tiempo real se guardan

### Pasos:
1. **Conecta cliente web**
2. **En DevTools Console** (F12):
   ```javascript
   // Suscribirse a canales
   socket.emit('subscribe', {
     channels: [0, 1],
     gains: { 0: 1.0, 1: 1.0 },
     pans: {}
   });
   
   // Cambiar ganancia
   socket.emit('update_gain', {
     channel: 0,
     gain: 0.5
   });
   ```
3. **Verifica inmediatamente en `config/channels_state.json`**
4. **Resultado esperado**:
   - El cambio está guardado en menos de 100ms
   - Puedes verlo en el archivo JSON

---

## Test 5: Consultar estado guardado vía API

### En DevTools Console:
```javascript
socket.emit('get_saved_channels_state', {}, (response) => {
  console.log('Estado guardado:', response.data);
  console.log('Total clientes:', response.count);
});
```

Resultado esperado:
```json
{
  "status": "ok",
  "data": {
    "client_id_1": {
      "channels": [0, 1, 2],
      "gains": {"0": 0.8, "1": 1.0, "2": 1.0},
      "pans": {"0": 0.0, "1": -0.5, "2": 0.0},
      "mutes": {},
      "master_gain": 1.0,
      "timestamp": 1704528000000
    }
  },
  "count": 1
}
```

---

## Test 6: Limpiar estado

### En DevTools Console:
```javascript
// Limpiar TODO
socket.emit('clear_saved_channels_state', {}, (response) => {
  console.log(response.message);
});

// Limpiar un cliente específico
socket.emit('clear_saved_channels_state', {
  'client_id': 'web-abc123'
}, (response) => {
  console.log(response.message);
});
```

Resultado esperado:
- `config/channels_state.json` se vacía (o queda sin ese cliente)
- Los nuevos refresh no restauran nada

---

## Logs esperados en la consola

### Al iniciar servidor:
```
[Device Registry] ✅ Estado de canales cargado: N clientes
[WebSocket] 🔄 Iniciando restauración de estado de N clientes...
[WebSocket] ✅ Estado restaurado para client-id: X canales, ganancia: {...}, pan: {...}
[WebSocket] ✅ Restauración de estado completada
```

### Cuando un cliente cambia ganancia:
```
[WebSocket] 💾 Estado de canales guardado para client-id
[WebSocket] ⚡ Gain CH0: 0.50 (client-id) [synced]
```

### Cuando se conecta un cliente:
```
[WebSocket] 🔄 Estado de canales restaurado para client-id: X canales
```

---

## Archivos involucrados

| Archivo | Responsabilidad |
|---------|-----------------|
| `config/channels_state.json` | Almacenamiento persistente del estado |
| `audio_server/device_registry.py` | Cargar/guardar estado |
| `audio_server/websocket_server.py` | Restaurar y guardar en tiempo real |

---

## Estructura de datos guardada

```json
{
  "timestamp": 1704528000,
  "channels_state": {
    "client_id": {
      "channels": [0, 1, 2],           // Canales activos
      "gains": {                        // Ganancias por canal
        "0": 1.0,
        "1": 0.8,
        "2": 0.9
      },
      "pans": {                         // Pan por canal
        "0": 0.0,
        "1": -0.5,
        "2": 0.25
      },
      "mutes": {                        // Mutes por canal
        "0": false,
        "1": false,
        "2": true
      },
      "master_gain": 1.0,               // Ganancia maestra
      "timestamp": 1704528000000        // Timestamp del estado
    }
  }
}
```

---

## Checklist de verificación

- [ ] Test 1: Estado persiste con refresh
- [ ] Test 2: Estado persiste con reinicio de servidor
- [ ] Test 3: Múltiples clientes tienen estados independientes
- [ ] Test 4: Cambios se guardan en tiempo real
- [ ] Test 5: API de consulta funciona
- [ ] Test 6: Limpiar estado funciona
- [ ] Logs muestran guardado/restauración correctamente
- [ ] Archivo `channels_state.json` se crea automáticamente

---

## Troubleshooting

### Problema: El estado no se restaura después del refresh
**Solución**:
1. Verifica que `config/channels_state.json` existe
2. Revisa los logs para errores de carga
3. Prueba limpiar y crear un nuevo estado

### Problema: El servidor no restaura al iniciar
**Solución**:
1. Verifica en los logs de inicio que diga "Restauración de estado"
2. Si no aparece, es posible que el archivo no exista o esté corrupto
3. Verifica permisos de lectura en `config/channels_state.json`

### Problema: Los cambios no se guardan
**Solución**:
1. Verifica que el servidor tiene permisos de escritura en `config/`
2. Espera a que el backend procese el cambio (puede tomar ~100ms)
3. Revisa los logs para ver si dice "Estado de canales guardado"

---

## Performance

- **Guardado**: Asincrónico en background (~100ms)
- **Restauración**: En paralelo con inicio (no bloquea)
- **Consulta**: Inmediata (desde memoria caché)
- **Impact**: Negligible en latencia de audio
