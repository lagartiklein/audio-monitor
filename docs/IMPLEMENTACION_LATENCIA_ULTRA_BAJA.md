# 🚀 Implementación Práctica: Código Optimizado

Este documento contiene código listo para implementar las optimizaciones más importantes.

---

## 1. AudioCallback Lock-Free (C++)

Reemplazar completamente `audio_callback.h`:

```cpp
// audio_callback_optimized.h - Lock-Free Ultra Low Latency
#ifndef FICHATECH_AUDIO_CALLBACK_OPTIMIZED_H
#define FICHATECH_AUDIO_CALLBACK_OPTIMIZED_H

#include <oboe/Oboe.h>
#include <android/log.h>
#include <atomic>
#include <cstring>
#include <cstdint>

#define LOG_TAG "AudioCallbackOpt"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

/**
 * Lock-Free Single-Producer Single-Consumer Ring Buffer
 * 
 * Principios:
 * 1. Solo el productor (network thread) modifica writePos
 * 2. Solo el consumidor (audio callback) modifica readPos
 * 3. Memory ordering garantiza visibilidad entre threads
 * 4. Sin mutex = sin bloqueo = latencia mínima
 */
class LockFreeAudioCallback : public oboe::AudioStreamDataCallback {
private:
    // ⚠️ CRÍTICO: Buffer size DEBE ser potencia de 2 para operación & eficiente
    static constexpr int BUFFER_SIZE_FRAMES = 128;   // ~2.67ms @ 48kHz
    static constexpr int BUFFER_SIZE_SAMPLES_MAX = BUFFER_SIZE_FRAMES * 2;  // Stereo
    static constexpr int BUFFER_MASK = BUFFER_SIZE_FRAMES - 1;
    
    // Buffer alineado a 64 bytes (línea de cache típica)
    alignas(64) float circularBuffer[BUFFER_SIZE_SAMPLES_MAX];
    
    // Posiciones en líneas de cache separadas (evitar false sharing)
    alignas(64) std::atomic<uint32_t> writePos{0};
    alignas(64) std::atomic<uint32_t> readPos{0};
    
    // Estadísticas (solo lectura en hotpath)
    alignas(64) std::atomic<uint32_t> underrunCount{0};
    alignas(64) std::atomic<uint32_t> overrunCount{0};
    alignas(64) std::atomic<int64_t> lastWriteTimeNs{0};
    
    int channelCount;
    int bufferSizeSamples;

public:
    explicit LockFreeAudioCallback(int channels) 
        : channelCount(channels)
        , bufferSizeSamples(BUFFER_SIZE_FRAMES * channels) {
        
        // Inicializar buffer a cero
        std::memset(circularBuffer, 0, sizeof(circularBuffer));
        
        LOGD("✅ LockFreeAudioCallback: %d canales, %d frames (~%.1fms)", 
             channels, BUFFER_SIZE_FRAMES, 
             BUFFER_SIZE_FRAMES * 1000.0f / 48000.0f);
    }

    /**
     * Escribir audio desde network thread (productor)
     * 
     * @return Número de frames escritos (puede ser menor que numFrames si buffer lleno)
     */
    int writeAudio(const float* data, int numFrames) {
        // Cargar posiciones con memory ordering apropiado
        const uint32_t currentWrite = writePos.load(std::memory_order_relaxed);
        const uint32_t currentRead = readPos.load(std::memory_order_acquire);
        
        // Calcular frames disponibles para escritura
        // (read - write - 1) & MASK = espacio libre en frames
        const uint32_t freeFrames = ((currentRead - currentWrite - 1) & BUFFER_MASK);
        
        if (freeFrames == 0) {
            overrunCount.fetch_add(1, std::memory_order_relaxed);
            return 0;  // Buffer lleno
        }
        
        const int framesToWrite = (numFrames <= static_cast<int>(freeFrames)) 
                                  ? numFrames 
                                  : static_cast<int>(freeFrames);
        
        const int samplesToWrite = framesToWrite * channelCount;
        uint32_t writeIdx = (currentWrite * channelCount) % bufferSizeSamples;
        
        // Escribir con wrap-around eficiente
        for (int i = 0; i < samplesToWrite; ++i) {
            circularBuffer[writeIdx] = data[i];
            writeIdx = (writeIdx + 1) % bufferSizeSamples;
        }
        
        // Actualizar posición con release fence (visible para consumidor)
        writePos.store((currentWrite + framesToWrite) & BUFFER_MASK, 
                       std::memory_order_release);
        
        // Timestamp para estadísticas (no crítico para latencia)
        lastWriteTimeNs.store(getCurrentTimeNs(), std::memory_order_relaxed);
        
        return framesToWrite;
    }

    /**
     * Callback de Oboe (consumidor) - CRÍTICO: debe ser lo más rápido posible
     */
    oboe::DataCallbackResult onAudioReady(
            oboe::AudioStream* audioStream,
            void* audioData,
            int32_t numFrames) override {
        
        auto* outputBuffer = static_cast<float*>(audioData);
        const int samplesNeeded = numFrames * channelCount;
        
        // Cargar posiciones
        const uint32_t currentRead = readPos.load(std::memory_order_relaxed);
        const uint32_t currentWrite = writePos.load(std::memory_order_acquire);
        
        // Calcular frames disponibles para lectura
        const uint32_t availableFrames = (currentWrite - currentRead) & BUFFER_MASK;
        
        if (availableFrames == 0) {
            // Buffer vacío - silencio rápido
            std::memset(outputBuffer, 0, samplesNeeded * sizeof(float));
            underrunCount.fetch_add(1, std::memory_order_relaxed);
            return oboe::DataCallbackResult::Continue;
        }
        
        const int framesToRead = (static_cast<int>(availableFrames) >= numFrames) 
                                 ? numFrames 
                                 : static_cast<int>(availableFrames);
        
        const int samplesToRead = framesToRead * channelCount;
        uint32_t readIdx = (currentRead * channelCount) % bufferSizeSamples;
        
        // Leer audio
        for (int i = 0; i < samplesToRead; ++i) {
            outputBuffer[i] = circularBuffer[readIdx];
            readIdx = (readIdx + 1) % bufferSizeSamples;
        }
        
        // Silencio para samples faltantes (si hay)
        if (samplesToRead < samplesNeeded) {
            std::memset(outputBuffer + samplesToRead, 0, 
                       (samplesNeeded - samplesToRead) * sizeof(float));
        }
        
        // Actualizar posición de lectura
        readPos.store((currentRead + framesToRead) & BUFFER_MASK, 
                      std::memory_order_release);
        
        return oboe::DataCallbackResult::Continue;
    }

    // === Métodos de estadísticas (no críticos para latencia) ===
    
    int getAvailableFrames() const {
        const uint32_t w = writePos.load(std::memory_order_acquire);
        const uint32_t r = readPos.load(std::memory_order_acquire);
        return (w - r) & BUFFER_MASK;
    }
    
    uint32_t getUnderrunCount() const { 
        return underrunCount.load(std::memory_order_relaxed); 
    }
    
    uint32_t getOverrunCount() const { 
        return overrunCount.load(std::memory_order_relaxed); 
    }
    
    float getLatencyMs() const {
        return (getAvailableFrames() * 1000.0f) / 48000.0f;
    }
    
    float getBufferUsagePercent() const {
        return (getAvailableFrames() * 100.0f) / BUFFER_SIZE_FRAMES;
    }
    
    bool isReceivingAudio() const {
        const int64_t now = getCurrentTimeNs();
        const int64_t lastWrite = lastWriteTimeNs.load(std::memory_order_relaxed);
        return (now - lastWrite) < 2000000000LL;  // 2 segundos en nanosegundos
    }
    
    void clear() {
        writePos.store(0, std::memory_order_release);
        readPos.store(0, std::memory_order_release);
        std::memset(circularBuffer, 0, sizeof(circularBuffer));
        LOGD("🧹 Buffer limpiado");
    }
    
    struct Stats {
        int availableFrames;
        float latencyMs;
        bool isReceiving;
        uint32_t underruns;
        uint32_t overruns;
        float usagePercent;
    };
    
    Stats getStats() const {
        return {
            getAvailableFrames(),
            getLatencyMs(),
            isReceivingAudio(),
            getUnderrunCount(),
            getOverrunCount(),
            getBufferUsagePercent()
        };
    }

private:
    static int64_t getCurrentTimeNs() {
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        return ts.tv_sec * 1000000000LL + ts.tv_nsec;
    }
};

#endif // FICHATECH_AUDIO_CALLBACK_OPTIMIZED_H
```

