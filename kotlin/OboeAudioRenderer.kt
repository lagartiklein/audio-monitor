package com.cepalabsfree.fichatech.audiostream

import android.util.Log
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.*

/**
 * ✅ FIXED: AudioRenderer con recuperación automática de saturación
 */
class OboeAudioRenderer {

    companion object {
        private const val TAG = "OboeAudioRenderer"
        private const val SAMPLE_RATE = 48000
        private const val CHANNELS = 2
        private const val MAX_WRITE_FAILURES = 2  // ✅ Reducido de 3 a 2
        private const val MAX_SIMULTANEOUS_STREAMS = 48 // ✅ Límite aumentado para más canales

        init {
            try {
                System.loadLibrary("fichatech_audio")
                Log.d(TAG, "✅ Biblioteca nativa Oboe cargada")
            } catch (e: UnsatisfiedLinkError) {
                Log.e(TAG, "❌ Error cargando biblioteca nativa: ${e.message}", e)
            }
        }
    }

    // ✅ Métodos nativos
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
    // ✅ NUEVO: Para baja latencia (solo buffer size, performance mode ya está en builder)
    private external fun nativeSetBufferSize(streamHandle: Long, bufferSize: Int)

    // Estado interno
    private var engineHandle: Long = 0
    private val streamHandles = ConcurrentHashMap<Int, StreamState>()
    private val channelStates = ConcurrentHashMap<Int, ChannelState>()

    private var masterGainDb = 0f
    private var isInitialized = false
    private var totalPacketsReceived = 0
    private var totalPacketsDropped = 0

    // ✅ Tracking de fallos por stream
    data class StreamState(
        val handle: Long,
        var consecutiveFailures: Int = 0,
        var lastWriteTime: Long = System.currentTimeMillis(),
        var lastClearTime: Long = 0  // ✅ NUEVO: Para evitar clears en bucle
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
            engineHandle = nativeCreateEngine(SAMPLE_RATE, CHANNELS)
            isInitialized = engineHandle != 0L

            if (isInitialized) {
                Log.d(TAG, "✅ Oboe Engine inicializado (RF Mode FIXED)")
                Log.d(TAG, "   📊 Sample Rate: $SAMPLE_RATE Hz")
                Log.d(TAG, "   🎵 Canales: $CHANNELS")
                Log.d(TAG, "   📦 Engine Handle: $engineHandle")
                Log.d(TAG, "   🔄 Auto-recuperación: ENABLED")
            } else {
                Log.e(TAG, "❌ Falló inicialización de Oboe Engine")
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error inicializando Oboe: ${e.message}", e)
            isInitialized = false
        }
    }

