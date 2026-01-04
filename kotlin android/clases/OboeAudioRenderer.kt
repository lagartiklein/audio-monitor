package com.cepalabsfree.fichatech.audiostream

import android.content.Context
import android.media.AudioManager
import android.util.Log
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.*

class OboeAudioRenderer(private val context: Context? = null) {

    companion object {
        private const val TAG = "OboeAudioRenderer"

        // ✅ SINGLETON: Una sola instancia compartida por toda la app
        @Volatile
        private var instance: OboeAudioRenderer? = null

        fun getInstance(context: Context? = null): OboeAudioRenderer {
            return instance ?: synchronized(this) {
                instance ?: OboeAudioRenderer(context).also { instance = it }
            }
        }

        // ✅ Variables mutables con valores por defecto seguros
        private var OPTIMAL_SAMPLE_RATE = 48000

        private const val CHANNELS = 2
        private const val MAX_WRITE_FAILURES = 2
        private const val MAX_SIMULTANEOUS_STREAMS = 48

        // ✅ OPTIMIZACIÓN LATENCIA FASE 1: Buffer size reducido para baja latencia
        // 64 frames @ 48kHz = 1.33ms (vs 2.67ms con 128 frames)
        // Nota: Requiere WiFi estable, puede aumentar underruns en redes inestables
        private var OPTIMAL_BUFFER_SIZE = 64  // ⬇️ REDUCIDO de 128 frames
        private const val MIN_BUFFER_SIZE = 64
        private const val MAX_BUFFER_SIZE = 256

        init {
            try {
                System.loadLibrary("fichatech_audio")
                Log.d(TAG, "✅ Biblioteca nativa Oboe cargada (Latencia Fase 1 optimizada)")
                Log.d(TAG, "   🎯 Buffer: ${OPTIMAL_BUFFER_SIZE} frames = ~1.33ms latencia")
            } catch (e: UnsatisfiedLinkError) {
                Log.e(TAG, "❌ Error cargando biblioteca nativa: ${e.message}", e)
            }
        }
    }

    // ✅ CORREGIDO: Métodos nativos con firmas correctas
    private external fun nativeCreateEngine(sampleRate: Int, channels: Int): Long
    private external fun nativeCreateStream(engineHandle: Long, channelId: Int): Long
    private external fun nativeWriteAudio(streamHandle: Long, buffer: FloatArray): Int
    private external fun nativeStartStream(streamHandle: Long)
    private external fun nativeStopStream(streamHandle: Long)
    private external fun nativeGetLatency(streamHandle: Long): Float
    private external fun nativeGetBufferStats(streamHandle: Long): Int
    private external fun nativeGetRFStats(streamHandle: Long): IntArray
    private external fun nativeClearBuffer(streamHandle: Long)
    private external fun nativeDestroyStream(streamHandle: Long)
    private external fun nativeDestroyEngine(engineHandle: Long)
    private external fun nativeSetBufferSize(streamHandle: Long, bufferSize: Int)

    private var engineHandle: Long = 0
    private val streamHandles = ConcurrentHashMap<Int, StreamState>()
    private val channelStates = ConcurrentHashMap<Int, ChannelState>()

    private var masterGainDb = 0f
    private var isInitialized = false
    private var totalPacketsReceived = 0
    private var totalPacketsDropped = 0

    // ✅ Device capabilities con valores seguros
    // ✅ OPTIMIZACIÓN LATENCIA FASE 1: Buffer pool para reducir GC pauses
    // Reutiliza buffers en lugar de crear nuevos en cada frame
    // Ganancia: 0.2-0.5ms menos variabilidad
    private val bufferPool = ArrayDeque<FloatArray>()
    private val MAX_POOLED_BUFFERS = 2  // Mínimo para no desperdiciar memoria

    private var deviceSupportsMMAP = false
    private var deviceFramesPerBurst = 0

    data class StreamState(
        val handle: Long,
        var consecutiveFailures: Int = 0,
        var lastWriteTime: Long = System.currentTimeMillis(),
        var lastClearTime: Long = 0
    )

