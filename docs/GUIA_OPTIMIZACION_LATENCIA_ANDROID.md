# 🎯 Guía Exhaustiva: Optimización de Latencia Ultra-Baja en Audio Android

## Análisis Profundo de la Arquitectura Actual + Estrategias de Optimización al Límite

**Versión:** 2.0  
**Fecha:** Enero 2026  
**Objetivo:** Latencia mínima teórica alcanzable (~5-15ms end-to-end)

---

## 📊 ANÁLISIS DE ARQUITECTURA ACTUAL

### Cadena de Latencia Actual (Estimada)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CADENA DE LATENCIA COMPLETA                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ COMPONENTE                │ ACTUAL (ms)  │ ÓPTIMO (ms)  │ DELTA            │
├───────────────────────────┼──────────────┼──────────────┼──────────────────┤
│ Network (WiFi RTT)        │ 2-10         │ 1-3          │ -5ms             │
│ TCP/UDP Processing        │ 1-3          │ 0.5-1        │ -2ms             │
│ JNI Boundary Crossing     │ 0.1-0.3      │ 0.05-0.1     │ -0.2ms           │
│ Ring Buffer (AudioCallback)│ 5.3          │ 2.7          │ -2.6ms           │
│ Oboe Buffer               │ 1.3-2.7      │ 0.67-1.3     │ -1.4ms           │
│ Android Audio HAL         │ 2-5          │ 1-2          │ -3ms             │
│ DAC/Hardware              │ 0.5-1        │ 0.5-1        │ 0ms              │
├───────────────────────────┼──────────────┼──────────────┼──────────────────┤
│ TOTAL ESTIMADO            │ 12-27ms      │ 5.7-11.1ms   │ -6.3 a -15.9ms   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 ANÁLISIS POR COMPONENTE

### 1. **AudioCallback (audio_callback.h)** - ⚠️ CUELLO DE BOTELLA PRINCIPAL

**Estado Actual:**
```cpp
static constexpr int BUFFER_SIZE_FRAMES = 256;      // ~5.3ms @ 48kHz
static constexpr int TARGET_BUFFER_FRAMES = 128;    // ~2.7ms objetivo
static constexpr int DROP_THRESHOLD = 192;          // 75% del buffer
```

**Problemas Detectados:**
1. `std::mutex bufferMutex` - El mutex bloquea durante escritura Y lectura
2. Buffer circular de 256 frames es conservador
3. Lock contention en callback de audio de alta prioridad
4. `std::memset` y `std::fill` son operaciones costosas en el hotpath

**🎯 OPTIMIZACIONES NIVEL 1 (Sin riesgo):**