    /**
     * ✅ FIXED: Obtiene o crea stream con auto-recuperación
     */
    private fun getOrCreateStream(channel: Int): Long {
        val streamState = streamHandles[channel]

        // ✅ Si existe y está sano, retornar
        if (streamState != null && streamState.consecutiveFailures < MAX_WRITE_FAILURES) {
            return streamState.handle
        }

        // ✅ Si existe pero tiene muchos fallos, recrear
        if (streamState != null) {
            Log.w(TAG, "🔄 Recreando stream canal $channel (${streamState.consecutiveFailures} fallos)")
            destroyStream(channel)
        }

        // ✅ Verificar límite antes de crear
        if (streamHandles.size >= MAX_SIMULTANEOUS_STREAMS && !streamHandles.containsKey(channel)) {
            Log.w(TAG, "⚠️ Límite de streams alcanzado ($MAX_SIMULTANEOUS_STREAMS)")

            // Opcional: cerrar stream menos usado
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

        // ✅ Crear nuevo stream
        return createNewStream(channel)
    }

    /**
     * ✅ Crear stream limpio
     */
    private fun createNewStream(channel: Int): Long {
        try {
            if (!isInitialized) {
                Log.e(TAG, "❌ Engine no inicializado")
                return 0L
            }

            val handle = nativeCreateStream(engineHandle, channel)

            if (handle != 0L) {
                // ✅ NUEVO: Configurar para baja latencia
                nativeSetBufferSize(handle, 128) // frames mínimos

                nativeStartStream(handle)
                streamHandles[channel] = StreamState(handle)
                Log.d(TAG, "✅ Stream canal $channel creado en modo LOW_LATENCY")
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
     * ✅ Destruir stream específico
     */
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

    /**
     * ✅ FIXED: Renderiza audio con auto-recuperación agresiva
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

        // ✅ Obtener o recrear stream si es necesario
        val streamHandle = getOrCreateStream(channel)
        if (streamHandle == 0L) {
            totalPacketsDropped++
            return
        }

        // Calcular ganancias
        val totalGainDb = state.gainDb + masterGainDb
        val linearGain = dbToLinear(totalGainDb)

        // Panorama
        val panRad = ((state.pan + 1f) * Math.PI / 4).toFloat()
        val leftGain = cos(panRad) * linearGain
        val rightGain = sin(panRad) * linearGain

        // Buffer stereo interleaved
        val stereoBuffer = FloatArray(audioData.size * 2)

        var sumSquares = 0f
        var peak = 0f

        for (i in audioData.indices) {
            val sample = audioData[i]

            val left = sample * leftGain
            val right = sample * rightGain

            stereoBuffer[i * 2] = softClip(left)
            stereoBuffer[i * 2 + 1] = softClip(right)

            val absSample = abs(sample * linearGain)
            if (absSample > peak) peak = absSample
            sumSquares += sample * sample
        }

        state.peakLevel = peak
        state.rmsLevel = sqrt(sumSquares / audioData.size)
        state.packetsReceived++

        // ✅ Escribir a Oboe con recuperación agresiva
        try {
            val written = nativeWriteAudio(streamHandle, stereoBuffer)
            val streamState = streamHandles[channel]

            if (written < stereoBuffer.size) {
                val dropped = (stereoBuffer.size - written) / 2
                totalPacketsDropped += dropped

                // ✅ Incrementar contador de fallos
                if (streamState != null) {
                    streamState.consecutiveFailures++

                    // ✅ NUEVO: Clear agresivo al PRIMER fallo si ya hubo uno reciente
                    val timeSinceLastClear = System.currentTimeMillis() - streamState.lastClearTime

                    // ✅ Estrategia escalonada
                    if (streamState.consecutiveFailures == 1) {
                        // Primer fallo: solo clear (rápido, ~5ms)
                        nativeClearBuffer(streamHandle)
                    }
                    else if (streamState.consecutiveFailures == 3) {
                        // 3 fallos: clear + reiniciar
                        nativeStopStream(streamHandle)
                        nativeStartStream(streamHandle)
                    }
                    else if (streamState.consecutiveFailures >= 5) {
                        // 5+ fallos: problema serio, recrear
                        destroyStream(channel)
                    }
                }

                if (dropped > 100) {
                    Log.d(TAG, "🗑️ RF Drop: $dropped frames en canal $channel")
                }
            } else {
                // ✅ Escritura exitosa, resetear fallos
                if (streamState != null) {
                    streamState.consecutiveFailures = 0
                    streamState.lastWriteTime = System.currentTimeMillis()
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error escribiendo canal $channel: ${e.message}")
            totalPacketsDropped += audioData.size / 2

            // ✅ Marcar como fallido y limpiar
            val streamState = streamHandles[channel]
            if (streamState != null) {
                streamState.consecutiveFailures++

                // ✅ NUEVO: En excepción, limpiar INMEDIATAMENTE
                val timeSinceLastClear = System.currentTimeMillis() - streamState.lastClearTime

                if (timeSinceLastClear > 500) {  // Mínimo 500ms entre clears
                    Log.w(TAG, "💀 Stream canal $channel con excepción, LIMPIANDO")

                    try {
                        nativeClearBuffer(streamHandle)
                        streamState.lastClearTime = System.currentTimeMillis()
                    } catch (ignored: Exception) {
                        // Si falla el clear, forzar recreación
                        Log.e(TAG, "Clear falló, marcando para recreación")
                        streamState.consecutiveFailures = MAX_WRITE_FAILURES
                    }
                }
            }
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

    /**
     * ✅ FIXED: Forzar recreación con limpieza completa
     */
    fun recreateAllStreams() {
        Log.w(TAG, "🔄 Recreando TODOS los streams...")

        val channelsToRecreate = streamHandles.keys.toList()

        // Destruir todos
        channelsToRecreate.forEach { channel ->
            destroyStream(channel)
        }

        // Los streams se recrearán automáticamente en el próximo renderChannelRF
        Log.i(TAG, "✅ Streams marcados para recreación: ${channelsToRecreate.size}")
    }

    /**
     * ✅ FIXED: Stats RF con campo de resets
     */
    fun getChannelRFStats(channel: Int): Map<String, Any> {
        val streamState = streamHandles[channel]
        if (streamState == null) {
            return emptyMap()
        }

        return try {
            val stats = nativeGetRFStats(streamState.handle)
            val resets = stats.getOrNull(6) as? Int ?: 0
            mapOf(
                "available_frames" to stats[0],
                "latency_ms" to stats[1],
                "is_receiving" to (stats[2] == 1),
                "underruns" to stats[3],
                "drops" to stats[4],
                "buffer_usage" to stats[5],
                "resets" to resets,
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
        var totalResets = 0  // ✅ NUEVO
        var activeChannels = 0
        var totalFailures = 0

        streamHandles.forEach { (channel, streamState) ->
            try {
                val stats = nativeGetRFStats(streamState.handle)
                totalAvailable += stats[0]
                totalLatency += stats[1]
                totalUnderruns += stats[3]
                totalDrops += stats[4]
                totalResets += stats.getOrNull(6) ?: 0  // ✅ NUEVO
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
            "resets" to totalResets,  // ✅ NUEVO
            "active_streams" to streamHandles.size,
            "is_initialized" to isInitialized,
            "total_failures" to totalFailures
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

            streamHandles.keys.forEach { channel ->
                destroyStream(channel)
            }

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

    private fun dbToLinear(db: Float): Float {
        return if (db <= -60f) 0f else 10.0f.pow(db / 20.0f)
    }

    private fun linearToDb(linear: Float): Float {
        return if (linear > 0.00001f) {
            20.0f * log10(linear)
        } else -60f
    }
}