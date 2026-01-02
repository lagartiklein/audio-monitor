package com.cepalabsfree.fichatech.audiostream

import android.util.Log
import kotlin.math.abs

/**
 * ✅ FASE 3: Sincronización de timestamps para UDP
 *
 * Propósito: Corrección de drift de reloj entre cliente y servidor
 * Ganancia: 0.5-1ms de latencia más predecible
 *
 * El protocolo UDP no garantiza orden ni tiempo, así que necesitamos:
 * 1. Detectar drift (reloj del cliente vs servidor)
 * 2. Aplicar corrección gradual
 * 3. Validar continuidad de audio
 */
class AudioTimestampSync {
    companion object {
        private const val TAG = "AudioTimestampSync"

        // Número de muestras de sincronización antes de aplicar corrección
        private const val SYNC_WINDOW = 16

        // Máximo drift permitido antes de resincronizar (ms)
        private const val MAX_ALLOWED_DRIFT_MS = 50.0

        // Factor de corrección suave (EMA - Exponential Moving Average)
        private const val CORRECTION_FACTOR = 0.1f
    }

    // Historial de timestamps para calcular drift
    private val timestampHistory = ArrayDeque<TimestampPair>(SYNC_WINDOW)
    private val syncLock = Any()

    // Estado de sincronización
    private var driftMsEMA = 0f  // Drift suavizado (EMA)
    private var isInitialized = false
    private var lastCorrectionTime = System.currentTimeMillis()
    private var correctionCount = 0

    data class TimestampPair(
        val serverTimestamp: Long,  // Timestamp del servidor (ms)
        val clientTimestamp: Long,  // Timestamp del cliente local (ms)
        val samplePosition: Long    // Posición de muestra en el stream
    )

    data class SyncResult(
        val driftMs: Float,        // Drift actual (ms)
        val correctionFactor: Float,  // Factor de corrección a aplicar
        val isSynced: Boolean      // Si está dentro de tolerancia
    )

    /**
     * Registrar un par de timestamps para análisis de drift
     */
    fun recordTimestamps(serverTime: Long, clientTime: Long, samplePos: Long): SyncResult {
        synchronized(syncLock) {
            // Agregar nuevo par
            timestampHistory.addLast(TimestampPair(serverTime, clientTime, samplePos))

            // Mantener ventana de análisis
            if (timestampHistory.size > SYNC_WINDOW) {
                timestampHistory.removeFirst()
            }

            // Calcular drift si tenemos suficientes muestras
            if (timestampHistory.size >= 4) {
                val drift = calculateDrift()

                // Aplicar EMA para suavizar drift
                driftMsEMA = (driftMsEMA * (1 - CORRECTION_FACTOR)) +
                             (drift * CORRECTION_FACTOR)

                isInitialized = true

                // Detectar si está sincronizado
                val isSynced = abs(driftMsEMA) < MAX_ALLOWED_DRIFT_MS

                return SyncResult(
                    driftMs = driftMsEMA,
                    correctionFactor = if (isSynced) 1.0f else (1.0f + driftMsEMA / 1000.0f),
                    isSynced = isSynced
                )
            }

            return SyncResult(0f, 1.0f, false)
        }
    }

    /**
     * Calcular drift entre reloj del cliente y servidor
     * Usa regresión lineal simple en la ventana
     */
    private fun calculateDrift(): Float {
        if (timestampHistory.size < 2) return 0f

        // Calcular diferencia de timestamp acumulada
        var totalServerDiff = 0L
        var totalClientDiff = 0L

        for (i in 1 until timestampHistory.size) {
            val prev = timestampHistory[i - 1]
            val curr = timestampHistory[i]

            totalServerDiff += (curr.serverTimestamp - prev.serverTimestamp)
            totalClientDiff += (curr.clientTimestamp - prev.clientTimestamp)
        }

        // Drift = cuánto se desvió (si es positivo, cliente es lento)
        if (totalClientDiff == 0L) return 0f

        val driftRatio = (totalServerDiff.toFloat() / totalClientDiff.toFloat()) - 1.0f

        // Convertir a ms/segundo
        return driftRatio * 1000f
    }