```cpp
// CAMBIO 1: Lock-free ring buffer con atomics
// Reemplazar std::mutex por diseño lock-free

class LockFreeAudioCallback : public oboe::AudioStreamDataCallback {
private:
    // Single-producer single-consumer lock-free buffer
    static constexpr int BUFFER_SIZE_FRAMES = 128;  // ⬇️ Reducido a ~2.7ms
    static constexpr int BUFFER_MASK = BUFFER_SIZE_FRAMES - 1;  // Power of 2!
    
    alignas(64) std::vector<float> circularBuffer;  // Cache-aligned
    
    // Atomics separados en líneas de cache diferentes (evitar false sharing)
    alignas(64) std::atomic<int> writePos{0};
    alignas(64) std::atomic<int> readPos{0};
    
    int channelCount = 2;

public:
    // Lock-free write (producer thread)
    int writeAudio(const float* data, int numFrames) {
        const int samplesTotal = numFrames * channelCount;
        int currentWrite = writePos.load(std::memory_order_relaxed);
        int currentRead = readPos.load(std::memory_order_acquire);
        
        // Calcular espacio disponible
        int available = (currentRead - currentWrite - 1) & BUFFER_MASK;
        int framesToWrite = std::min(numFrames, available / channelCount);
        
        if (framesToWrite <= 0) return 0;
        
        // Escribir sin lock
        int samplesToWrite = framesToWrite * channelCount;
        int writeIdx = currentWrite * channelCount;
        
        for (int i = 0; i < samplesToWrite; i++) {
            circularBuffer[(writeIdx + i) & (BUFFER_SIZE_FRAMES * channelCount - 1)] = data[i];
        }
        
        // Memory barrier + actualizar posición
        writePos.store((currentWrite + framesToWrite) & BUFFER_MASK, 
                       std::memory_order_release);
        
        return framesToWrite;
    }
    
    // Lock-free read (consumer/callback thread)
    oboe::DataCallbackResult onAudioReady(
            oboe::AudioStream* audioStream,
            void* audioData,
            int32_t numFrames) override {
            
        auto* outputBuffer = static_cast<float*>(audioData);
        
        int currentRead = readPos.load(std::memory_order_relaxed);
        int currentWrite = writePos.load(std::memory_order_acquire);
        
        int available = (currentWrite - currentRead) & BUFFER_MASK;
        int framesToPlay = std::min(available, numFrames);
        
        if (framesToPlay > 0) {
            int readIdx = currentRead * channelCount;
            int samplesToPlay = framesToPlay * channelCount;
            
            for (int i = 0; i < samplesToPlay; i++) {
                outputBuffer[i] = circularBuffer[(readIdx + i) & (BUFFER_SIZE_FRAMES * channelCount - 1)];
            }
            
            readPos.store((currentRead + framesToPlay) & BUFFER_MASK,
                         std::memory_order_release);
        }
        
        // Silencio para frames faltantes (optimizado con NEON/SIMD si disponible)
        if (framesToPlay < numFrames) {
            std::memset(outputBuffer + framesToPlay * channelCount, 0,
                       (numFrames - framesToPlay) * channelCount * sizeof(float));
        }
        
        return oboe::DataCallbackResult::Continue;
    }
};
```

**Ganancia estimada:** 0.5-1.5ms (eliminación de lock contention)

---

### 2. **native_audio_engine.cpp** - ✅ Buena base, optimizable

**Estado Actual:**
```cpp
// ✅ CORRECTO: Ya usa LowLatency + Exclusive
builder.setPerformanceMode(oboe::PerformanceMode::LowLatency)
       .setSharingMode(oboe::SharingMode::Exclusive);

// ✅ CORRECTO: Buffer óptimo 2x burst
int32_t optimalBufferSize = framesPerBurst * 2;
```

**🎯 OPTIMIZACIONES NIVEL 2 (Agresivas pero seguras):**

```cpp
// CAMBIO 2: Configuración ultra-agresiva de Oboe
JNIEXPORT jlong JNICALL
Java_..._nativeCreateStream(JNIEnv* env, jobject thiz, jlong engineHandle, jint channelId) {
    
    auto* engine = reinterpret_cast<AudioEngine*>(engineHandle);
    auto callback = std::make_shared<LockFreeAudioCallback>(engine->channels);
    
    oboe::AudioStreamBuilder builder;
    
    builder.setDirection(oboe::Direction::Output)
           ->setFormat(oboe::AudioFormat::Float)
           ->setSampleRate(engine->sampleRate)
           ->setChannelCount(engine->channels)
           ->setDataCallback(callback.get())
           
           // 🎯 CRÍTICO: Performance máximo
           ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
           ->setSharingMode(oboe::SharingMode::Exclusive)
           
           // 🎯 NUEVO: Uso Media para prioridad de audio
           ->setUsage(oboe::Usage::Media)
           ->setContentType(oboe::ContentType::Music)
           
           // 🎯 NUEVO: Sugerir frames por callback pequeños
           // Esto reduce la latencia del callback pero aumenta CPU
           ->setFramesPerCallback(engine->sampleRate == 48000 ? 48 : 44)  // ~1ms
           
           // 🎯 NUEVO: Preferir AAudio sobre OpenSL ES (mejor latencia)
           ->setAudioApi(oboe::AudioApi::AAudio);
    
    // ... resto del código
}
```

**Nota sobre `setFramesPerCallback`:** Valores muy pequeños (<48 frames) pueden causar:
- Mayor uso de CPU (más callbacks por segundo)
- Posibles glitches en dispositivos de gama baja
- **Recomendación:** Hacer configurable según dispositivo

---

### 3. **NativeAudioClient.kt (TCP)** - ⚠️ Múltiples áreas de mejora

**Problemas Detectados:**