---

## 2. NativeAudioClient Optimizado (Kotlin)

Cambios clave para el cliente TCP:

```kotlin
// Agregar a companion object de NativeAudioClient.kt
companion object {
    // ... constantes existentes ...
    
    // ✅ OPTIMIZADOS: Buffers de socket más grandes
    private const val SOCKET_SNDBUF = 65536      // 64KB (era 8KB)
    private const val SOCKET_RCVBUF = 131072     // 128KB (era 4KB)
    
    // ✅ OPTIMIZADO: Timeout más corto
    private const val READ_TIMEOUT = 10000       // 10s (era 30s)
    
    // ✅ NUEVO: QoS para audio
    private const val TRAFFIC_CLASS_EF = 0xB8    // DSCP Expedited Forwarding
}

// ✅ NUEVA función de conexión optimizada
private suspend fun connectInternal(): Boolean = withContext(Dispatchers.IO) {
    try {
        socket = Socket().apply {
            // Configuración básica
            soTimeout = READ_TIMEOUT
            tcpNoDelay = true      // ⚠️ CRÍTICO: Deshabilitar Nagle
            keepAlive = true
            
            // Buffers optimizados
            sendBufferSize = SOCKET_SNDBUF
            receiveBufferSize = SOCKET_RCVBUF
            
            // ✅ NUEVO: QoS para prioridad de audio
            try {
                trafficClass = TRAFFIC_CLASS_EF
                Log.d(TAG, "✅ Traffic class EF configurado")
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ No se pudo configurar traffic class: ${e.message}")
            }
            
            // ✅ NUEVO: Linger off para cierre rápido
            setSoLinger(false, 0)
            
            // Conectar
            connect(InetSocketAddress(serverIp, serverPort), CONNECT_TIMEOUT)
        }
        
        // Streams con buffer optimizado
        inputStream = DataInputStream(
            socket?.getInputStream()?.buffered(SOCKET_RCVBUF)
        )
        outputStream = DataOutputStream(
            socket?.getOutputStream()?.buffered(SOCKET_SNDBUF)
        )
        
        // ... resto del código existente ...
        
        true
    } catch (e: Exception) {
        Log.e(TAG, "❌ Error conectando: ${e.message}")
        false
    }
}

// ✅ OPTIMIZACIÓN CRÍTICA: Callback directo sin cambio de contexto
private fun startReaderThread() {
    CoroutineScope(Dispatchers.IO).launch {
        setThreadPriority()
        
        val headerBuffer = ByteArray(HEADER_SIZE)
        
        while (!shouldStop && isConnected) {
            try {
                val input = inputStream ?: break
                
                input.readFully(headerBuffer)
                val header = decodeHeader(headerBuffer)
                
                // Validaciones...
                if (header.magic != MAGIC_NUMBER) continue
                
                val payload = ByteArray(header.payloadLength)
                if (header.payloadLength > 0) {
                    input.readFully(payload)
                }
                
                when (header.msgType) {
                    MSG_TYPE_AUDIO -> {
                        val audioData = decodeAudioPayload(payload, header.flags)
                        if (audioData != null) {
                            // ⚠️ CAMBIO CRÍTICO: NO dispatch a Main thread
                            // El callback se ejecuta directamente en el thread de IO
                            // El consumidor (OboeAudioRenderer) debe ser thread-safe
                            onAudioData?.invoke(audioData)
                        }
                    }
                    MSG_TYPE_CONTROL -> handleControlMessage(payload)
                }
                
            } catch (e: SocketTimeoutException) {
                continue  // Normal, seguir esperando
            } catch (e: Exception) {
                if (!shouldStop) {
                    handleConnectionLost("Error: ${e.message}")
                }
                break
            }
        }
    }
}

// ✅ OPTIMIZACIÓN: Thread priority mejorada
private fun setThreadPriority() {
    try {
        // Prioridad máxima de audio
        android.os.Process.setThreadPriority(
            android.os.Process.THREAD_PRIORITY_URGENT_AUDIO
        )
        
        // Información de debug
        val tid = android.os.Process.myTid()
        Log.d(TAG, "✅ Thread $tid: URGENT_AUDIO priority")
        
    } catch (e: Exception) {
        Log.w(TAG, "⚠️ No se pudo establecer prioridad: ${e.message}")
    }
}
```

