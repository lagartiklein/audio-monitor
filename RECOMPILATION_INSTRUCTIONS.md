# 🚀 Instrucciones de Recompilación - Fix Buffer Saturado

## ⚡ Resumen Rápido

Se han hecho 3 cambios para eliminar lag de audio cuando "buffer saturado":

| Archivo | Cambio | Recompilación Requerida |
|---------|--------|--------------------------|
| `config.py` | BLOCKSIZE: 128 → 64 | ❌ NO (solo restart server) |
| `audio_callback.h` | Buffer: 1024 → 2048, drop: 75% → 50% | ✅ SÍ (C++) |
| `NativeAudioClient.kt` | Heartbeat + timing (ya hecho) | ✅ SÍ (Kotlin) |

---

## 📱 PASO 1: Recompilar Android App

### Requisitos:
- Android Studio (versión reciente)
- Kotlin plugin actualizado
- NDK instalado (para compilar C++)
- Device o emulador conectado

### Instrucciones Detalladas:

#### Opción A: Recompilación Limpia (Recomendado)
```
1. Abrir Android Studio
2. Ir a: File → Open → Seleccionar carpeta "kotlin android"
3. Esperar a que Gradle sincronice (puede tomar 2-3 minutos)
4. En Build menu, hacer clic en: "Clean Project"
   - Esperar a que termine
5. Luego: Build → "Make Project"
   - Esto compilará:
     * Código Kotlin (.kt files)
     * Código C++ (CMakeLists.txt)
     * Linkear con Oboe
6. Ver la sección "Build" abajo para mensajes de compilación
7. Esperar a que aparezca: "BUILD SUCCESSFUL"
```

#### Opción B: Build y Run Directo (Más Rápido)
```
1. Conectar dispositivo Android con USB
   - O tener emulador iniciado
2. Android Studio: Run → "Run 'app'" (o presionar Shift+F10)
   - Compilará automáticamente
   - Instalará en device
   - Iniciará la app
```

#### Opción C: Desde Terminal
```bash
cd "c:\audio-monitor\kotlin android"

# Build APK (en release mode, recomendado)
.\gradlew.bat build -x test

# O directamente instalar en device
.\gradlew.bat installRelease

# Build para debug
.\gradlew.bat assembleDebug
```

### ✅ Validar Compilación Exitosa:
- Debe aparecer en Android Studio: "BUILD SUCCESSFUL"
- No debe haber errores en rojo en la ventana "Build"
- Mensajes en amarillo (warnings) son OK

### ⚠️ Si Falla la Compilación:

**Error: "CMake not found"**
```
→ File → Settings → Android SDK → SDK Tools
→ Buscar "CMake"
→ Instalar versión 3.22.1 o superior
```

**Error: "NDK not installed"**
```
→ File → Settings → Android SDK → SDK Tools
→ Buscar "NDK (Side by side)"
→ Instalar versión 25.x o superior
```

**Error: "Kotlin compiler error"**
```
→ File → Settings → Plugins
→ Buscar "Kotlin"
→ Actualizar a versión más reciente
→ Reiniciar Android Studio
```

**Error: "Oboe not found"**
```
→ android/build.gradle o CMakeLists.txt debe incluir:
   - URL de Oboe (GitHub o Maven)
   - Versión compatible (1.8.x o similar)
→ Si faltan dependencias:
   - File → Sync Now
   - Build → Clean Project
   - Build → Rebuild Project
```

---

## 🖥️ PASO 2: Reiniciar Servidor Python

### Requisitos:
- Servidor Python en `c:\audio-monitor` ejecutándose
- Acceso a terminal

### Instrucciones:

#### Si el Servidor está en Una Terminal:
```
1. En la terminal donde está ejecutándose:
   - Presionar: Ctrl + C
   - Esperar a que se detenga completamente
   
2. Reiniciar:
   - python main.py
   
3. Esperar a ver:
   "🟢 SERVIDOR RF MODO RECEPTOR PURO - FIXED"
   "✅ SERVIDOR NATIVO EN 0.0.0.0:5101"
```

#### Si el Servidor está en Background:
```powershell
# En PowerShell, encontrar proceso Python
Get-Process python*

# Detener servidor Python
Stop-Process -Name python -Force

# Esperar 2 segundos
Start-Sleep -Seconds 2

# Reiniciar
cd c:\audio-monitor
python main.py
```

#### En Bash (Git Bash / WSL):
```bash
# Encontrar proceso
ps aux | grep python

# Matar proceso (reemplazar PID)
kill -9 <PID>

# Reiniciar
cd /c/audio-monitor  # WSL: cd /mnt/c/audio-monitor
python main.py
```