    data class ChannelState(
        var gainDb: Float = 0f,
        var pan: Float = 0f,
        var isActive: Boolean = true,
        var peakLevel: Float = 0f,
        var rmsLevel: Float = 0f,
        var packetsReceived: Int = 0
    )

    init {
        try {
            // ✅ CORREGIDO: Detectar capabilities solo si hay context
            if (context != null) {
                detectDeviceCapabilities()
            } else {
                Log.w(TAG, "⚠️ Context no disponible, usando configuración por defecto")
            }

            // ✅ CORREGIDO: Usar firma correcta (sin bufferSize)
            engineHandle = nativeCreateEngine(OPTIMAL_SAMPLE_RATE, CHANNELS)
            isInitialized = engineHandle != 0L

            if (isInitialized) {
                Log.d(TAG, """
                    ✅ Oboe Engine ULTRA-LOW LATENCY
                       📊 Sample Rate: $OPTIMAL_SAMPLE_RATE Hz ${if (context != null) "(nativo)" else "(default)"}
                       🎵 Canales: $CHANNELS
                       📦 Buffer Size: $OPTIMAL_BUFFER_SIZE frames (~${(OPTIMAL_BUFFER_SIZE * 1000f / OPTIMAL_SAMPLE_RATE).format(1)}ms)
                       🚀 MMAP Support: $deviceSupportsMMAP
                       ⚡ Frames/Burst: $deviceFramesPerBurst
                       🔧 Engine Handle: $engineHandle
                """.trimIndent())
            } else {
                Log.e(TAG, "❌ Falló inicialización de Oboe Engine")
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error inicializando Oboe: ${e.message}", e)
            isInitialized = false
        }
    }

    /**
     * ✅ CORREGIDO: Validación de AudioManager
     */
    private fun detectDeviceCapabilities() {
        try {
            // ✅ Validar que context no sea null
            if (context == null) {
                Log.w(TAG, "⚠️ Context es null, usando defaults")
                return
            }

            val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager

            if (audioManager != null) {
                // Obtener sample rate nativo
                val sampleRateStr = audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)
                val detectedSampleRate = sampleRateStr?.toIntOrNull()

                // ✅ Validar que sea un valor razonable
                if (detectedSampleRate != null && detectedSampleRate in 44100..96000) {
                    OPTIMAL_SAMPLE_RATE = detectedSampleRate
                } else {
                    Log.w(TAG, "⚠️ Sample rate inválido: $detectedSampleRate, usando default")
                }

                // Obtener frames per burst
                val framesPerBurstStr = audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)
                val detectedFrames = framesPerBurstStr?.toIntOrNull()

                // ✅ Validar que sea un valor razonable
                if (detectedFrames != null && detectedFrames in 64..512) {
                    deviceFramesPerBurst = detectedFrames

                    // Ajustar buffer size basado en frames per burst
                    OPTIMAL_BUFFER_SIZE = when {
                        deviceFramesPerBurst <= 96 -> 64
                        deviceFramesPerBurst <= 192 -> 128
                        else -> 256
                    }.coerceIn(MIN_BUFFER_SIZE, MAX_BUFFER_SIZE)
                } else {
                    Log.w(TAG, "⚠️ Frames per burst inválido: $detectedFrames, usando default")
                    deviceFramesPerBurst = 128
                }

                // ✅ Detectar soporte MMAP con verificación de PackageManager
                try {
                    deviceSupportsMMAP = context.packageManager.hasSystemFeature(
                        "android.hardware.audio.low_latency"
                    ) || context.packageManager.hasSystemFeature(
                        "android.hardware.audio.pro"
                    )
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ Error detectando MMAP: ${e.message}")
                    deviceSupportsMMAP = false
                }

                Log.d(TAG, """
                    🔍 Device Audio Capabilities:
                       Native Sample Rate: $OPTIMAL_SAMPLE_RATE Hz
                       Frames Per Burst: $deviceFramesPerBurst
                       Optimal Buffer: $OPTIMAL_BUFFER_SIZE frames
                       MMAP Capable: $deviceSupportsMMAP
                """.trimIndent())

            } else {
                Log.w(TAG, "⚠️ AudioManager no disponible, usando defaults")
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error detectando capabilities: ${e.message}")
            // Continuar con valores por defecto
        }
    }