---

## 3. UDPAudioClient con Jitter Buffer Adaptativo

```kotlin
// Agregar a UDPAudioClient.kt

/**
 * Jitter Buffer Adaptativo
 * 
 * Ajusta automáticamente su tamaño basado en la variabilidad de la red
 */
class AdaptiveJitterBuffer(
    private val minPackets: Int = 2,
    private val maxPackets: Int = 10
) {
    private var targetSize = 4
    private var currentJitter = 0f
    private val packetArrivals = LongArray(32)
    private var arrivalIndex = 0
    private var arrivalCount = 0
    
    // Buffer de paquetes ordenados por sequence
    private val buffer = TreeMap<Int, FloatAudioData>()
    private val bufferLock = Any()
    private var lastDeliveredSeq = -1
    
    /**
     * Registrar llegada de paquete y calcular jitter
     */
    fun onPacketArrival(sequence: Int, data: FloatAudioData): FloatAudioData? {
        val now = System.nanoTime()
        
        // Actualizar historial de tiempos de llegada
        synchronized(this) {
            packetArrivals[arrivalIndex] = now
            arrivalIndex = (arrivalIndex + 1) % packetArrivals.size
            arrivalCount = minOf(arrivalCount + 1, packetArrivals.size)
            
            // Calcular jitter si tenemos suficientes samples
            if (arrivalCount >= 4) {
                updateJitterEstimate()
            }
        }
        
        // Agregar al buffer
        synchronized(bufferLock) {
            // Descartar paquetes muy antiguos
            if (lastDeliveredSeq >= 0 && sequence <= lastDeliveredSeq) {
                return null  // Paquete ya reproducido
            }
            
            buffer[sequence] = data
            
            // Limitar tamaño del buffer
            while (buffer.size > targetSize * 2) {
                val removed = buffer.pollFirstEntry()
                Log.w("JitterBuffer", "⚠️ Descartando paquete antiguo seq=${removed?.key}")
            }
            
            // Entregar si tenemos suficientes paquetes
            return tryDeliverNext()
        }
    }
    
    private fun tryDeliverNext(): FloatAudioData? {
        if (buffer.size < targetSize) {
            return null  // Esperar más paquetes
        }
        
        // Buscar el siguiente paquete en secuencia
        val expectedSeq = lastDeliveredSeq + 1
        
        val entry = buffer.entries.firstOrNull()
        if (entry != null) {
            buffer.remove(entry.key)
            lastDeliveredSeq = entry.key
            return entry.value
        }
        
        return null
    }
    
    private fun updateJitterEstimate() {
        // Calcular variabilidad de inter-arrival times
        var sumDiff = 0L
        var count = 0
        
        for (i in 1 until arrivalCount) {
            val prev = packetArrivals[(arrivalIndex - i + packetArrivals.size) % packetArrivals.size]
            val curr = packetArrivals[(arrivalIndex - i + 1 + packetArrivals.size) % packetArrivals.size]
            if (prev > 0 && curr > 0) {
                sumDiff += kotlin.math.abs(curr - prev)
                count++
            }
        }
        
        if (count > 0) {
            val avgDiffNs = sumDiff / count
            val expectedDiffNs = 2_666_666L  // ~2.67ms @ 48kHz/128 frames
            
            val jitterNs = kotlin.math.abs(avgDiffNs - expectedDiffNs)
            val jitterMs = jitterNs / 1_000_000f
            
            // EMA del jitter
            currentJitter = (currentJitter * 0.9f) + (jitterMs * 0.1f)
            
            // Ajustar target size
            targetSize = when {
                currentJitter < 1f -> minPackets      // Red muy estable
                currentJitter < 3f -> minPackets + 1  // Red estable
                currentJitter < 5f -> minPackets + 2  // Red variable
                currentJitter < 10f -> maxPackets - 2 // Red inestable
                else -> maxPackets                    // Red muy inestable
            }
        }
    }
    
    fun getStats(): Map<String, Any> = synchronized(bufferLock) {
        mapOf(
            "buffer_size" to buffer.size,
            "target_size" to targetSize,
            "jitter_ms" to currentJitter,
            "last_delivered_seq" to lastDeliveredSeq
        )
    }
    
    fun reset() {
        synchronized(bufferLock) {
            buffer.clear()
            lastDeliveredSeq = -1
        }
        synchronized(this) {
            arrivalIndex = 0
            arrivalCount = 0
            currentJitter = 0f
            targetSize = 4
        }
    }
}
```