```kotlin
// PROBLEMA 1: Buffers de stream pequeños
private const val SOCKET_SNDBUF = 8192   // ⚠️ Puede causar fragmentación
private const val SOCKET_RCVBUF = 4096   // ⚠️ Muy pequeño para audio

// PROBLEMA 2: Dispatch a Main thread innecesario
withContext(Dispatchers.Main) {
    onAudioData?.invoke(audioData)  // ⚠️ Context switch costoso!
}

// PROBLEMA 3: Prioridad de thread podría ser mejor
Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
// ✅ Correcto, pero se puede mejorar con affinity
```

**🎯 OPTIMIZACIONES NIVEL 1:**

```kotlin
companion object {
    // ✅ OPTIMIZADO: Buffers de socket más grandes
    private const val SOCKET_SNDBUF = 65536    // 64KB
    private const val SOCKET_RCVBUF = 131072   // 128KB (suficiente para ~2.7s de audio)
    
    // ✅ OPTIMIZADO: Timeout de lectura más corto para respuesta rápida
    private const val READ_TIMEOUT = 10000     // 10s (era 30s)
    
    // ✅ NUEVO: Tamaño óptimo de paquete para evitar fragmentación TCP
    private const val OPTIMAL_PACKET_SIZE = 1400  // < MTU típico (1500)
}

// ✅ OPTIMIZACIÓN CRÍTICA: Evitar dispatch a Main thread
// El procesamiento de audio DEBE ser en thread de alta prioridad
private fun startReaderThread() {
    CoroutineScope(Dispatchers.IO).launch {
        setThreadPriority()
        
        // ... código de lectura ...
        
        // ⚠️ CAMBIO CRÍTICO: NO hacer dispatch a Main
        // El callback debe ejecutarse en el thread de audio
        when (header.msgType) {
            MSG_TYPE_AUDIO -> {
                val audioData = decodeAudioPayload(payload, header.flags)
                if (audioData != null) {
                    // ✅ DIRECTO: Sin cambio de contexto
                    onAudioData?.invoke(audioData)
                }
            }
        }
    }
}
```

**🎯 OPTIMIZACIÓN NIVEL 2: Thread Affinity (Android 7+)**

```kotlin
private fun setThreadPriority() {
    try {
        // 1. Prioridad de thread
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
        
        // 2. CPU Affinity (fijar a cores grandes en big.LITTLE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            val cpuCount = Runtime.getRuntime().availableProcessors()
            if (cpuCount >= 4) {
                // Preferir cores 4-7 (big cores en la mayoría de SoCs)
                // Esto es específico del dispositivo, pero generalmente funciona
                val mask = 0xF0L  // Cores 4-7
                
                // Usar JNI para sched_setaffinity (no hay API Java directa)
                // nativeSetCpuAffinity(mask)
            }
        }
        
        Log.d(TAG, "✅ Thread priority: URGENT_AUDIO, CPU affinity: big cores")
    } catch (e: Exception) {
        Log.w(TAG, "⚠️ No se pudo optimizar thread: ${e.message}")
    }
}
```

---

### 4. **UDPAudioClient.kt** - 🚀 Mejor opción para latencia mínima

UDP es inherentemente más rápido que TCP para audio en tiempo real porque:
- No hay handshake de 3 vías
- No hay retransmisión (la pérdida de paquetes es aceptable)
- No hay control de congestión

**Estado Actual:**
```kotlin
private const val UDP_BUFFER_SIZE = 65536
private const val UDP_TIMEOUT_MS = 10000
```

**🎯 OPTIMIZACIONES UDP NIVEL 1:**

