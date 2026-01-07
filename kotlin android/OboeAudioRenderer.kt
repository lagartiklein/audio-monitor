package com.cepalabsfree.fichatech.audiostream

import android.content.Context
import android.media.AudioManager
import android.util.Log
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.*

class OboeAudioRenderer(private val context: Context? = null) {
    companion object {
        private const val TAG = "OboeAudioRenderer"
        private const val RENDER_STEREO_CHANNEL = 0 // Canal dedicado para render principal

        // ✅ Variables mutables con valores por defecto seguros
        private var OPTIMAL_SAMPLE_RATE = 48000

        private const val CHANNELS = 2
        private const val MAX_WRITE_FAILURES = 2
        private const val MAX_SIMULTANEOUS_STREAMS = 48

        // ✅ OPTIMIZACIÓN LATENCIA: preferimos buffers pequeños, pero alineados a framesPerBurst del dispositivo
        private var OPTIMAL_BUFFER_SIZE = 64 // se recalcula con detectDeviceCapabilities()
        private const val MIN_BUFFER_SIZE = 64
        private const val MAX_BUFFER_SIZE = 128

        init {
            try {
                System.loadLibrary("fichatech_audio")
                Log.d(TAG, "✅ Biblioteca nativa Oboe cargada")
                Log.d(TAG, "   🎯 Buffer inicial: ${OPTIMAL_BUFFER_SIZE} frames")
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

    // ✅ Deduplicación mínima por canal para evitar audio “doblado” por duplicados de red/hilos.
    private val lastRenderedSamplePosition = ConcurrentHashMap<Int, Long>()

    // ✅ Pool de buffers por tamaño: evita GC/jitter.
    // Importante: NO hacemos fill(0f) en release: siempre sobrescribimos todo el buffer al renderizar.
    private val bufferPoolsBySize = ConcurrentHashMap<Int, ArrayDeque<FloatArray>>()
    private val maxPooledBuffersPerSize = 2

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
            if (context != null) {
                detectDeviceCapabilities()
            } else {
                Log.w(TAG, "⚠️ Context no disponible, usando configuración por defecto")
            }

            engineHandle = nativeCreateEngine(OPTIMAL_SAMPLE_RATE, CHANNELS)
            isInitialized = engineHandle != 0L

            if (isInitialized) {
                Log.d(
                    TAG,
                    """
                    ✅ Oboe Engine ULTRA-LOW LATENCY
                       📊 Sample Rate: $OPTIMAL_SAMPLE_RATE Hz ${if (context != null) "(nativo)" else "(default)"}
                       🎵 Canales: $CHANNELS
                       📦 Buffer Size: $OPTIMAL_BUFFER_SIZE frames (~${(OPTIMAL_BUFFER_SIZE * 1000f / OPTIMAL_SAMPLE_RATE).format(1)}ms)
                       🚀 MMAP Support (heurístico): $deviceSupportsMMAP
                       ⚡ Frames/Burst: $deviceFramesPerBurst
                       🔧 Engine Handle: $engineHandle
                """.trimIndent()
                )
            } else {
                Log.e(TAG, "❌ Falló inicialización de Oboe Engine")
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error inicializando Oboe: ${e.message}", e)
            isInitialized = false
        }
    }

    private fun detectDeviceCapabilities() {
        try {
            if (context == null) return

            val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            if (audioManager != null) {
                audioManager
                    .getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)
                    ?.toIntOrNull()
                    ?.let { if (it in 44100..96000) OPTIMAL_SAMPLE_RATE = it }

                audioManager
                    .getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)
                    ?.toIntOrNull()
                    ?.let { frames ->
                        if (frames in 32..1024) {
                            deviceFramesPerBurst = frames
                            // ✅ Mejor para latencia: alinear a framesPerBurst (AAudio/Oboe suele trabajar por burst)
                            OPTIMAL_BUFFER_SIZE = frames.coerceIn(MIN_BUFFER_SIZE, MAX_BUFFER_SIZE)
                        }
                    }

                deviceSupportsMMAP =
                    context.packageManager.hasSystemFeature("android.hardware.audio.low_latency") ||
                        context.packageManager.hasSystemFeature("android.hardware.audio.pro")

                Log.d(
                    TAG,
                    "🔍 Audio: $OPTIMAL_SAMPLE_RATE Hz, buffer=${OPTIMAL_BUFFER_SIZE}f, framesPerBurst=$deviceFramesPerBurst, lowLatencyFeature=$deviceSupportsMMAP"
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error detectando capabilities: ${e.message}")
        }
    }

    /** ✅ CORREGIDO: Usar método nativo correcto */
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

            val leastUsed = streamHandles.entries.minByOrNull { it.value.lastWriteTime }?.key

            if (leastUsed != null) {
                Log.w(TAG, "🗑️ Liberando canal $leastUsed por límite")
                destroyStream(leastUsed)
            } else {
                return 0L
            }
        }

        return createNewStream(channel)
    }