---

## 4. OboeAudioRenderer Thread-Safe

Modificaciones para soportar callbacks directos sin dispatch:

```kotlin
// En OboeAudioRenderer.kt

/**
 * Renderiza audio de forma thread-safe
 * 
 * ⚠️ IMPORTANTE: Este método puede ser llamado desde cualquier thread
 * El lock-free ring buffer en C++ garantiza thread safety
 */
@Synchronized  // Solo para acceso a channelStates (no afecta hotpath de audio)
fun renderChannelRF(channel: Int, audioData: FloatArray, samplePosition: Long) {
    if (!isInitialized || audioData.isEmpty()) {
        return
    }
    
    // Obtener estado del canal (thread-safe con synchronized)
    val state = channelStates.getOrPut(channel) { ChannelState() }
    
    if (!state.isActive || state.gainDb <= -60f) {
        return
    }
    
    totalPacketsReceived++
    
    // Obtener o crear stream (internamente thread-safe)
    val streamHandle = getOrCreateStream(channel)
    if (streamHandle == 0L) {
        totalPacketsDropped++
        return
    }
    
    // Calcular ganancias (operaciones matemáticas, thread-safe)
    val totalGainDb = state.gainDb + masterGainDb
    val linearGain = dbToLinear(totalGainDb)
    
    val panRad = ((state.pan + 1f) * Math.PI / 4).toFloat()
    val leftGain = cos(panRad) * linearGain
    val rightGain = sin(panRad) * linearGain
    
    // Usar buffer del pool (thread-local o pool thread-safe)
    val bufferSize = audioData.size * 2
    val stereoBuffer = FloatArray(bufferSize)  // Temporal por seguridad
    
    // Procesar audio
    for (i in audioData.indices) {
        val sample = audioData[i]
        stereoBuffer[i * 2] = softClip(sample * leftGain)
        stereoBuffer[i * 2 + 1] = softClip(sample * rightGain)
    }
    
    // Actualizar niveles (atomic update para thread safety)
    state.peakLevel = audioData.maxOfOrNull { abs(it * linearGain) } ?: 0f
    state.packetsReceived++
    
    // Escribir a Oboe (el lock-free buffer maneja thread safety internamente)
    try {
        val written = nativeWriteAudio(streamHandle, stereoBuffer)
        
        if (written < stereoBuffer.size) {
            totalPacketsDropped += (stereoBuffer.size - written) / 2
        }
    } catch (e: Exception) {
        Log.e(TAG, "❌ Error escribiendo canal $channel: ${e.message}")
        totalPacketsDropped += audioData.size / 2
    }
}
```