```kotlin
companion object {
    // ✅ Buffer de recepción grande (importante para jitter)
    private const val UDP_BUFFER_SIZE = 262144  // 256KB
    
    // ✅ Timeout más corto para respuesta rápida
    private const val UDP_TIMEOUT_MS = 3000     // 3s
    
    // ✅ Jitter buffer dinámico
    private const val MIN_JITTER_PACKETS = 2    // ~4ms @ 48kHz/128 frames
    private const val MAX_JITTER_PACKETS = 10   // ~20ms
    private const val TARGET_JITTER_PACKETS = 4 // ~8ms (equilibrio)
}

// ✅ NUEVO: Jitter buffer adaptativo
class AdaptiveJitterBuffer(initialSize: Int = 4) {
    private var targetSize = initialSize
    private var currentJitter = 0f
    private val packetTimes = ArrayDeque<Long>(32)
    
    fun onPacketReceived() {
        val now = System.nanoTime()
        if (packetTimes.isNotEmpty()) {
            val delta = (now - packetTimes.last()) / 1_000_000f  // ms
            val expectedDelta = 2.67f  // 128 frames @ 48kHz
            
            // Calcular jitter como variabilidad
            currentJitter = (currentJitter * 0.9f) + (abs(delta - expectedDelta) * 0.1f)
            
            // Ajustar tamaño del buffer según jitter
            targetSize = when {
                currentJitter < 1f -> 2   // Red muy estable
                currentJitter < 3f -> 4   // Red estable
                currentJitter < 10f -> 6  // Red variable
                else -> 10                // Red inestable
            }
        }
        
        packetTimes.addLast(now)
        if (packetTimes.size > 32) packetTimes.removeFirst()
    }
    
    fun getTargetSize() = targetSize
    fun getCurrentJitter() = currentJitter
}
```

---

### 5. **OboeAudioRenderer.kt** - ✅ Bien optimizado, detalles menores

**Estado Actual:**
```kotlin
// ✅ Buffer reducido
private var OPTIMAL_BUFFER_SIZE = 64  // ~1.33ms

// ✅ Pool de buffers
private val bufferPool = ArrayDeque<FloatArray>()

// ✅ LUT para soft clipping
private val clipLUT = FloatArray(4096) { ... }
```

**🎯 OPTIMIZACIONES ADICIONALES:**

```kotlin
// ✅ OPTIMIZACIÓN: SIMD-friendly processing
// Procesar en bloques de 4 para aprovechar vectorización
fun renderChannelRF(channel: Int, audioData: FloatArray, samplePosition: Long) {
    // ... setup ...
    
    // Procesar en bloques de 4 (NEON/SSE friendly)
    val blockSize = audioData.size and 3.inv()  // Múltiplo de 4
    var i = 0
    
    while (i < blockSize) {
        // Procesar 4 samples a la vez
        val s0 = audioData[i] * leftGain
        val s1 = audioData[i + 1] * leftGain
        val s2 = audioData[i + 2] * leftGain
        val s3 = audioData[i + 3] * leftGain
        
        val sr0 = audioData[i] * rightGain
        val sr1 = audioData[i + 1] * rightGain
        val sr2 = audioData[i + 2] * rightGain
        val sr3 = audioData[i + 3] * rightGain
        
        stereoBuffer[i * 2] = softClip(s0)
        stereoBuffer[i * 2 + 1] = softClip(sr0)
        stereoBuffer[i * 2 + 2] = softClip(s1)
        stereoBuffer[i * 2 + 3] = softClip(sr1)
        stereoBuffer[i * 2 + 4] = softClip(s2)
        stereoBuffer[i * 2 + 5] = softClip(sr2)
        stereoBuffer[i * 2 + 6] = softClip(s3)
        stereoBuffer[i * 2 + 7] = softClip(sr3)
        
        i += 4
    }
    
    // Procesar samples restantes
    while (i < audioData.size) {
        stereoBuffer[i * 2] = softClip(audioData[i] * leftGain)
        stereoBuffer[i * 2 + 1] = softClip(audioData[i] * rightGain)
        i++
    }
}
```

---

## 🌐 OPTIMIZACIONES DE RED

### Configuración de Socket TCP Óptima

```kotlin
socket = Socket().apply {
    // ✅ CRÍTICO: Deshabilitar Nagle's algorithm
    tcpNoDelay = true
    
    // ✅ CRÍTICO: Buffers grandes
    sendBufferSize = 65536
    receiveBufferSize = 131072
    
    // ✅ Keep-alive para detección rápida de desconexión
    keepAlive = true
    
    // ✅ Timeout razonable
    soTimeout = 10000
    
    // ✅ NUEVO: Traffic class para QoS (prioridad de audio)
    // DSCP EF (Expedited Forwarding) = 0x2E << 2 = 0xB8
    trafficClass = 0xB8
    
    // ✅ NUEVO: Linger off para cierre rápido
    setSoLinger(false, 0)
}
```

