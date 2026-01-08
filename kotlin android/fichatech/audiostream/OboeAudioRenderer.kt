package com.cepalabsfree.fichatech.audiostream

import android.content.Context
import android.media.AudioManager
import android.os.PowerManager
import android.util.Log
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.*

/**
 * ✅ ULTRA-OPTIMIZADO: Sin funciones obsoletas de C++
 * - Eliminadas todas las llamadas a nativeGetRFStats (no existe)
 * - Stats simplificados solo con funciones disponibles
 * - Reducción de overhead en callbacks
 * - Pool de buffers optimizado
 */
class OboeAudioRenderer(private val context: Context? = null) {
    companion object {
        private const val TAG = "OboeAudioRenderer"
        private const val RENDER_STEREO_CHANNEL = 0

        private var OPTIMAL_SAMPLE_RATE = 48000
        private const val CHANNELS = 2
        private const val MAX_WRITE_FAILURES = 2
        private const val MAX_SIMULTANEOUS_STREAMS = 32

        private var OPTIMAL_BUFFER_SIZE = 64
        private const val MIN_BUFFER_SIZE = 32
        private const val MAX_BUFFER_SIZE = 512

        init {
            try {
                System.loadLibrary("fichatech_audio")
                Log.d(TAG, "✅ Biblioteca nativa Oboe cargada")
            } catch (e: UnsatisfiedLinkError) {
                Log.e(TAG, "❌ Error cargando biblioteca nativa: ${e.message}", e)
            }
        }
    }

    // ✅ SOLO las funciones JNI que EXISTEN en C++
    private external fun nativeCreateEngine(sampleRate: Int, channels: Int): Long
    private external fun nativeCreateStream(engineHandle: Long, channelId: Int): Long
    private external fun nativeWriteAudio(streamHandle: Long, buffer: FloatArray): Int
    private external fun nativeStartStream(streamHandle: Long)
    private external fun nativeStopStream(streamHandle: Long)
    private external fun nativeGetLatency(streamHandle: Long): Float
    private external fun nativeGetBufferStats(streamHandle: Long): Int
    private external fun nativeClearBuffer(streamHandle: Long)
    private external fun nativeDestroyStream(streamHandle: Long)
    private external fun nativeDestroyEngine(engineHandle: Long)
    private external fun nativeSetBufferSize(streamHandle: Long, bufferSize: Int)

    private var engineHandle: Long = 0
    private val streamHandles = ConcurrentHashMap<Int, StreamState>()
    private val channelStates = ConcurrentHashMap<Int, ChannelState>()

    private var partialWakeLock: PowerManager.WakeLock? = null
    private var masterGainDb = 0f
    private var isInitialized = false

    // ✅ Tracking mínimo
    private val lastRenderedSamplePosition = ConcurrentHashMap<Int, Long>()

    // ✅ Pool de buffers optimizado
    private val bufferPoolsBySize = ConcurrentHashMap<Int, ArrayDeque<FloatArray>>()
    private val maxPooledBuffersPerSize = 4

    private var deviceSupportsMMAP = false
    private var deviceFramesPerBurst = 0

    data class StreamState(
        val handle: Long,
        var consecutiveFailures: Int = 0,
        var lastWriteTime: Long = System.currentTimeMillis()
    )

    data class ChannelState(
        var gainDb: Float = 0f,
        var pan: Float = 0f,
        var isActive: Boolean = true
    )