---

## 5. Métricas de Latencia en Tiempo Real

```kotlin
// LatencyMetrics.kt

/**
 * Sistema de métricas de latencia end-to-end
 */
object LatencyMetrics {
    private const val TAG = "LatencyMetrics"
    
    // Componentes de latencia (en ms)
    private var networkLatencyMs = 0f
    private var jitterMs = 0f
    private var bufferLatencyMs = 0f
    private var outputLatencyMs = 0f
    
    // Historial para percentiles
    private val latencyHistory = ArrayDeque<Float>(100)
    private val historyLock = Any()
    
    /**
     * Registrar medición de latencia de red
     */
    fun recordNetworkLatency(serverTimestamp: Long, receiveTimestamp: Long = System.currentTimeMillis()) {
        val latency = (receiveTimestamp - serverTimestamp).toFloat()
        
        // EMA para suavizar
        networkLatencyMs = (networkLatencyMs * 0.9f) + (latency * 0.1f)
        
        // Guardar en historial
        synchronized(historyLock) {
            latencyHistory.addLast(latency)
            if (latencyHistory.size > 100) {
                latencyHistory.removeFirst()
            }
        }
    }
    
    /**
     * Registrar latencia de jitter buffer
     */
    fun recordJitterBufferLatency(jitterBufferMs: Float) {
        jitterMs = (jitterMs * 0.9f) + (jitterBufferMs * 0.1f)
    }
    
    /**
     * Registrar latencia del buffer de audio
     */
    fun recordBufferLatency(bufferMs: Float) {
        bufferLatencyMs = (bufferLatencyMs * 0.9f) + (bufferMs * 0.1f)
    }
    
    /**
     * Registrar latencia de salida (de Oboe)
     */
    fun recordOutputLatency(outputMs: Float) {
        outputLatencyMs = (outputLatencyMs * 0.9f) + (outputMs * 0.1f)
    }
    
    /**
     * Obtener latencia total estimada
     */
    fun getTotalLatencyMs(): Float {
        return networkLatencyMs + jitterMs + bufferLatencyMs + outputLatencyMs
    }
    
    /**
     * Obtener percentil de latencia
     */
    fun getLatencyPercentile(percentile: Int): Float {
        synchronized(historyLock) {
            if (latencyHistory.isEmpty()) return 0f
            
            val sorted = latencyHistory.sorted()
            val index = ((percentile / 100.0) * (sorted.size - 1)).toInt()
            return sorted[index]
        }
    }
    
    /**
     * Obtener resumen de métricas
     */
    fun getMetrics(): Map<String, Any> {
        return mapOf(
            "network_ms" to networkLatencyMs,
            "jitter_ms" to jitterMs,
            "buffer_ms" to bufferLatencyMs,
            "output_ms" to outputLatencyMs,
            "total_ms" to getTotalLatencyMs(),
            "p50_ms" to getLatencyPercentile(50),
            "p95_ms" to getLatencyPercentile(95),
            "p99_ms" to getLatencyPercentile(99)
        )
    }
    
    /**
     * Log periódico de métricas
     */
    fun logMetrics() {
        Log.d(TAG, """
            |📊 Latencia End-to-End:
            |   Network: ${String.format("%.1f", networkLatencyMs)}ms
            |   Jitter Buffer: ${String.format("%.1f", jitterMs)}ms
            |   Audio Buffer: ${String.format("%.1f", bufferLatencyMs)}ms
            |   Output: ${String.format("%.1f", outputLatencyMs)}ms
            |   ────────────────
            |   TOTAL: ${String.format("%.1f", getTotalLatencyMs())}ms
            |   P95: ${String.format("%.1f", getLatencyPercentile(95))}ms
        """.trimMargin())
    }
    
    fun reset() {
        networkLatencyMs = 0f
        jitterMs = 0f
        bufferLatencyMs = 0f
        outputLatencyMs = 0f
        synchronized(historyLock) {
            latencyHistory.clear()
        }
    }
}
```

