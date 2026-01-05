# TEST GUIDE - Audio Monitor System

## ✅ System Status
- **Web Server:** Listening (port 5000)
- **RF Native Server:** LISTENING on port 5101
- **Audio Devices:** 88 devices detected
- **Project Structure:** OK
- **Dependencies:** All installed (flask, flask_socketio, numpy, sounddevice)

---

## 🧪 TEST 1: Audio del Maestro (Web Streaming)

### Prerequisitos
- Servidor Python corriendo (`main.py`)
- Navegador web abierto

### Pasos
1. **Abrir web UI:** http://localhost:5000
2. **Seleccionar cliente:** Click en "🎧 Monitor Sonidista"
3. **Iniciar streaming:** Click en "▶️ Escuchar"
4. **Verificar:**
   - Audio debe reproducirse en navegador
   - Logs deben mostrar `[WebSocket] Master audio streaming active`
   - Latencia mostrada en UI (ms)

### Resultado Esperado
```
[AudioMixer] ✅ Inicializado: 48000Hz, 2048 samples
[WebSocket] ✅ Audio Mixer conectado
[AudioCapture] 🎛️ AudioMixer conectado
[AudioCapture] 🎧 Cliente maestro: __master_server_client__
```

---

## 🧪 TEST 2: Sincronización Web → Android

### Prerequisitos
- APK Android conectado a RF Server (5101)
- Web UI abierta
- Mismo servidor de audio

### Pasos
1. **En Web UI:** Cambiar ganancia de canal 0
2. **Mover slider** de ganancia (Gain)
3. **Verificar en Android:**
   - Slider del canal se mueve automáticamente
   - Audio cambia en tiempo real
   - Logs muestran `Sync Web→Android`

### Resultado Esperado
```
[NativeServer] 📤 Broadcast channel_update a 1/1 clientes
[NativeAudioClient] 📥 channel_update: CH0 gain=-12.0dB
```

---

## 🧪 TEST 3: Sincronización Android → Web

### Prerequisitos
- APK Android conectado
- Web UI abierta
- Logs visibles en servidor

### Pasos
1. **En Android:** Cambiar Pan de un canal
2. **Deslizar Pan slider**
3. **Verificar en Web:**
   - Slider Pan del canal se mueve
   - UI actualiza sin recargar
   - Logs muestran `param_sync`

### Resultado Esperado
```
[NativeServer] ⚡ param_sync: pan ch2=0.5
[WebSocket] 📡 Param sync broadcast completado
```

---

## 🧪 TEST 4: Validación de Canales

### Prerequisitos
- Servidor configurado con 8 canales

### Pasos
1. **En Android:** Intentar suscribir canales 0-3 (válidos)
2. **Intentar suscribir canales 8-15** (inválidos)
3. **Verificar logs:**
   - Solo canales 0-3 se activan
   - Logs muestran warning de canales inválidos

### Resultado Esperado
```
[ChannelManager] ✅ Canales válidos: {0, 1, 2, 3}
[ChannelManager] ⚠️ Canales inválidos ignorados: {8, 9, 10, 11, ...}
```

---

## 🧪 TEST 5: Persistencia de Configuración

### Prerequisitos
- Android y Web conectados

### Pasos
1. **En Web:** Configurar canales 0-2 activos
2. **Ajustar ganancias** (ej: -6dB, -12dB, -3dB)
3. **Cerrar y reabrir APK Android**
4. **Verificar:**
   - Mismos canales 0-2 activos
   - Mismas ganancias restauradas

### Resultado Esperado
```
[DeviceRegistry] ✅ Configuración restaurada desde disk
[NativeAudioClient] 🔄 Restaurando canales: [0, 1, 2]
```

---

## 📊 Logs Esperados Principales

### Inicio del Servidor
```
[ChannelManager] ✅ Inicializado: 8 canales
[AudioCapture] 🎛️ AudioMixer conectado
[AudioCapture] 🎧 Cliente maestro: __master_server_client__
[AudioMixer] ✅ Inicializado: 48000Hz, 2048 samples
[WebSocket] ✅ Audio Mixer conectado
[MAIN] ✅ AudioMixer conectado y configurado
```

### Conexión de Cliente
```
[NativeServer] 🔌 Cliente nativo conectado: abc123
[NativeServer] ✅ Handshake completado
[NativeServer] 📥 Suscripción confirmada: canales [0, 1, 2]
```

### Sincronización Activa
```
[WebSocket] ✅ Sync Web→Android: gain para abc12345
[NativeServer] 📤 Broadcast channel_update a 1/1 clientes
[NativeServer] ⚡ param_sync: gain ch2=0.8
[WebSocket] 📡 Param sync broadcast completado
```

---

## ❌ Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| Web no carga | Server no corriendo | Verificar terminal con main.py |
| Sin audio en web | AudioMixer no conectado | Revisar logs del servidor |
| Android no conecta | Puerto 5101 cerrado | Verificar firewall |
| Cambios no sincronizan | WebSocket desconectado | Reconectar cliente |
| Canales fuera de rango | Validación falla | Verificar operational_channels |

---

## ✅ Checklist de Completitud

- [x] Web Server corriendo
- [x] RF Server escuchando (5101)
- [x] Audio Devices detectados
- [x] Dependencias instaladas
- [x] Logs muestran inicialización correcta
- [ ] Test 1: Audio maestro reproduciéndose
- [ ] Test 2: Web→Android sync funcionando
- [ ] Test 3: Android→Web sync funcionando
- [ ] Test 4: Validación de canales OK
- [ ] Test 5: Persistencia restaurando config

---

## 🚀 Comandos Útiles

```bash
# Ver logs del servidor
tail -f logs/server.log

# Verificar puerto 5101
netstat -an | findstr "5101"

# Reiniciar servidor
Ctrl+C (en terminal) y .\.venv\Scripts\python main.py

# Limpiar sesiones
rm config/web_sessions.json
```

---

**Fecha**: 2026-01-05
**Versión**: 1.0
**Estado**: Ready for Testing
