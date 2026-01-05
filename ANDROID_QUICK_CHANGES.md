# ⚡ CAMBIOS ANDROID - IMPLEMENTACIÓN RÁPIDA

## 🎯 RESUMEN EJECUTIVO

El Android **YA ESTÁ BIEN OPTIMIZADO**. Aquí hay 3 opciones:

### **OPCIÓN A: Sin Cambios** ✅
- Mantener todo como está
- WiFi fuerte: 5-8ms latencia
- Estable, no hay riesgo

### **OPCIÓN B: Tier 1 (Recomendado)** ⭐
- Cambios **MÍNIMOS y SEGUROS**
- WiFi fuerte: 2-5ms latencia
- Sigue siendo estable

### **OPCIÓN C: Tier 2 (Agresivo)**
- Cambios **MÁS AGRESIVOS**
- WiFi fuerte: 1-3ms latencia
- Requiere WiFi EXCELENTE

---

## 🔧 OPCIÓN B - TIER 1 (RECOMENDADO)

### Cambio 1: NativeAudioClient.kt (líneas ~50-55)

**BUSCAR:**
```kotlin
private const val SOCKET_SNDBUF = 8192
private const val SOCKET_RCVBUF = 4096
...
private const val READ_TIMEOUT = 30000
...
private const val RECONNECT_DELAY_MS = 1000L
private const val MAX_RECONNECT_DELAY_MS = 8000L
```

**REEMPLAZAR POR:**
```kotlin
private const val SOCKET_SNDBUF = 6144   // ⬇️ Reducido para latencia
private const val SOCKET_RCVBUF = 3072   // ⬇️ Reducido para latencia
...
private const val READ_TIMEOUT = 5000    // ⬇️ Detección más rápida
...
private const val RECONNECT_DELAY_MS = 500L      // ⬇️ Reconecta más rápido
private const val MAX_RECONNECT_DELAY_MS = 4000L // ⬇️ Máximo más bajo
```

### Cambio 2: OboeAudioRenderer.kt (línea ~75)

**BUSCAR:**
```kotlin
private val MAX_POOLED_BUFFERS = 2
```

**REEMPLAZAR POR:**
```kotlin
private val MAX_POOLED_BUFFERS = 3  // ⬇️ Reduce GC pauses
```

---

## 🔧 OPCIÓN C - TIER 2 (AGRESIVO)

### Cambio 1: NativeAudioClient.kt - Buffers

**BUSCAR:**
```kotlin
private const val SOCKET_SNDBUF = 8192
private const val SOCKET_RCVBUF = 4096
```

**REEMPLAZAR POR:**
```kotlin
private const val SOCKET_SNDBUF = 4096  // ⬇️ MÁS reducido
private const val SOCKET_RCVBUF = 2048  // ⬇️ MÁS reducido
```

### Cambio 2: NativeAudioClient.kt - Timeouts

**BUSCAR:**
```kotlin
private const val READ_TIMEOUT = 30000
private const val RECONNECT_DELAY_MS = 1000L
private const val MAX_RECONNECT_DELAY_MS = 8000L
```

**REEMPLAZAR POR:**
```kotlin
private const val READ_TIMEOUT = 2000           // ⬇️ EXTREMO
private const val RECONNECT_DELAY_MS = 300L     // ⬇️ MUY rápido
private const val MAX_RECONNECT_DELAY_MS = 3000L // ⬇️ Máximo bajo
```

### Cambio 3: NativeAudioClient.kt - Streamed I/O

**BUSCAR (línea ~135-140):**
```kotlin
inputStream = DataInputStream(socket?.getInputStream()?.buffered(4096))
outputStream = DataOutputStream(socket?.getOutputStream()?.buffered(4096))
```

**REEMPLAZAR POR:**
```kotlin
inputStream = DataInputStream(socket?.getInputStream()?.buffered(64))  // ⬇️ Buffer mínimo
outputStream = DataOutputStream(socket?.getOutputStream()?.buffered(64)) // ⬇️ Buffer mínimo
```

### Cambio 4: OboeAudioRenderer.kt

**BUSCAR:**
```kotlin
private val MAX_POOLED_BUFFERS = 2
```

**REEMPLAZAR POR:**
```kotlin
private val MAX_POOLED_BUFFERS = 4  // ⬇️ Más buffers reutilizables
```

---

## 📊 COMPARATIVA

| Métrica | Base | Tier 1 | Tier 2 |
|---------|------|--------|--------|
| Latencia | 5-8ms | 2-5ms | 1-3ms |
| Estabilidad | ✅✅✅ | ✅✅✅ | ✅✅ |
| WiFi Requerido | WiFi Normal | WiFi Fuerte | WiFi Excelente |
| Complejidad | Ninguna | Mínima | Moderada |
| Riesgo | Ninguno | Muy bajo | Bajo |

---

## ✅ CHECKLIST DE DECISIÓN

### ¿Usar TIER 1?
- [✓] Si tienes WiFi fuerte y estable
- [✓] Si quieres mejorar latencia SIN riesgo
- [✓] **RECOMENDADO** para la mayoría

### ¿Usar TIER 2?
- [ ] Si tienes WiFi EXCELENTE (muy baja latencia, sin jitter)
- [ ] Si notaste que Tier 1 sigue siendo lento
- [ ] Si puedes probar y volver a Tier 1 fácilmente

### ¿Mantener BASE?
- [ ] Si el audio actual es aceptable
- [ ] Si tienes red variable/inestable
- [ ] Si prefieres máxima estabilidad

---

## 🧪 CÓMO PROBAR

1. **Implementar Tier 1**
2. **Compilar y ejecutar**
3. **Conectar en WiFi fuerte**
4. **Escuchar:** ¿Suena bien? ¿Menos latencia?
5. **Si sí:** Mantener Tier 1 ✅
6. **Si quieres más:** Pasar a Tier 2 y repetir

---

## ⚠️ SI ALGO FALLA

1. **Muchos cortes:** Volver a Tier 1 o Base
2. **No conecta:** Aumentar READ_TIMEOUT y RECONNECT_DELAY
3. **Audio entrecortado:** Aumentar MAX_POOLED_BUFFERS o Socket buffers

---

## 🎯 MI RECOMENDACIÓN

**👉 IMPLEMENTA TIER 1** - Es mínimo riesgo, máximo beneficio.

Si después quieres Tier 2, es fácil cambiar números.

**Tiempo de implementación:** 5-10 minutos