    init {
        try {
            if (context != null) {
                detectDeviceCapabilities()
            }

            engineHandle = nativeCreateEngine(OPTIMAL_SAMPLE_RATE, CHANNELS)
            isInitialized = engineHandle != 0L

            if (isInitialized) {
                Log.d(TAG, """
                    ✅ Oboe Engine ULTRA-LOW LATENCY
                       📊 Sample Rate: $OPTIMAL_SAMPLE_RATE Hz
                       🎵 Canales: $CHANNELS
                       📦 Buffer: $OPTIMAL_BUFFER_SIZE frames (~${(OPTIMAL_BUFFER_SIZE * 1000f / OPTIMAL_SAMPLE_RATE).format(1)}ms)
                       🚀 MMAP: $deviceSupportsMMAP
                """.trimIndent())
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
                            OPTIMAL_BUFFER_SIZE = frames.coerceIn(MIN_BUFFER_SIZE, MAX_BUFFER_SIZE)
                        }
                    }

                deviceSupportsMMAP =
                    context.packageManager.hasSystemFeature("android.hardware.audio.low_latency")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error detectando capabilities: ${e.message}")
        }
    }

    private fun getOrCreateStream(channel: Int): Long {
        val streamState = streamHandles[channel]

        if (streamState != null && streamState.consecutiveFailures < MAX_WRITE_FAILURES) {
            return streamState.handle
        }

        if (streamState != null) {
            destroyStream(channel)
        }

        if (streamHandles.size >= MAX_SIMULTANEOUS_STREAMS && !streamHandles.containsKey(channel)) {
            val leastUsed = streamHandles.entries.minByOrNull { it.value.lastWriteTime }?.key
            if (leastUsed != null) {
                destroyStream(leastUsed)
            } else {
                return 0L
            }
        }

        return createNewStream(channel)
    }

    private fun createNewStream(channel: Int): Long {
        try {
            if (!isInitialized) return 0L

            val handle = nativeCreateStream(engineHandle, channel)

            if (handle != 0L) {
                nativeSetBufferSize(handle, OPTIMAL_BUFFER_SIZE)
                nativeStartStream(handle)
                streamHandles[channel] = StreamState(handle = handle)

                val latencyEstimate = (OPTIMAL_BUFFER_SIZE * 1000f / OPTIMAL_SAMPLE_RATE).format(1)
                Log.d(TAG, "✅ Stream canal $channel: ${latencyEstimate}ms")
            }

            return handle
        } catch (e: Exception) {
            Log.e(TAG, "❌ Excepción creando stream canal $channel: ${e.message}", e)
            return 0L
        }
    }

    // ✅ Render estéreo ULTRA-OPTIMIZADO
    fun renderStereo(audioData: FloatArray, samplePosition: Long) {
        if (!isInitialized || audioData.isEmpty()) return

        val lastPos = lastRenderedSamplePosition[RENDER_STEREO_CHANNEL]
        if (lastPos != null && samplePosition == lastPos) return
        lastRenderedSamplePosition[RENDER_STEREO_CHANNEL] = samplePosition

        val state = channelStates.getOrPut(RENDER_STEREO_CHANNEL) { ChannelState() }
        if (!state.isActive || state.gainDb <= -60f) return

        val streamHandle = getOrCreateStream(RENDER_STEREO_CHANNEL)
        if (streamHandle == 0L) return

        val totalGainDb = state.gainDb + masterGainDb
        val linearGain = dbToLinear(totalGainDb)

        val outSize = audioData.size * 2
        val stereoBuffer = acquireBuffer(outSize)

        var i = 0
        var outIdx = 0
        while (i < audioData.size) {
            val sample = audioData[i] * linearGain
            val clipped = softClipFast(sample)
            stereoBuffer[outIdx] = clipped
            stereoBuffer[outIdx + 1] = clipped
            i++
            outIdx += 2
        }

        try {
            val written = nativeWriteAudio(streamHandle, stereoBuffer)
            val streamState = streamHandles[RENDER_STEREO_CHANNEL]

            if (written < stereoBuffer.size) {
                if (streamState != null) {
                    streamState.consecutiveFailures++
                    when (streamState.consecutiveFailures) {
                        1 -> nativeClearBuffer(streamHandle)
                        3 -> {
                            nativeStopStream(streamHandle)
                            nativeStartStream(streamHandle)
                        }
                        in 5..Int.MAX_VALUE -> destroyStream(RENDER_STEREO_CHANNEL)
                    }
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

    // ✅ Render RF ULTRA-OPTIMIZADO
    fun renderChannelRF(channel: Int, audioData: FloatArray, samplePosition: Long) {
        if (channel == RENDER_STEREO_CHANNEL) return
        if (!isInitialized || audioData.isEmpty()) return

        val lastPos = lastRenderedSamplePosition[channel]
        if (lastPos != null && samplePosition == lastPos) return
        lastRenderedSamplePosition[channel] = samplePosition

        val state = channelStates.getOrPut(channel) { ChannelState() }
        if (!state.isActive || state.gainDb <= -60f) return

        val streamHandle = getOrCreateStream(channel)
        if (streamHandle == 0L) return

        val totalGainDb = state.gainDb + masterGainDb
        val linearGain = dbToLinear(totalGainDb)

        val panRad = ((state.pan + 1f) * Math.PI / 4).toFloat()
        val leftGain = cos(panRad) * linearGain
        val rightGain = sin(panRad) * linearGain

        val outSize = audioData.size * 2
        val stereoBuffer = acquireBuffer(outSize)

        var i = 0
        var outIdx = 0
        while (i < audioData.size) {
            val sample = audioData[i]
            stereoBuffer[outIdx] = softClipFast(sample * leftGain)
            stereoBuffer[outIdx + 1] = softClipFast(sample * rightGain)
            i++
            outIdx += 2
        }

        try {
            val written = nativeWriteAudio(streamHandle, stereoBuffer)
            val streamState = streamHandles[channel]

            if (written < stereoBuffer.size) {
                if (streamState != null) {
                    streamState.consecutiveFailures++
                    when (streamState.consecutiveFailures) {
                        1 -> nativeClearBuffer(streamHandle)
                        3 -> {
                            nativeStopStream(streamHandle)
                            nativeStartStream(streamHandle)
                        }
                        in 5..Int.MAX_VALUE -> destroyStream(channel)
                    }
                }
            } else {
                if (streamState != null) {
                    streamState.consecutiveFailures = 0
                    streamState.lastWriteTime = System.currentTimeMillis()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error escribiendo canal $channel: ${e.message}")
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

    @Suppress("NOTHING_TO_INLINE")
    private inline fun softClipFast(sample: Float): Float {
        return when {
            sample > 1f -> 0.9f + (sample - 1f) * 0.05f
            sample < -1f -> -0.9f + (sample + 1f) * 0.05f
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

    // ✅ STATS SIMPLIFICADOS - Solo funciones que EXISTEN
    fun getRFStats(): Map<String, Any> {
        var totalLatency = 0f
        var totalAvailable = 0
        var activeChannels = 0
        var totalFailures = 0

        streamHandles.forEach { (_, streamState) ->
            try {
                totalAvailable += nativeGetBufferStats(streamState.handle)
                totalLatency += nativeGetLatency(streamState.handle)
                totalFailures += streamState.consecutiveFailures
                activeChannels++
            } catch (_: Exception) {}
        }

        val avgLatency = if (activeChannels > 0) totalLatency / activeChannels else 0f

        return mapOf(
            "avg_latency_ms" to avgLatency,
            "available_frames" to totalAvailable,
            "active_streams" to streamHandles.size,
            "is_initialized" to isInitialized,
            "total_failures" to totalFailures,
            "device_sample_rate" to OPTIMAL_SAMPLE_RATE,
            "device_buffer_size" to OPTIMAL_BUFFER_SIZE,
            "mmap_capable" to deviceSupportsMMAP
        )
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
        if (!active) destroyStream(channel)
    }

    fun setMasterGain(gainDb: Float) {
        masterGainDb = gainDb.coerceIn(-60f, 12f)
    }

    fun getChannelState(channel: Int): ChannelState? = channelStates[channel]
    fun getAllChannelStates(): Map<Int, ChannelState> = channelStates.toMap()

    fun stop() {
        try {
            streamHandles.keys.forEach { channel -> destroyStream(channel) }
            channelStates.clear()
            lastRenderedSamplePosition.clear()
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error deteniendo: ${e.message}")
        }
    }

    fun release() {
        try {
            stop()
            releaseWakeLock()
            if (engineHandle != 0L) {
                nativeDestroyEngine(engineHandle)
                engineHandle = 0
            }
            isInitialized = false
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error liberando: ${e.message}")
        }
    }

    fun isActive(): Boolean = isInitialized && streamHandles.isNotEmpty()

    // ✅ WakeLock management
    fun acquirePartialWakeLock(context: Context) {
        try {
            if (partialWakeLock?.isHeld == true) return

            val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
            partialWakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "FichaTech:AudioRendererCPU"
            ).apply {
                acquire(10 * 60 * 1000L)
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error adquiriendo WakeLock: ${e.message}", e)
        }
    }

    fun renewPartialWakeLock() {
        try {
            partialWakeLock?.let {
                if (it.isHeld) it.acquire(10 * 60 * 1000L)
            }
        } catch (e: Exception) {
            Log.e(TAG, "⚠️ Error renovando WakeLock: ${e.message}")
        }
    }

    fun releaseWakeLock() {
        try {
            partialWakeLock?.let {
                if (it.isHeld) it.release()
            }
            partialWakeLock = null
        } catch (e: Exception) {
            Log.e(TAG, "⚠️ Error liberando WakeLock: ${e.message}")
        }
    }

    // ✅ Latency simplificada
    fun getLatencyMs(): Float {
        if (!isInitialized || streamHandles.isEmpty()) return 0f

        return try {
            var totalLatency = 0f
            var count = 0

            streamHandles.forEach { (_, streamState) ->
                totalLatency += nativeGetLatency(streamState.handle)
                count++
            }

            if (count > 0) totalLatency / count else 0f
        } catch (e: Exception) {
            0f
        }
    }

    @Suppress("NOTHING_TO_INLINE")
    private inline fun dbToLinear(db: Float): Float = 10.0f.pow(db / 20.0f)
    private fun Float.format(digits: Int) = "%.${digits}f".format(this)
}