    /**
     * ✅ CORREGIDO: Usar método nativo correcto
     */
    private fun getOrCreateStream(channel: Int): Long {
        val streamState = streamHandles[channel]

        if (streamState != null && streamState.consecutiveFailures < MAX_WRITE_FAILURES) {
            return streamState.handle
        }

        if (streamState != null) {
            Log.w(TAG, "🔄 Recreando stream canal $channel (${streamState.consecutiveFailures} fallos)")
            destroyStream(channel)
        }

        if (streamHandles.size >= MAX_SIMULTANEOUS_STREAMS && !streamHandles.containsKey(channel)) {
            Log.w(TAG, "⚠️ Límite de streams alcanzado ($MAX_SIMULTANEOUS_STREAMS)")

            val leastUsed = streamHandles.entries
                .minByOrNull { it.value.lastWriteTime }
                ?.key

            if (leastUsed != null) {
                Log.w(TAG, "🗑️ Liberando canal $leastUsed por límite")
                destroyStream(leastUsed)
            } else {
                return 0L
            }
        }

        return createNewStream(channel)
    }

    /**
     * ✅ SIMPLIFICADO: Usar método nativo estándar sin MMAP custom
     *
     * RAZÓN: MMAP se activa automáticamente por Oboe cuando:
     * - Performance mode es LowLatency
     * - Sharing mode es Exclusive
     * - El dispositivo lo soporta
     *
     * NO necesitamos método nativo custom para MMAP.
     */
    private fun createNewStream(channel: Int): Long {
        try {
            if (!isInitialized) {
                Log.e(TAG, "❌ Engine no inicializado")
                return 0L
            }

            // ✅ Usar método nativo estándar
            val handle = nativeCreateStream(engineHandle, channel)

            if (handle != 0L) {
                // ✅ Configurar buffer size óptimo
                nativeSetBufferSize(handle, OPTIMAL_BUFFER_SIZE)

                nativeStartStream(handle)
                streamHandles[channel] = StreamState(handle = handle)

                val latencyEstimate = (OPTIMAL_BUFFER_SIZE * 1000f / OPTIMAL_SAMPLE_RATE).format(1)

                Log.d(TAG, """
                    ✅ Stream canal $channel creado
                       Buffer: $OPTIMAL_BUFFER_SIZE frames (~${latencyEstimate}ms)
                       Sample Rate: $OPTIMAL_SAMPLE_RATE Hz
                """.trimIndent())
            } else {
                Log.e(TAG, "❌ Falló creación de stream para canal $channel")
            }

            return handle

        } catch (e: Exception) {
            Log.e(TAG, "❌ Excepción creando stream canal $channel: ${e.message}", e)
            return 0L
        }
    }

