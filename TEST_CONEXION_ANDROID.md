# 🧪 GUÍA DE TEST: Verificar Fix de Conexión Android

## 📋 Pre-requisitos

- ✅ Servidor Python corriendo en `localhost:5101` (o IP de red)
- ✅ Dispositivo Android con app compilada
- ✅ WiFi conectada y estable (mínimo 5 Mbps)
- ✅ Logcat abierto para ver outputs en tiempo real

---

## 🚀 TEST 1: Conexión Normal (5 minutos)

### Paso 1: Limpiar logs
```bash
adb logcat -c
```

### Paso 2: Abrir app Android
```bash
adb shell am start -n com.cepalabsfree.fichatech/.MainActivity
```

### Paso 3: Iniciar conexión
- En la app, ingresa IP del servidor (ej: `192.168.1.100`)
- Puerto: `5101`
- Presiona "Conectar"

### Paso 4: Verificar logs
```bash
adb logcat | grep "NativeAudioClient"
```

**Buscar:**
```
✅ Conectado RF (ID: xxxxxxxx)  <- Debe aparecer en INTENTO 1
```

**❌ Problema si ves:**
```
🔄 Reconexión #1 (delay: 1000ms)
🔄 Reconexión #2 (delay: 1500ms)
🔄 Reconexión #3 (delay: 2250ms)
```

**✅ Correcto si ves:**
```
✅ Conectado RF (ID: xxxxxxxx)
```

---

## 🌐 TEST 2: Desconexión Intencional (3 minutos)

### Paso 1: Con app conectada
```bash
adb logcat -c
adb logcat | grep -E "Conectado|BUSCANDO|desconect|reconect"
```

### Paso 2: Desconectar WiFi
- En el dispositivo Android, apaga WiFi (Settings → WiFi → Off)

### Paso 3: Verificar búsqueda de señal
**Debes ver:**
```
📡 Señal RF perdida: Socket error
📡 BUSCANDO SEÑAL...
🔄 Reconexión #1 (delay: 1000ms)
```

### Paso 4: Reconectar WiFi
- En el dispositivo Android, enciende WiFi (Settings → WiFi → On)

### Paso 5: Verificar reconexión
**Debes ver (en < 5 segundos):**
```
✅ Reconexión exitosa (#1)
```

**Métrica:** Tiempo desde apagar WiFi hasta "✅ Reconexión exitosa"
- ✅ **< 10 segundos** = CORRECTO
- ⚠️ **10-20 segundos** = ACEPTABLE
- ❌ **> 20 segundos** = PROBLEMA

---

## 📡 TEST 3: WiFi Ruidoso - Simulación (5 minutos)

### Pre-requisito
- Estar en red **2.4GHz** congestionada (no 5GHz)
- Varias apps usando WiFi

### Paso 1: Conectar en ambiente ruidoso
```bash
adb logcat -c
# Conectar normalmente
# Esperar 30 segundos
```

### Paso 2: Monitorear errores
```bash
adb logcat | grep "Magic"
```

**Buscar patrones:**

✅ **CORRECTO:**
```
⚠️ Magic error #1/5
⚠️ Magic error #2/5
⚠️ Magic error #3/5
(conexión se mantiene)
(resincroniza)
```

❌ **PROBLEMA:**
```
⚠️ Magic error #1/5
⚠️ Magic error #2/5
⚠️ Magic error #3/5
❌ Protocolo inválido (3 errores)
📡 BUSCANDO SEÑAL...
```

### Paso 3: Duración de conexión
- Mantener conectado por 2 minutos
- No debe desconectar por WiFi noise
- ✅ Si se mantiene conectado = CORRECTO

---

## ⚡ TEST 4: Reconexión Rápida (2 minutos)

### Paso 1: Con app conectada
```bash
adb logcat -c
```

### Paso 2: Cerrar app completamente
```bash
adb shell am force-stop com.cepalabsfree.fichatech
```

### Paso 3: Abrir app nuevamente
```bash
adb shell am start -n com.cepalabsfree.fichatech/.MainActivity
```

### Paso 4: Presionar Conectar nuevamente
- Verificar que reconecta rápido

**Debes ver:**
```
✅ Conectado RF (ID: xxxxxxxx)  <- En < 1 segundo
```

**Métrica:** Tiempo desde presionar botón hasta "✅ Conectado"
- ✅ **< 1 segundo** = EXCELENTE
- ⚠️ **1-2 segundos** = ACEPTABLE
- ❌ **> 2 segundos** = REVISAR

---