    private fun createNewStream(channel: Int): Long {
        try {
            if (!isInitialized) {
                Log.e(TAG, "❌ Engine no inicializado")
                return 0L
            }

            val handle = nativeCreateStream(engineHandle, channel)

            if (handle != 0L) {
                // ✅ Configurar buffer size óptimo (alineado a framesPerBurst si existe)
                nativeSetBufferSize(handle, OPTIMAL_BUFFER_SIZE)

                nativeStartStream(handle)
                streamHandles[channel] = StreamState(handle = handle)

                val latencyEstimate = (OPTIMAL_BUFFER_SIZE * 1000f / OPTIMAL_SAMPLE_RATE).format(1)

                Log.d(
                    TAG,
                    """
                    ✅ Stream canal $channel creado
                       Buffer: $OPTIMAL_BUFFER_SIZE frames (~${latencyEstimate}ms)
                       Sample Rate: $OPTIMAL_SAMPLE_RATE Hz
                """.trimIndent()
                )
            } else {
                Log.e(TAG, "❌ Falló creación de stream para canal $channel")
            }

            return handle
        } catch (e: Exception) {
            Log.e(TAG, "❌ Excepción creando stream canal $channel: ${e.message}", e)
            return 0L
        }
    }

    // Render principal: MONO (N) -> estéreo interleaved (2N)
    fun renderStereo(audioData: FloatArray, samplePosition: Long) {
        if (!isInitialized || audioData.isEmpty()) return

        val lastPos = lastRenderedSamplePosition[RENDER_STEREO_CHANNEL]
        if (lastPos != null && samplePosition == lastPos) return
        lastRenderedSamplePosition[RENDER_STEREO_CHANNEL] = samplePosition

        val state = channelStates.getOrPut(RENDER_STEREO_CHANNEL) { ChannelState() }
        if (!state.isActive || state.gainDb <= -60f) return

        totalPacketsReceived++

        val streamHandle = getOrCreateStream(RENDER_STEREO_CHANNEL)
        if (streamHandle == 0L) {
            totalPacketsDropped++
            return
        }

        val totalGainDb = state.gainDb + masterGainDb
        val linearGain = dbToLinear(totalGainDb)
        val leftGain = linearGain
        val rightGain = linearGain

        val outSize = audioData.size * 2
        val stereoBuffer = acquireBuffer(outSize)

        var sumSquares = 0f
        var peak = 0f

        for (i in audioData.indices) {
            val sample = audioData[i]
            val l = sample * leftGain
            val r = sample * rightGain
            stereoBuffer[i * 2] = softClip(l)
            stereoBuffer[i * 2 + 1] = softClip(r)

            val absSample = abs(sample * linearGain)
            if (absSample > peak) peak = absSample
            sumSquares += sample * sample
        }

        state.peakLevel = peak
        state.rmsLevel = sqrt(sumSquares / audioData.size)
        state.packetsReceived++

        try {
            val written = nativeWriteAudio(streamHandle, stereoBuffer)
            val streamState = streamHandles[RENDER_STEREO_CHANNEL]

            if (written < stereoBuffer.size) {
                val dropped = (stereoBuffer.size - written) / 2
                totalPacketsDropped += dropped

                if (streamState != null) {
                    streamState.consecutiveFailures++
                    if (streamState.consecutiveFailures == 1) {
                        nativeClearBuffer(streamHandle)
                    } else if (streamState.consecutiveFailures == 3) {
                        nativeStopStream(streamHandle)
                        nativeStartStream(streamHandle)
                    } else if (streamState.consecutiveFailures >= 5) {
                        destroyStream(RENDER_STEREO_CHANNEL)
                    }
                }

                if (dropped > 100) {
                    Log.d(TAG, "🗑️ Drop: $dropped frames en render estéreo principal")
                }
            } else {
                if (streamState != null) {
                    streamState.consecutiveFailures = 0
                    streamState.lastWriteTime = System.currentTimeMillis()
                }
            }
        } finally {
            releaseBuffer(outSize, stereoBuffer)
        }
    }