    /**
     * Obtener corrección a aplicar a la playback speed
     */
    fun getCorrectionFactor(): Float {
        if (!isInitialized) return 1.0f

        // Corrección suave: 1.0 = no cambio, 1.01 = 1% más rápido, 0.99 = 1% más lento
        val maxCorrection = 0.05f  // Máximo 5% de corrección
        val correction = (driftMsEMA / 1000.0f).coerceIn(-maxCorrection, maxCorrection)

        return 1.0f + correction
    }

    /**
     * Estado actual de sincronización para debugging
     */
    fun getDebugInfo(): Map<String, Any> {
        synchronized(syncLock) {
            return mapOf(
                "initialized" to isInitialized as Any,
                "drift_ms" to driftMsEMA as Any,
                "correction_factor" to getCorrectionFactor() as Any,
                "buffer_size" to timestampHistory.size as Any,
                "correction_count" to correctionCount as Any,
                "last_correction_ms_ago" to (System.currentTimeMillis() - lastCorrectionTime) as Any
            )
        }
    }

    /**
     * Resetear sincronización (e.g., después de reconexión)
     */
    fun reset() {
        synchronized(syncLock) {
            timestampHistory.clear()
            driftMsEMA = 0f
            isInitialized = false
            correctionCount = 0
            lastCorrectionTime = System.currentTimeMillis()
            Log.d(TAG, "🔄 Sincronización resetizada")
        }
    }
}

/**
 * ✅ FASE 3: Jitter Buffer para UDP
 *
 * Propósito: Absorber variabilidad de latencia de red
 * Tamaño: 10 paquetes (~20-50ms de buffer)
 *
 * Sin jitter buffer, cada variación de latencia causa:
 * - Underruns (falta de audio)
 * - Overruns (buffer lleno)
 * - Audio discontinuo
 */
class JitterBuffer(val maxPackets: Int = 10) {
    companion object {
        private const val TAG = "JitterBuffer"
    }

    private data class BufferedPacket(
        val sequence: Int,
        val samplePosition: Long,
        val audioData: FloatArray,
        val arrivalTime: Long = System.currentTimeMillis()
    )

    private val buffer = ArrayDeque<BufferedPacket>(maxPackets)
    private val bufferLock = Any()
    private var lastSequence = -1
    private var sequenceGaps = 0

    /**
     * Agregar paquete al buffer
     * Retorna false si el buffer está lleno
     */
    fun push(sequence: Int, samplePos: Long, audioData: FloatArray): Boolean {
        synchronized(bufferLock) {
            if (buffer.size >= maxPackets) {
                sequenceGaps++
                return false  // Buffer lleno, descartar
            }

            // Detectar gaps en secuencia
            if (lastSequence >= 0 && sequence != lastSequence + 1) {
                val gap = sequence - lastSequence - 1
                if (gap > 0) {
                    sequenceGaps += gap
                    Log.w(TAG, "⚠️ Brecha de secuencia: $gap paquetes perdidos")
                }
            }

            buffer.addLast(BufferedPacket(sequence, samplePos, audioData))
            lastSequence = sequence

            return true
        }
    }

    /**
     * Obtener siguiente paquete
     */
    fun pop(): Map<String, Any>? {
        synchronized(bufferLock) {
            val packet = buffer.removeFirstOrNull() ?: return null

            // Retornar como map para ser agnóstico del tipo
            return mapOf(
                "samplePosition" to packet.samplePosition as Any,
                "audioData" to packet.audioData as Any,
                "activeChannels" to listOf(0) as Any,
                "samplesPerChannel" to packet.audioData.size as Any,
                "timestamp" to packet.arrivalTime as Any,
                "sequence" to packet.sequence as Any
            )
        }
    }

    /**
     * Estado del buffer
     */
    fun getStats(): Map<String, Any> {
        synchronized(bufferLock) {
            return mapOf(
                "current_size" to buffer.size as Any,
                "max_size" to maxPackets as Any,
                "fill_percent" to ((buffer.size.toFloat() / maxPackets) * 100).toInt() as Any,
                "sequence_gaps" to sequenceGaps as Any
            )
        }
    }

    /**
     * Limpiar buffer
     */
    fun clear() {
        synchronized(bufferLock) {
            buffer.clear()
            lastSequence = -1
            sequenceGaps = 0
        }
    }
}