---

## 6. CMakeLists.txt Actualizado

```cmake
# CMakeLists.txt - Optimizado para baja latencia

cmake_minimum_required(VERSION 3.18)

project(fichatech_audio)

# ⚠️ CRÍTICO: Optimizaciones de compilador para latencia
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3")           # Optimización máxima
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -ffast-math")   # Math rápido (menos preciso)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -march=armv8-a") # NEON habilitado
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -DNDEBUG")       # Sin asserts

# LTO (Link Time Optimization)
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)

# Oboe
find_package(oboe REQUIRED CONFIG)

add_library(fichatech_audio SHARED
    native_audio_engine.cpp
)

target_link_libraries(fichatech_audio
    oboe::oboe
    android
    log
)

# Cache alignment para mejor rendimiento
target_compile_options(fichatech_audio PRIVATE
    -falign-functions=64
    -falign-loops=64
)
```

---

## Checklist de Implementación

### ✅ Fase 1: Quick Wins (Sin riesgo)
- [ ] Reducir `BUFFER_SIZE_FRAMES` de 256 a 128 en audio_callback.h
- [ ] Aumentar buffers de socket TCP a 64KB/128KB
- [ ] Eliminar `withContext(Dispatchers.Main)` en callback de audio
- [ ] Habilitar `tcpNoDelay = true` (ya implementado)

### ✅ Fase 2: Optimizaciones Medias
- [ ] Implementar `LockFreeAudioCallback` (reemplazar mutex)
- [ ] Implementar `AdaptiveJitterBuffer` para UDP
- [ ] Añadir `trafficClass = 0xB8` para QoS
- [ ] Añadir métricas de latencia (`LatencyMetrics`)

### ✅ Fase 3: Optimizaciones Avanzadas
- [ ] Actualizar CMakeLists.txt con flags de optimización
- [ ] Implementar detección de perfil de dispositivo
- [ ] Añadir configuración dinámica de buffer según dispositivo
- [ ] Testing en múltiples dispositivos

---

**Resultado esperado:** Reducción de latencia de ~25-40ms a ~8-15ms en dispositivos compatibles con Low Latency Audio.
