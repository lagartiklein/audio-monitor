package com.cepalabsfree.fichatech.sonometro

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import kotlin.math.*

class BpmView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    companion object {
        private const val MAX_RECENT_AMPLITUDES = 150 // Aumentado para mejor análisis
        private const val MAX_BEAT_TIMES = 16 // Aumentado para mayor precisión
        private const val MIN_BPM_INTERVAL_MS = 300L // 200 BPM máximo
        private const val MAX_BPM_INTERVAL_MS = 2000L // 30 BPM mínimo
    }

    // Pinturas para pantalla digital
    private val screenPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val bpmTextPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val confidencePaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val beatIndicatorPaint = Paint(Paint.ANTI_ALIAS_FLAG)

    private var bpm = 60.0
    private var lastBeatTime = 0L
    private val beatAnimationDuration = 200L // ms
    private var beatAnimationStartTime = 0L

    // Para detección de picos mejorada
    private val recentAmplitudes = mutableListOf<Double>()

    // Para cálculo de BPM
    private val beatTimes = mutableListOf<Long>()

    // ✅ NUEVO: Métricas de confianza
    private var detectionConfidence = 0.0 // 0-1
    private var bpmStability = 0.0 // 0-1, basado en varianza de intervalos

    // ✅ NUEVO: Análisis de tendencia
    private val bpmHistory = mutableListOf<Double>()
    private val maxBpmHistory = 20

    init {
        setupPaints()
    }

    private fun setupPaints() {
        // Fondo pantalla digital
        screenPaint.color = Color.parseColor("#181A1B")
        screenPaint.style = Paint.Style.FILL

        // Borde pantalla con glow
        borderPaint.color = Color.parseColor("#33FF4081")
        borderPaint.style = Paint.Style.STROKE
        borderPaint.strokeWidth = 6f
        borderPaint.setShadowLayer(10f, 0f, 0f, Color.parseColor("#FF4081"))

        // BPM grande tipo digital
        bpmTextPaint.color = Color.parseColor("#FFEB3B")
        bpmTextPaint.textSize = 88f
        bpmTextPaint.textAlign = Paint.Align.CENTER
        bpmTextPaint.typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
        bpmTextPaint.setShadowLayer(8f, 0f, 0f, Color.parseColor("#80FFEB3B"))

        // Etiqueta BPM
        labelPaint.color = Color.parseColor("#FF4081")
        labelPaint.textSize = 28f
        labelPaint.textAlign = Paint.Align.CENTER
        labelPaint.typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)

        // ✅ NUEVO: Indicador de confianza
        confidencePaint.color = Color.parseColor("#4CAF50")
        confidencePaint.textSize = 20f
        confidencePaint.textAlign = Paint.Align.CENTER
        confidencePaint.typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)

        // ✅ NUEVO: Indicador de beat
        beatIndicatorPaint.style = Paint.Style.FILL
        beatIndicatorPaint.color = Color.parseColor("#FF4081")
    }

    fun updateAmplitude(amplitude: Double) {
        // Agregar amplitud reciente
        recentAmplitudes.add(amplitude)
        if (recentAmplitudes.size > MAX_RECENT_AMPLITUDES) {
            recentAmplitudes.removeAt(0)
        }

        // ✅ MEJORADO: Detección de picos con análisis estadístico más robusto
        if (recentAmplitudes.size > 30) { // Aumentado de 20 a 30
            val currentIndex = recentAmplitudes.size - 1
            val currentAmp = recentAmplitudes[currentIndex]

            // Ventana de análisis más amplia
            val windowSize = 40
            val startIndex = max(0, currentIndex - windowSize)
            val analysisWindow = recentAmplitudes.subList(startIndex, currentIndex)

            // ✅ NUEVO: Calcular media y desviación estándar
            val mean = analysisWindow.average()
            val variance = analysisWindow.map { (it - mean).pow(2) }.average()
            val stdDev = sqrt(variance)

            // ✅ MEJORADO: Umbral adaptativo basado en desviación estándar
            // Un pico debe estar al menos 2 desviaciones estándar por encima de la media
            val adaptiveThreshold = mean + (stdDev * 2.0)
            val minimumThreshold = max(adaptiveThreshold, 0.08) // Threshold mínimo

            // ✅ NUEVO: Verificar que sea un pico local (no solo un valor alto)
            val isLocalPeak = if (currentIndex >= 2 && currentIndex < recentAmplitudes.size - 2) {
                val prev1 = recentAmplitudes[currentIndex - 1]
                val prev2 = recentAmplitudes[currentIndex - 2]
                val trend = currentAmp > prev1 && prev1 >= prev2
                trend && currentAmp > minimumThreshold
            } else {
                currentAmp > minimumThreshold
            }

            if (isLocalPeak) {
                val currentTime = System.currentTimeMillis()

                // Verificar intervalo mínimo
                if (beatTimes.isEmpty() || (currentTime - lastBeatTime) > MIN_BPM_INTERVAL_MS) {
                    beatTimes.add(currentTime)
                    lastBeatTime = currentTime
                    beatAnimationStartTime = currentTime

                    // Mantener ventana de beats
                    if (beatTimes.size > MAX_BEAT_TIMES) {
                        beatTimes.removeAt(0)
                    }

                    // Calcular BPM
                    calculateBPMImproved()

                    // Iniciar animación de latido
                    invalidate()
                }
            }
        }

        // Actualizar visualización continuamente
        invalidate()
    }

    private fun calculateBPMImproved() {
        if (beatTimes.size < 3) { // Aumentado de 2 a 3
            bpm = 60.0
            detectionConfidence = 0.0
            bpmStability = 0.0
            return
        }

        // Calcular intervalos entre picos
        val intervals = mutableListOf<Long>()
        for (i in 1 until beatTimes.size) {
            intervals.add(beatTimes[i] - beatTimes[i - 1])
        }

        // ✅ MEJORADO: Filtrado de outliers con IQR mejorado
        val sortedIntervals = intervals.sorted()

        // Filtrar por rango válido primero
        val validIntervals = sortedIntervals.filter {
            it in MIN_BPM_INTERVAL_MS..MAX_BPM_INTERVAL_MS
        }

        if (validIntervals.isEmpty()) {
            bpm = 60.0
            detectionConfidence = 0.0
            bpmStability = 0.0
            return
        }

        // ✅ NUEVO: Método de agrupación (clustering) para encontrar tempo dominante
        val bpmCandidates = validIntervals.map { 60000.0 / it }

        // Agrupar BPMs similares (±5 BPM)
        val clusters = mutableMapOf<Int, MutableList<Double>>()
        bpmCandidates.forEach { bpmValue ->
            val roundedBpm = (bpmValue / 5.0).roundToInt() * 5 // Redondear a múltiplos de 5
            clusters.getOrPut(roundedBpm) { mutableListOf() }.add(bpmValue)
        }

        // Encontrar el cluster más grande
        val dominantCluster = clusters.maxByOrNull { it.value.size }?.value

        if (dominantCluster == null || dominantCluster.isEmpty()) {
            bpm = 60.0
            detectionConfidence = 0.0
            bpmStability = 0.0
            return
        }

        // ✅ MEJORADO: BPM es la mediana del cluster dominante (más robusto que la media)
        val sortedCluster = dominantCluster.sorted()
        val medianBpm = if (sortedCluster.size % 2 == 0) {
            (sortedCluster[sortedCluster.size / 2 - 1] + sortedCluster[sortedCluster.size / 2]) / 2.0
        } else {
            sortedCluster[sortedCluster.size / 2]
        }

        // ✅ NUEVO: Calcular confianza basada en tamaño del cluster
        detectionConfidence = (dominantCluster.size.toDouble() / bpmCandidates.size).coerceIn(0.0, 1.0)

        // ✅ NUEVO: Calcular estabilidad basada en varianza del cluster
        val clusterMean = dominantCluster.average()
        val clusterVariance = dominantCluster.map { (it - clusterMean).pow(2) }.average()
        val clusterStdDev = sqrt(clusterVariance)
        bpmStability = (1.0 - (clusterStdDev / clusterMean).coerceIn(0.0, 1.0)).coerceIn(0.0, 1.0)

        // ✅ MEJORADO: Suavizado temporal con peso basado en confianza
        val smoothingFactor = 0.3 * detectionConfidence + 0.1 * (1 - detectionConfidence)
        val newBpm = medianBpm.coerceIn(30.0, 200.0)
        bpm = bpm * (1.0 - smoothingFactor) + newBpm * smoothingFactor

        // ✅ NUEVO: Mantener historial de BPM
        bpmHistory.add(bpm)
        if (bpmHistory.size > maxBpmHistory) {
            bpmHistory.removeAt(0)
        }

        invalidate()
    }

    fun getCurrentBPM(): Double {
        return bpm
    }

    fun getConfidence(): Double {
        return detectionConfidence
    }

    fun getStability(): Double {
        return bpmStability
    }

    fun reset() {
        bpm = 60.0
        lastBeatTime = 0L
        beatAnimationStartTime = 0L
        recentAmplitudes.clear()
        beatTimes.clear()
        bpmHistory.clear()
        detectionConfidence = 0.0
        bpmStability = 0.0
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val width = width.toFloat()
        val height = height.toFloat()
        val centerX = width / 2
        val centerY = height / 2

        val padding = 18f
        val rectLeft = padding
        val rectTop = padding
        val rectRight = width - padding
        val rectBottom = height - padding

        // Fondo pantalla digital
        canvas.drawRoundRect(rectLeft, rectTop, rectRight, rectBottom, 32f, 32f, screenPaint)

        // ✅ NUEVO: Animación de beat (pulso de borde)
        val timeSinceBeat = System.currentTimeMillis() - beatAnimationStartTime
        if (timeSinceBeat < beatAnimationDuration) {
            val progress = timeSinceBeat / beatAnimationDuration.toFloat()
            val alpha = ((1f - progress) * 255).toInt().coerceIn(0, 255)
            borderPaint.alpha = alpha
            borderPaint.strokeWidth = 6f + (progress * 4f)
        } else {
            borderPaint.alpha = 80
            borderPaint.strokeWidth = 6f
        }

        // Borde pantalla
        canvas.drawRoundRect(rectLeft, rectTop, rectRight, rectBottom, 32f, 32f, borderPaint)

        // ✅ MEJORADO: Color BPM basado en rango típico
        bpmTextPaint.color = when {
            bpm < 60 -> Color.parseColor("#64B5F6") // Azul (lento)
            bpm < 100 -> Color.parseColor("#FFEB3B") // Amarillo (normal)
            bpm < 140 -> Color.parseColor("#FFA726") // Naranja (rápido)
            else -> Color.parseColor("#EF5350") // Rojo (muy rápido)
        }

        // BPM grande centrado
        val bpmText = "%.0f".format(bpm)
        canvas.drawText(bpmText, centerX, centerY + 10f, bpmTextPaint)

        // Etiqueta BPM
        canvas.drawText("BPM", centerX, centerY + 60f, labelPaint)

        // ✅ NUEVO: Indicador de confianza
        if (detectionConfidence > 0.3) {
            val confidencePercent = (detectionConfidence * 100).toInt()
            confidencePaint.color = when {
                detectionConfidence > 0.7 -> Color.parseColor("#4CAF50") // Verde
                detectionConfidence > 0.5 -> Color.parseColor("#FFC107") // Amarillo
                else -> Color.parseColor("#FF9800") // Naranja
            }
            confidencePaint.textSize = 18f
            canvas.drawText(
                "Conf: $confidencePercent%",
                centerX,
                rectBottom - 15f,
                confidencePaint
            )
        }

        // ✅ NUEVO: Indicador visual de beats
        if (timeSinceBeat < beatAnimationDuration) {
            val progress = timeSinceBeat / beatAnimationDuration.toFloat()
            val radius = 8f + (progress * 12f)
            val alpha = ((1f - progress) * 200).toInt().coerceIn(0, 200)

            beatIndicatorPaint.alpha = alpha
            canvas.drawCircle(rectRight - 25f, rectTop + 25f, radius, beatIndicatorPaint)
        }
    }
}