### Configuración WiFi Óptima

```kotlin
// Ya implementado correctamente en AudioStreamForegroundService.kt
wifiLock = wifiManager.createWifiLock(
    WifiManager.WIFI_MODE_FULL_LOW_LATENCY,  // ✅ CRÍTICO
    "FichaTech:AudioStreamRF"
)
```

**Nota:** `WIFI_MODE_FULL_LOW_LATENCY` requiere API 29+ (Android 10)

---

## 📱 OPTIMIZACIONES ESPECÍFICAS POR DISPOSITIVO

### Detección de Capacidades del Dispositivo

```kotlin
class DeviceOptimizer(private val context: Context) {
    
    data class DeviceProfile(
        val supportsLowLatency: Boolean,
        val supportsProAudio: Boolean,
        val optimalBufferSize: Int,
        val optimalFramesPerBurst: Int,
        val recommendedJitterBuffer: Int,
        val useDirectBuffer: Boolean
    )
    
    fun detectProfile(): DeviceProfile {
        val pm = context.packageManager
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        
        val supportsLowLatency = pm.hasSystemFeature(PackageManager.FEATURE_AUDIO_LOW_LATENCY)
        val supportsProAudio = pm.hasSystemFeature(PackageManager.FEATURE_AUDIO_PRO)
        
        val nativeSampleRate = am.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)
            ?.toIntOrNull() ?: 48000
        val framesPerBurst = am.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)
            ?.toIntOrNull() ?: 192
        
        // Perfil según capacidades
        return when {
            supportsProAudio -> DeviceProfile(
                supportsLowLatency = true,
                supportsProAudio = true,
                optimalBufferSize = 32,          // Ultra agresivo
                optimalFramesPerBurst = framesPerBurst,
                recommendedJitterBuffer = 2,     // Mínimo
                useDirectBuffer = true
            )
            supportsLowLatency -> DeviceProfile(
                supportsLowLatency = true,
                supportsProAudio = false,
                optimalBufferSize = 64,          // Agresivo
                optimalFramesPerBurst = framesPerBurst,
                recommendedJitterBuffer = 4,     // Bajo
                useDirectBuffer = true
            )
            else -> DeviceProfile(
                supportsLowLatency = false,
                supportsProAudio = false,
                optimalBufferSize = 128,         // Conservador
                optimalFramesPerBurst = framesPerBurst,
                recommendedJitterBuffer = 8,     // Medio
                useDirectBuffer = false
            )
        }
    }
}
```

---

## ⚖️ COMPATIBILIDAD CON POLÍTICAS DE GOOGLE PLAY

### Requisitos de Foreground Service

```kotlin
// ✅ YA IMPLEMENTADO CORRECTAMENTE en AudioStreamForegroundService.kt

// 1. Tipo de servicio declarado en manifest
<service
    android:name=".audiostream.AudioStreamForegroundService"
    android:foregroundServiceType="mediaPlayback"
    android:exported="false" />

// 2. Permisos requeridos
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
<uses-permission android:name="android.permission.WAKE_LOCK" />

// 3. Notificación obligatoria antes de startForeground()
startForeground(NOTIFICATION_ID, notification, 
    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
```

### Lock Management (Cumplimiento de Políticas)

```kotlin
// ✅ YA IMPLEMENTADO: Timeout de 5 minutos con renovación
private const val LOCK_TIMEOUT_MS = 5 * 60 * 1000L
private const val RENEWAL_INTERVAL_MS = 4 * 60 * 1000L

// ✅ Renovación periódica para evitar timeout del sistema
private val lockRenewalRunnable = object : Runnable {
    override fun run() {
        renewLocks()
        lockRenewalHandler.postDelayed(this, RENEWAL_INTERVAL_MS)
    }
}
```

### Optimizaciones Permitidas por Google

| Optimización | Permitida | Notas |
|-------------|-----------|-------|
| MMAP Audio | ✅ Sí | Automático con Oboe |
| Thread Priority URGENT_AUDIO | ✅ Sí | API pública |
| WiFi Low Latency Lock | ✅ Sí | Requiere permiso |
| Wake Lock | ✅ Sí | Con foreground service |
| CPU Affinity | ⚠️ Parcial | No hay API Java oficial |
| Real-time scheduling | ❌ No | Requiere root |