### ✅ Validar Servidor Iniciado:
```
Debe aparecer en terminal:
[Información del servidor]
"✅ SERVIDOR NATIVO EN 0.0.0.0:5101"
"BLOCKSIZE = 64"  ← Confirmar que se cargó nuevo valor
```

---

## 📲 PASO 3: Testear en Dispositivo

### Procedimiento:

#### 1. Conectar Android al Server
```
1. Abrir app en Android
2. Ingresar IP: 192.168.1.7 (o la IP de tu server)
3. Puerto: 5101
4. Modo: RF (nativo)
5. Conectar
```

#### 2. Reproducir Audio
```
1. Seleccionar canales de audio
2. Reproducir audio desde el server
3. Mantener conexión activa por 5+ minutos
```

#### 3. Observar en Logcat
```
En Android Studio:
- View → Tool Windows → Logcat
- Filtrar por: "Buffer|saturado|Oboe"

Buscar mensajes:
- "🗑️ Buffer saturado" → Normal si aparece, pero no debería haber lag
- "❌ SIGSEGV" → NO debe aparecer
- "Heartbeat timeout" → NO debe aparecer
- "Magic error" → Máximo 1-2 al iniciar
```

#### 4. Criterios de Éxito
```
✅ Conexión se establece al primer intento
✅ Conexión se mantiene 5+ minutos sin desconectar
✅ Audio reproduce de manera FLUIDA
✅ Si aparece "Buffer saturado", NO hay lag/stutter audible
✅ No hay mensajes de error críticos

❌ Fallos:
- Desconexiones frecuentes
- SIGSEGV crashes
- Audio con cortes/lag cuando dice "Buffer saturado"
- Heartbeat timeout (desconexión después de 6 segundos)
```

---

## 🔍 Troubleshooting Durante Test

### "Buffer saturado" aparece cada 1-2 segundos
```
Problema: Aún hay desajuste de velocidad
Solución:
  1. Reducir más BLOCKSIZE: 64 → 32 en config.py
  2. Aumentar buffer: 2048 → 4096 en audio_callback.h
  3. Reiniciar server y recompilar app
```

### "Desconexión después de 6 segundos"
```
Problema: Heartbeat timeout (conexión perdida)
Verificar:
  1. ¿Server está corriendo? (ver terminal)
  2. ¿Red WiFi estable? (ping 192.168.1.7)
  3. ¿Firewall bloqueando puerto 5101?
     - Windows: Control Panel → Windows Defender Firewall
     - Agregar excepción para puerto 5101
```

### "SIGSEGV crash"
```
Problema: Race condition en socket reads (debería estar fijado)
Verificar:
  1. ¿Recompilaste después del cambio en NativeAudioClient.kt?
  2. Si sigue crashing, reportar logcat completo
```

### "Audio muy lentificado (mayor latencia)"
```
Problema: Buffer target muy alto (128 vs 96 anterior)
Solución:
  1. Reducir TARGET_BUFFER_FRAMES: 128 → 96 en audio_callback.h
  2. Recompilar
  3. Reiniciar
```

---

## 📊 Resumen de Cambios a Aplicar

### ✅ Ya Hecho:
- `config.py`: BLOCKSIZE = 64
- `audio_callback.h`: Buffer sizes updated
- `NativeAudioClient.kt`: Mutex + timing fixes

### ⏳ Requiere Recompilación:
- **Android App** (cambios C++ en audio_callback.h)
- **Android App** (cambios Kotlin en NativeAudioClient.kt)

### ⏳ Requiere Reinicio:
- **Python Server** (nuevo BLOCKSIZE en config.py)

---

## ✨ Próxima Validación

Una vez completados los pasos:

1. **Conexión:** ✅ Debe funcionar (ya validado)
2. **Audio:** 📊 Verificar que lag se eliminó o redujo significativamente
3. **Estabilidad:** 🔒 Mantener conexión 5+ minutos sin problemas

Si todo está bien:
- **DONE** 🎉
- Documentar resultados en TEST_REPORT.md

Si hay issues:
- Recolectar logcat
- Probar next tier de fixes (BLOCKSIZE 32, buffer 4096, etc.)

---

## 🎬 Comandos Quick Reference

### Terminal:
```bash
# Recompile Android
cd "c:\audio-monitor\kotlin android" && gradlew build

# Restart Python Server
cd c:\audio-monitor && python main.py
```

### Android Studio Menu:
```
Build → Clean Project
Build → Make Project
Run → Run 'app'
View → Tool Windows → Logcat
```

---

## 📞 Support

Si hay problemas durante recompilación:
1. **Errores de compilación:** Check Android Studio version + Kotlin plugin
2. **Device not detected:** Check USB cable + USB debugging enabled
3. **App crashes:** Revisar Logcat para stack trace exacto
4. **Connection fails:** Check server IP + firewall rules