    /** ✅ NUEVO: Renderiza audio MONO y lo convierte a estéreo */
    fun renderChannelRF(channel: Int, audioData: FloatArray, samplePosition: Long) {
        if (channel == RENDER_STEREO_CHANNEL) return
        if (!isInitialized || audioData.isEmpty()) return

        val lastPos = lastRenderedSamplePosition[channel]
        if (lastPos != null && samplePosition == lastPos) return
        lastRenderedSamplePosition[channel] = samplePosition

        val state = channelStates.getOrPut(channel) { ChannelState() }
        if (!state.isActive || state.gainDb <= -60f) return

        totalPacketsReceived++

        val streamHandle = getOrCreateStream(channel)
        if (streamHandle == 0L) {
            totalPacketsDropped++
            return
        }

        val totalGainDb = state.gainDb + masterGainDb
        val linearGain = dbToLinear(totalGainDb)

        val panRad = ((state.pan + 1f) * Math.PI / 4).toFloat()
        val leftGain = cos(panRad) * linearGain
        val rightGain = sin(panRad) * linearGain

        val outSize = audioData.size * 2
        val stereoBuffer = acquireBuffer(outSize)

        var sumSquares = 0f
        var peak = 0f

        for (i in audioData.indices) {
            val sample = audioData[i]
            val l = sample * leftGain
            val r = sample * rightGain

            stereoBuffer[i * 2] = softClip(l)
            stereoBuffer[i * 2 + 1] = softClip(r)

            val absSample = abs(sample * linearGain)
            if (absSample > peak) peak = absSample
            sumSquares += sample * sample
        }

        state.peakLevel = peak
        state.rmsLevel = sqrt(sumSquares / audioData.size)
        state.packetsReceived++

        try {
            val written = nativeWriteAudio(streamHandle, stereoBuffer)
            val streamState = streamHandles[channel]

            if (written < stereoBuffer.size) {
                val dropped = (stereoBuffer.size - written) / 2
                totalPacketsDropped += dropped

                if (streamState != null) {
                    streamState.consecutiveFailures++
                    if (streamState.consecutiveFailures == 1) {
                        nativeClearBuffer(streamHandle)
                    } else if (streamState.consecutiveFailures == 3) {
                        nativeStopStream(streamHandle)
                        nativeStartStream(streamHandle)
                    } else if (streamState.consecutiveFailures >= 5) {
                        destroyStream(channel)
                    }
                }

                if (dropped > 100) {
                    Log.d(TAG, "🗑️ RF Drop: $dropped frames en canal $channel")
                }
            } else {
                if (streamState != null) {
                    streamState.consecutiveFailures = 0
                    streamState.lastWriteTime = System.currentTimeMillis()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error escribiendo canal $channel: ${e.message}")
            totalPacketsDropped += audioData.size / 2

            val streamState = streamHandles[channel]
            if (streamState != null) {
                streamState.consecutiveFailures++
                val timeSinceLastClear = System.currentTimeMillis() - streamState.lastClearTime

                if (timeSinceLastClear > 500) {
                    try {
                        nativeClearBuffer(streamHandle)
                        streamState.lastClearTime = System.currentTimeMillis()
                    } catch (_: Exception) {
                        streamState.consecutiveFailures = MAX_WRITE_FAILURES
                    }
                }
            }
        } finally {
            releaseBuffer(outSize, stereoBuffer)
        }
    }

    private fun acquireBuffer(size: Int): FloatArray {
        val q = bufferPoolsBySize.getOrPut(size) { ArrayDeque() }
        return q.removeFirstOrNull() ?: FloatArray(size)
    }

    private fun releaseBuffer(size: Int, buffer: FloatArray) {
        val q = bufferPoolsBySize.getOrPut(size) { ArrayDeque() }
        if (q.size < maxPooledBuffersPerSize) {
            q.addLast(buffer)
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
        channelsToRecreate.forEach { channel -> destroyStream(channel) }

        Log.i(TAG, "✅ Streams marcados para recreación: ${channelsToRecreate.size}")
    }

    /** ✅ CORREGIDO: Obtener info sin campos MMAP custom */
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
            "drop_rate" to
                    if (totalPacketsReceived > 0)
                        (totalFramesDropped.toFloat() / totalPacketsReceived * 100f)
                    else 0f,
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
        // ✅ También resetear dedup para no bloquear el primer paquete tras reset
        lastRenderedSamplePosition.clear()
    }

    fun stop() {
        try {
            Log.d(TAG, "🛑 Deteniendo OboeAudioRenderer...")
            streamHandles.keys.forEach { channel -> destroyStream(channel) }
            channelStates.clear()
            resetRFStats()
            Log.d(TAG, "✅ OboeAudioRenderer detenido")
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

    private fun dbToLinear(db: Float): Float = 10.0f.pow(db / 20.0f)
    private fun linearToDb(linear: Float): Float = if (linear > 0) 20.0f * log10(linear) else -60f
    private fun Float.format(digits: Int) = "%.${digits}f".format(this)
}