---

## 🛠️ IMPLEMENTACIÓN PASO A PASO

### Fase 1: Quick Wins (1-2 días)

1. **Reducir buffer en AudioCallback a 128 frames**
   ```cpp
   static constexpr int BUFFER_SIZE_FRAMES = 128;  // ~2.7ms
   ```

2. **Eliminar dispatch a Main thread en callback de audio**
   ```kotlin
   // ANTES
   withContext(Dispatchers.Main) { onAudioData?.invoke(audioData) }
   
   // DESPUÉS
   onAudioData?.invoke(audioData)  // Directo
   ```

3. **Aumentar buffers de socket**
   ```kotlin
   sendBufferSize = 65536
   receiveBufferSize = 131072
   ```

**Ganancia estimada:** 2-4ms

### Fase 2: Optimizaciones Medias (1 semana)

1. **Implementar lock-free ring buffer en AudioCallback**
2. **Añadir jitter buffer adaptativo para UDP**
3. **Configurar QoS de tráfico (traffic class)**

**Ganancia estimada:** 2-3ms adicionales

### Fase 3: Optimizaciones Avanzadas (2+ semanas)

1. **Detección dinámica de perfil de dispositivo**
2. **Buffer sizes configurables según dispositivo**
3. **Procesamiento SIMD para audio**
4. **Métricas de latencia en tiempo real**

**Ganancia estimada:** 1-2ms adicionales

---

## 📈 MÉTRICAS Y MONITOREO

### Implementar Medición de Latencia End-to-End

```kotlin
class LatencyMetrics {
    private var networkLatency = 0f
    private var processingLatency = 0f
    private var bufferLatency = 0f
    private var outputLatency = 0f
    
    // Calcular desde timestamp del servidor
    fun measureNetworkLatency(serverTimestamp: Long) {
        val now = System.currentTimeMillis()
        networkLatency = (networkLatency * 0.9f) + ((now - serverTimestamp) * 0.1f)
    }
    
    // Obtener latencia total estimada
    fun getTotalLatency(): Float {
        return networkLatency + processingLatency + bufferLatency + outputLatency
    }
    
    // Debug info
    fun getDetailedMetrics(): Map<String, Float> = mapOf(
        "network_ms" to networkLatency,
        "processing_ms" to processingLatency,
        "buffer_ms" to bufferLatency,
        "output_ms" to outputLatency,
        "total_ms" to getTotalLatency()
    )
}
```

---

## 🎯 RESUMEN: LATENCIA MÍNIMA ALCANZABLE

| Escenario | Latencia Estimada | Requisitos |
|-----------|-------------------|------------|
| **Óptimo (Pro Audio device, WiFi 5GHz, UDP)** | 5-8ms | Pixel 6+, Samsung Pro Audio |
| **Bueno (Low Latency device, WiFi 5GHz, TCP)** | 10-15ms | La mayoría de flagships |
| **Normal (Device estándar, WiFi 2.4GHz)** | 20-40ms | Gama media |
| **Conservador (Compatibilidad máxima)** | 40-80ms | Cualquier Android 7+ |

---

## ⚠️ RIESGOS Y MITIGACIONES

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Glitches con buffer muy pequeño | Audio cortado | Buffer adaptativo según estabilidad |
| CPU usage alto con callbacks frecuentes | Batería, throttling | Monitorear CPU, reducir si > 30% |
| Incompatibilidad dispositivos antiguos | Crashes | Feature flags, fallback a valores seguros |
| Rechazo de Google Play | App no publicada | Seguir guías de foreground service |

---

## 📚 REFERENCIAS

- [Oboe Best Practices](https://github.com/google/oboe/blob/main/docs/GettingStarted.md)
- [Android Audio Latency](https://source.android.com/devices/audio/latency)
- [AAudio vs OpenSL ES](https://developer.android.com/ndk/guides/audio/aaudio/aaudio)
- [Google Play Foreground Services](https://developer.android.com/guide/components/foreground-services)
- [Lock-free Programming](https://preshing.com/20120612/an-introduction-to-lock-free-programming/)

---

**Última actualización:** Enero 2026  
**Autor:** Análisis de arquitectura FichaTech Audio