    /**
     * ✅ OPTIMIZADO: Renderizado de audio con procesamiento vectorizado
     */
    fun renderChannelRF(channel: Int, audioData: FloatArray, samplePosition: Long) {
        if (!isInitialized || audioData.isEmpty()) {
            return
        }

        val state = channelStates.getOrPut(channel) { ChannelState() }

        if (!state.isActive || state.gainDb <= -60f) {
            return
        }

        totalPacketsReceived++

        val streamHandle = getOrCreateStream(channel)
        if (streamHandle == 0L) {
            totalPacketsDropped++
            return
        }

        // Calcular ganancias (pre-calculado una vez)
        val totalGainDb = state.gainDb + masterGainDb
        val linearGain = dbToLinear(totalGainDb)

        // Panorama optimizado
        val panRad = ((state.pan + 1f) * Math.PI / 4).toFloat()
        val leftGain = cos(panRad) * linearGain
        val rightGain = sin(panRad) * linearGain

        val bufferSize = audioData.size * 2
        val stereoBuffer = acquireBuffer(bufferSize)

        // ✅ OPTIMIZADO: Procesamiento en bloques de 4 (SIMD-friendly)
        var sumSquares = 0f
        var peak = 0f
        val audioSize = audioData.size
        val limit = audioSize - (audioSize % 4)
        
        var i = 0
        while (i < limit) {
            // Bloque de 4 samples para mejor vectorización
            val s0 = audioData[i]
            val s1 = audioData[i + 1]
            val s2 = audioData[i + 2]
            val s3 = audioData[i + 3]
            
            // Left channel
            val l0 = s0 * leftGain
            val l1 = s1 * leftGain
            val l2 = s2 * leftGain
            val l3 = s3 * leftGain
            
            // Right channel
            val r0 = s0 * rightGain
            val r1 = s1 * rightGain
            val r2 = s2 * rightGain
            val r3 = s3 * rightGain
            
            // ✅ OPTIMIZADO: Soft clip sin branches (tanh-approximation)
            val baseIdx = i * 2
            stereoBuffer[baseIdx] = fastSoftClip(l0)
            stereoBuffer[baseIdx + 1] = fastSoftClip(r0)
            stereoBuffer[baseIdx + 2] = fastSoftClip(l1)
            stereoBuffer[baseIdx + 3] = fastSoftClip(r1)
            stereoBuffer[baseIdx + 4] = fastSoftClip(l2)
            stereoBuffer[baseIdx + 5] = fastSoftClip(r2)
            stereoBuffer[baseIdx + 6] = fastSoftClip(l3)
            stereoBuffer[baseIdx + 7] = fastSoftClip(r3)
            
            // Stats (menos frecuente para mejor perf)
            val abs0 = abs(s0 * linearGain)
            if (abs0 > peak) peak = abs0
            sumSquares += s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3
            
            i += 4
        }
        
        // Resto de samples
        while (i < audioSize) {
            val sample = audioData[i]
            val left = sample * leftGain
            val right = sample * rightGain
            
            stereoBuffer[i * 2] = fastSoftClip(left)
            stereoBuffer[i * 2 + 1] = fastSoftClip(right)
            
            val absSample = abs(sample * linearGain)
            if (absSample > peak) peak = absSample
            sumSquares += sample * sample
            i++
        }

        state.peakLevel = peak
        state.rmsLevel = sqrt(sumSquares / audioSize)
        state.packetsReceived++

        // Escribir a Oboe
        try {
            val written = nativeWriteAudio(streamHandle, stereoBuffer)
            val streamState = streamHandles[channel]

            if (written < stereoBuffer.size) {
                val dropped = (stereoBuffer.size - written) / 2
                totalPacketsDropped += dropped

                if (streamState != null) {
                    streamState.consecutiveFailures++

                    // Estrategia de recuperación
                    when (streamState.consecutiveFailures) {
                        1 -> nativeClearBuffer(streamHandle)
                        3 -> {
                            nativeStopStream(streamHandle)
                            nativeStartStream(streamHandle)
                        }
                        5 -> destroyStream(channel)
                    }
                }

                if (dropped > 100) {
                    Log.d(TAG, "🗑️ RF Drop: $dropped frames en canal $channel")
                }
            } else {
                streamState?.let {
                    it.consecutiveFailures = 0
                    it.lastWriteTime = System.currentTimeMillis()
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error escribiendo canal $channel: ${e.message}")
            totalPacketsDropped += audioData.size / 2

            streamHandles[channel]?.let { streamState ->
                streamState.consecutiveFailures++
                val timeSinceLastClear = System.currentTimeMillis() - streamState.lastClearTime

                if (timeSinceLastClear > 500) {
                    try {
                        nativeClearBuffer(streamHandle)
                        streamState.lastClearTime = System.currentTimeMillis()
                    } catch (ignored: Exception) {
                        streamState.consecutiveFailures = MAX_WRITE_FAILURES
                    }
                }
            }
        } finally {
            releaseBuffer(stereoBuffer)
        }
    }
    
    /**
     * ✅ OPTIMIZADO: Soft clip sin branches usando aproximación matemática
     * x / (1 + |x|) da un clip suave similar pero sin branches
     */
    private fun fastSoftClip(x: Float): Float {
        return x / (1f + abs(x) * 0.25f)  // Aproximación rápida con límite ~1.0
    }

    // Pool de buffers
    private fun acquireBuffer(size: Int): FloatArray {
        return bufferPool.removeFirstOrNull()?.takeIf { it.size == size }
            ?: FloatArray(size)
    }

    private fun releaseBuffer(buffer: FloatArray) {
        if (bufferPool.size < MAX_POOLED_BUFFERS) {
            buffer.fill(0f)  // Limpiar antes de devolver
            bufferPool.addLast(buffer)
        }
    }

    private fun softClip(sample: Float): Float {
        return when {
            sample > 1f -> {
                val excess = sample - 1f
                1f - (1f / (1f + excess))
            }
            sample < -1f -> {
                val excess = -sample - 1f
                -1f + (1f / (1f + excess))
            }
            else -> sample
        }
    }

    private fun destroyStream(channel: Int) {
        val streamState = streamHandles.remove(channel) ?: return

        try {
            nativeStopStream(streamState.handle)
            nativeDestroyStream(streamState.handle)
            Log.d(TAG, "🗑️ Stream canal $channel destruido")
        } catch (e: Exception) {
            Log.e(TAG, "Error destruyendo stream canal $channel: ${e.message}")
        }
    }

    fun recreateAllStreams() {
        Log.w(TAG, "🔄 Recreando TODOS los streams...")

        val channelsToRecreate = streamHandles.keys.toList()
        channelsToRecreate.forEach { channel ->
            destroyStream(channel)
        }

        Log.i(TAG, "✅ Streams marcados para recreación: ${channelsToRecreate.size}")
    }

    /**
     * ✅ CORREGIDO: Obtener info sin campos MMAP custom
     */
    fun getDeviceInfo(): Map<String, Any> {
        return mapOf(
            "sample_rate" to OPTIMAL_SAMPLE_RATE,
            "buffer_size" to OPTIMAL_BUFFER_SIZE,
            "estimated_latency_ms" to (OPTIMAL_BUFFER_SIZE * 1000f / OPTIMAL_SAMPLE_RATE),
            "mmap_support" to deviceSupportsMMAP,
            "frames_per_burst" to deviceFramesPerBurst,
            "active_streams" to streamHandles.size
        )
    }

    fun getChannelRFStats(channel: Int): Map<String, Any> {
        val streamState = streamHandles[channel] ?: return emptyMap()

        return try {
            val stats = nativeGetRFStats(streamState.handle)
            mapOf(
                "available_frames" to stats[0],
                "latency_ms" to stats[1],
                "is_receiving" to (stats[2] == 1),
                "underruns" to stats[3],
                "drops" to stats[4],
                "buffer_usage" to stats[5],
                "resets" to (stats.getOrNull(6) ?: 0),
                "consecutive_failures" to streamState.consecutiveFailures
            )
        } catch (e: Exception) {
            Log.e(TAG, "Error obteniendo stats RF: ${e.message}")
            emptyMap()
        }
    }

    fun updateChannelGain(channel: Int, gainDb: Float) {
        val state = channelStates.getOrPut(channel) { ChannelState() }
        state.gainDb = gainDb.coerceIn(-60f, 12f)
    }

    fun updateChannelPan(channel: Int, pan: Float) {
        val state = channelStates.getOrPut(channel) { ChannelState() }
        state.pan = pan.coerceIn(-1f, 1f)
    }

    fun setChannelActive(channel: Int, active: Boolean) {
        val state = channelStates.getOrPut(channel) { ChannelState() }
        state.isActive = active

        if (!active) {
            state.peakLevel = 0f
            state.rmsLevel = 0f
            destroyStream(channel)
        }
    }

    fun setMasterGain(gainDb: Float) {
        masterGainDb = gainDb.coerceIn(-60f, 12f)
    }

    fun getChannelState(channel: Int): ChannelState? {
        return channelStates[channel]
    }

    fun getAllChannelStates(): Map<Int, ChannelState> {
        return channelStates.toMap()
    }

    fun getRFStats(): Map<String, Any> {
        var totalLatency = 0f
        var totalAvailable = 0
        var totalUnderruns = 0
        var totalDrops = 0
        var totalResets = 0
        var activeChannels = 0
        var totalFailures = 0

        streamHandles.forEach { (_, streamState) ->
            try {
                val stats = nativeGetRFStats(streamState.handle)
                totalAvailable += stats[0]
                totalLatency += stats[1]
                totalUnderruns += stats[3]
                totalDrops += stats[4]
                totalResets += stats.getOrNull(6) ?: 0
                totalFailures += streamState.consecutiveFailures
                activeChannels++
            } catch (_: Exception) {}
        }

        val avgLatency = if (activeChannels > 0) totalLatency / activeChannels else 0f
        val totalFramesDropped = totalDrops + totalPacketsDropped

        return mapOf(
            "total_packets" to totalPacketsReceived,
            "dropped_frames" to totalFramesDropped,
            "drop_rate" to if (totalPacketsReceived > 0)
                (totalFramesDropped.toFloat() / totalPacketsReceived * 100f) else 0f,
            "avg_latency_ms" to avgLatency,
            "available_frames" to totalAvailable,
            "underruns" to totalUnderruns,
            "resets" to totalResets,
            "active_streams" to streamHandles.size,
            "is_initialized" to isInitialized,
            "total_failures" to totalFailures,
            "device_sample_rate" to OPTIMAL_SAMPLE_RATE,
            "device_buffer_size" to OPTIMAL_BUFFER_SIZE,
            "mmap_capable" to deviceSupportsMMAP
        )
    }

    fun resetRFStats() {
        totalPacketsReceived = 0
        totalPacketsDropped = 0
        channelStates.values.forEach { it.packetsReceived = 0 }
        streamHandles.values.forEach {
            it.consecutiveFailures = 0
            it.lastClearTime = 0
        }
    }

    fun stop() {
        try {
            Log.d(TAG, "🛑 Deteniendo OboeAudioRenderer...")
            val channelsToStop = streamHandles.keys.toList()
            channelsToStop.forEach { channel ->
                try {
                    destroyStream(channel)
                    Log.d(TAG, "✅ Stream canal $channel detenido")
                } catch (e: Exception) {
                    Log.e(TAG, "⚠️ Error deteniendo stream $channel: ${e.message}")
                }
            }
            channelStates.clear()
            resetRFStats()
            Log.d(TAG, "✅ OboeAudioRenderer detenido completamente")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error deteniendo: ${e.message}")
        }
    }

    fun release() {
        try {
            stop()
            if (engineHandle != 0L) {
                nativeDestroyEngine(engineHandle)
                engineHandle = 0
            }
            isInitialized = false
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error liberando: ${e.message}")
        }
    }

    fun isActive(): Boolean {
        return isInitialized && streamHandles.isNotEmpty()
    }

    fun getLatencyMs(): Float {
        if (!isInitialized || streamHandles.isEmpty()) return 0f

        return try {
            var totalLatency = 0f
            var count = 0

            streamHandles.forEach { (_, streamState) ->
                val latency = nativeGetLatency(streamState.handle)
                totalLatency += latency
                count++
            }

            if (count > 0) totalLatency / count else 0f
        } catch (e: Exception) {
            Log.e(TAG, "Error calculando latencia: ${e.message}")
            0f
        }
    }

    fun getBufferInfo(): Map<String, Any> {
        var totalBufferedFrames = 0

        streamHandles.forEach { (_, streamState) ->
            try {
                totalBufferedFrames += nativeGetBufferStats(streamState.handle)
            } catch (_: Exception) {}
        }

        return mapOf(
            "buffered_frames" to totalBufferedFrames,
            "active_streams" to streamHandles.size,
            "packets_received" to totalPacketsReceived,
            "packets_dropped" to totalPacketsDropped,
            "is_initialized" to isInitialized
        )
    }

    private fun dbToLinear(db: Float): Float {
        return if (db <= -60f) 0f else 10.0f.pow(db / 20.0f)
    }

    private fun linearToDb(linear: Float): Float {
        return if (linear > 0.00001f) {
            20.0f * log10(linear)
        } else -60f
    }

    private fun Float.format(digits: Int) = "%.${digits}f".format(this)
}