## 📊 TEST 5: Múltiples Reconexiones (5 minutos)

### Paso 1: Setup
```bash
adb logcat -c
# Conectar normalmente
adb logcat | grep -E "Reconexión|✅ Conectado|BUSCANDO"
```

### Paso 2: Desconectar/Conectar WiFi 5 veces
1. Apagar WiFi
2. Esperar 2 segundos
3. Encender WiFi
4. Esperar conexión
5. Repetir

### Paso 3: Verificar estabilidad
**Debes ver en cada ciclo:**
```
📡 BUSCANDO SEÑAL...
✅ Reconexión exitosa (#N)
```

**Métricas:**
- ✅ Todos los ciclos reconectan exitosamente
- ✅ Tiempo promedio < 10 segundos
- ✅ Sin errores no esperados en servidor

---

## 🔍 TEST 6: Logs del Servidor (2 minutos)

### Verificar servidor
```bash
# En Python
python main.py
```

**Buscar en logs:**

✅ **CORRECTO:**
```
[RF-SERVER] INFO - ✅ Cliente RF: temp_192.168... (192.168.x.x)
[RF-SERVER] INFO - 🤝 XXXXXXXX - HANDSHAKE: reconnection=False, auto_reconnect=True
[RF-SERVER] INFO - ✅ ID actualizado: temp_... → device-uuid
[RF-SERVER] INFO - 📡 Canales restaurados: 8 canales
```

❌ **PROBLEMA si ves:**
```
[RF-SERVER] WARNING - ⚠️ Demasiados errores
[RF-SERVER] ERROR - ❌ Read loop: [error details]
[RF-SERVER] WARNING - Socket XXXXXXXX cerrado
```

---

## 📋 TABLA DE CHEQUEO FINAL

| Test | Métrica | Meta | Resultado | ✅/❌ |
|------|---------|------|-----------|-------|
| 1 | Intentos para conectar | 1 intento | __/1 | ☐ |
| 2 | Tiempo de reconexión | < 10s | __s | ☐ |
| 3 | Estabilidad en ruido | Sin desconexión | __/5min | ☐ |
| 4 | Reconexión rápida | < 1s | __s | ☐ |
| 5 | Múltiples ciclos | 5/5 exitosos | __/5 | ☐ |
| 6 | Logs servidor | Sin errores | __errors | ☐ |

---

## 🆘 TROUBLESHOOTING

### Problema: Sigue necesitando 3 intentos
**Causas posibles:**
- [ ] Cambios no se guardaron correctamente
- [ ] App no fue recompilada
- [ ] Servidor no se reinició

**Solución:**
```bash
# Verificar cambios
git diff audio_server/native_server.py | head -20

# Recompilar y reiniciar servidor
python main.py

# Limpiar logcat y reintentar
adb logcat -c
```

### Problema: Múltiples "Magic error"
**Causas posibles:**
- WiFi muy ruidosa (normal)
- Servidor retrasado
- Cable USB interferencia

**Solución:**
- [ ] Cambiar a WiFi 5GHz si es posible
- [ ] Acercar dispositivo al router
- [ ] Probar sin cable USB

### Problema: Desconexión después de conectar
**Causas posibles:**
- Socket no se configuró correctamente
- Thread de envío falla
- Problema de red

**Solución:**
```bash
# Verificar socket en native_server.py línea 45-50
# Debe estar: setblocking(True) + settimeout(3.0)

# Reiniciar servidor en verbose mode
DEBUG=True python main.py
```

---

## 📞 REPORTE DE RESULTADOS

Si algo falla, recopila:

```bash
# Logs del cliente
adb logcat > client_logs.txt

# Logs del servidor (primera línea de inicio)
python main.py > server_logs.txt 2>&1

# Información del dispositivo
adb shell getprop | grep -E "model|version|device"
```

Incluir estos archivos en reporte de bug.

---

## ✅ CRITERIO DE ÉXITO

**Test EXITOSO si:**
- ✅ Conecta en 1 intento
- ✅ Mantiene conexión en WiFi ruidoso
- ✅ Reconecta en < 10 segundos tras desconexión
- ✅ Sin errores críticos en logs

**Test FALLIDO si:**
- ❌ Necesita > 2 intentos
- ❌ Se desconecta por noise WiFi
- ❌ Tarda > 15 segundos en reconectar
- ❌ Errores de socket en servidor

---

**Estado:** 🧪 **LISTO PARA EJECUTAR**

Ejecuta estos tests antes de deployment. Reporte de éxito/fallo será indicativo si el fix funcionó correctamente.
