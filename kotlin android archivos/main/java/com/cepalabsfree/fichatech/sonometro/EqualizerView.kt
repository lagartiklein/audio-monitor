package com.cepalabsfree.fichatech.sonometro

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import kotlin.math.*

/**
 * Vista profesional para detección de acoples y tonos problemáticos en tiempo real
 * Versión mejorada con menos falsos positivos
 *
 * NOTA: Este archivo permanece SIN CAMBIOS MAYORES
 * Solo recibe buffers desde InicioFragment y hace su propio análisis FFT
 */
class EqualizerView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null
) : View(context, attrs) {

    companion object {
        private const val BAR_COUNT = 60
        private const val MIN_FREQ = 20.0
        private const val MAX_FREQ = 20000.0
        private const val SAMPLE_RATE = 44100.0
        private const val FFT_SIZE = 2048

        private const val FEEDBACK_THRESHOLD = 0.75
        private const val FEEDBACK_PERSISTENCE_MS = 2000L
        private const val SMOOTH_FACTOR = 0.12f
        private const val AMPLITUDE_SCALE = 0.45f
        private const val MIN_THRESHOLD = 0.12
        private const val NOISE_FLOOR = 600f

        private val FEEDBACK_FREQ_RANGES = listOf(
            250.0 to 500.0,
            500.0 to 800.0,
            800.0 to 1600.0,
            1600.0 to 2400.0,
            2400.0 to 4000.0,
            4000.0 to 6000.0,
            6000.0 to 8000.0
        )

        private const val BAR_RADIUS = 6f
        private const val BAR_SPACING_FACTOR = 1.15f

        private const val HISTORY_SIZE = 25
        private const val VAR_THRESHOLD = 0.0025
        private const val MIN_PEAK_RATIO = 1.25
    }

    private object Colors {
        val BACKGROUND = Color.parseColor("#0A0E14")
        val GRID = Color.argb(25, 100, 150, 200)
        val INACTIVE_BAR = Color.argb(30, 120, 120, 140)

        val SAFE = Color.parseColor("#00C853")
        val WARNING = Color.parseColor("#FFD600")
        val DANGER = Color.parseColor("#FF6D00")
        val FEEDBACK = Color.parseColor("#FF1744")

        val FREQUENCY_BG = Color.argb(220, 25, 30, 40)
        val FEEDBACK_BG = Color.argb(240, 120, 20, 20)
    }

    private data class BarData(
        val index: Int,
        val centerFreq: Double,
        val leftEdge: Double,
        val rightEdge: Double,
        var amplitude: Double = 0.0,
        var smoothAmplitude: Double = 0.0,
        var peakAmplitude: Double = 0.0,
        var feedbackStartTime: Long? = null,
        var isFeedback: Boolean = false,
        var isFeedbackFreq: Boolean = false
    )

    private data class DetectedTone(
        val frequency: Double,
        val amplitude: Double,
        val barIndex: Int,
        val isFeedback: Boolean,
        val persistenceMs: Long,
        val confidence: Double
    )

    private var barsData: List<BarData> = emptyList()
    private val detectedTones = mutableListOf<DetectedTone>()

    private val window = FloatArray(FFT_SIZE) { i ->
        val a0 = 0.35875f
        val a1 = 0.48829f
        val a2 = 0.14128f
        val a3 = 0.01168f
        val n = FFT_SIZE - 1
        (a0 - a1 * cos(2 * PI * i / n) +
                a2 * cos(4 * PI * i / n) -
                a3 * cos(6 * PI * i / n)).toFloat()
    }

    private val real = FloatArray(FFT_SIZE)
    private val imag = FloatArray(FFT_SIZE)
    private val magnitudes = FloatArray(FFT_SIZE / 2)

    private var primaryFreq: Double? = null
    private val peakDecayRate = 0.012f

    private val amplitudeHistory = Array(BAR_COUNT) { mutableListOf<Double>() }
    private val maxHistorySize = HISTORY_SIZE

    private val bgPaint = Paint().apply {
        color = Colors.BACKGROUND
        style = Paint.Style.FILL
    }

    private val barInactivePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Colors.INACTIVE_BAR
        style = Paint.Style.FILL
    }

    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 28f
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        textAlign = Paint.Align.CENTER
        setShadowLayer(8f, 0f, 3f, Color.argb(150, 0, 0, 0))
    }

    private val smallTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 20f
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.NORMAL)
        textAlign = Paint.Align.CENTER
        setShadowLayer(6f, 0f, 2f, Color.argb(120, 0, 0, 0))
    }

    private val freqBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Colors.FREQUENCY_BG
        style = Paint.Style.FILL
    }

    private val feedbackBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Colors.FEEDBACK_BG
        style = Paint.Style.FILL
    }

    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Colors.GRID
        strokeWidth = 1f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(8f, 5f), 0f)
    }

    private val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        maskFilter = BlurMaskFilter(16f, BlurMaskFilter.Blur.NORMAL)
    }

    private val peakLinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        strokeWidth = 2.5f
        style = Paint.Style.STROKE
        alpha = 180
    }

    private val connectorPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 2f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(6f, 4f), 0f)
        alpha = 160
    }

    private val feedbackIndicatorPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 4f
        style = Paint.Style.STROKE
    }

    init {
        initializeBarsData()
        barsData.forEach { bar ->
            bar.isFeedbackFreq = FEEDBACK_FREQ_RANGES.any { (low, high) ->
                bar.centerFreq in low..high
            }
        }
    }

    private fun initializeBarsData() {
        val logMin = ln(MIN_FREQ)
        val logMax = ln(MAX_FREQ)
        val logStep = (logMax - logMin) / (BAR_COUNT - 1)

        barsData = List(BAR_COUNT) { i ->
            val centerFreq = exp(logMin + i * logStep)
            val leftEdge = if (i == 0) MIN_FREQ else sqrt(
                exp(logMin + (i - 1) * logStep) * centerFreq
            )
            val rightEdge = if (i == BAR_COUNT - 1) MAX_FREQ else sqrt(
                centerFreq * exp(logMin + (i + 1) * logStep)
            )

            BarData(
                index = i,
                centerFreq = centerFreq,
                leftEdge = leftEdge,
                rightEdge = rightEdge
            )
        }
    }

    private fun getBarColor(amplitude: Double, isFeedback: Boolean): Int {
        return when {
            isFeedback -> Colors.FEEDBACK
            amplitude > 0.80 -> Colors.DANGER
            amplitude > 0.60 -> Colors.WARNING
            else -> Colors.SAFE
        }
    }

    fun updateAmplitudes(rawBuffer: ShortArray) {
        val sizeToProcess = min(rawBuffer.size, FFT_SIZE)

        for (i in 0 until FFT_SIZE) {
            real[i] = if (i < sizeToProcess) rawBuffer[i] * window[i] else 0f
            imag[i] = 0f
        }

        fft(real, imag)

        var maxMag = 0f
        var maxIdx = 0
        for (i in magnitudes.indices) {
            val mag = sqrt(real[i] * real[i] + imag[i] * imag[i])
            magnitudes[i] = mag
            if (mag > maxMag) {
                maxMag = mag
                maxIdx = i
            }
        }

        primaryFreq = if (maxMag > NOISE_FLOOR) {
            maxIdx * SAMPLE_RATE / FFT_SIZE
        } else {
            null
        }

        applyFeedbackBandpass()

        updateBarAmplitudes()
        detectFeedback()
        updatePeaks()
        postInvalidateOnAnimation()
    }

    private fun applyFeedbackBandpass() {
        for (i in magnitudes.indices) {
            val freq = i * SAMPLE_RATE / FFT_SIZE
            val weight = calculateFrequencyWeight(freq)
            magnitudes[i] *= weight
        }
    }

    private fun calculateFrequencyWeight(freq: Double): Float {
        return when {
            freq in 250.0..500.0 -> 1.25f
            freq in 500.0..800.0 -> 1.30f
            freq in 800.0..1600.0 -> 1.35f
            freq in 1600.0..2400.0 -> 1.30f
            freq in 2400.0..4000.0 -> 1.25f
            freq in 4000.0..6000.0 -> 1.20f
            freq in 6000.0..8000.0 -> 1.15f
            freq < 100.0 -> 0.5f
            freq > 10000.0 -> 0.6f
            else -> 0.8f
        }
    }

    private fun updateBarAmplitudes() {
        barsData.forEach { bar ->
            val startBin = ((bar.leftEdge * FFT_SIZE) / SAMPLE_RATE).toInt()
            val endBin = ((bar.rightEdge * FFT_SIZE) / SAMPLE_RATE).toInt()

            var sum = 0.0
            var count = 0

            for (bin in startBin..endBin.coerceAtMost(magnitudes.size - 1)) {
                sum += magnitudes[bin]
                count++
            }

            val avgMagnitude = if (count > 0) sum / count else 0.0

            val rawAmplitude = (avgMagnitude / 10000.0) * AMPLITUDE_SCALE
            bar.amplitude = rawAmplitude.coerceIn(0.0, 1.0)

            val dynamicSmoothFactor = if (bar.amplitude < 0.3) {
                SMOOTH_FACTOR * 1.6f
            } else if (bar.amplitude < 0.6) {
                SMOOTH_FACTOR * 1.2f
            } else {
                SMOOTH_FACTOR
            }

            bar.smoothAmplitude += (bar.amplitude - bar.smoothAmplitude) * dynamicSmoothFactor

            if (bar.smoothAmplitude < MIN_THRESHOLD) {
                bar.smoothAmplitude *= 0.6f
            }

            if (bar.isFeedbackFreq) {
                amplitudeHistory[bar.index].add(bar.smoothAmplitude)
                if (amplitudeHistory[bar.index].size > maxHistorySize) {
                    amplitudeHistory[bar.index].removeAt(0)
                }
            }
        }
    }

    private fun detectFeedback() {
        val currentTime = System.currentTimeMillis()
        detectedTones.clear()

        barsData.forEach { bar ->
            if (!bar.isFeedbackFreq) {
                bar.feedbackStartTime = null
                bar.isFeedback = false
                return@forEach
            }

            if (bar.smoothAmplitude > FEEDBACK_THRESHOLD) {
                if (bar.feedbackStartTime == null) {
                    bar.feedbackStartTime = currentTime
                }

                val persistenceTime = currentTime - (bar.feedbackStartTime ?: currentTime)

                val history = amplitudeHistory[bar.index]
                val isStable = if (history.size >= 15) {
                    val recent = history.takeLast(15)
                    val avg = recent.average()
                    val variance = recent.map { (it - avg).pow(2) }.average()
                    val minAmplitude = recent.minOrNull() ?: 0.0
                    val maxAmplitude = recent.maxOrNull() ?: 0.0
                    val range = maxAmplitude - minAmplitude

                    variance < VAR_THRESHOLD &&
                            avg > 0.75 &&
                            minAmplitude > 0.6 &&
                            range < 0.15
                } else false

                val neighborIndices = listOf(
                    bar.index - 3, bar.index - 2, bar.index - 1,
                    bar.index + 1, bar.index + 2, bar.index + 3
                ).filter { it in 0 until BAR_COUNT }

                val neighborAmplitudes = neighborIndices.map { barsData[it].smoothAmplitude }
                val maxNeighbor = neighborAmplitudes.maxOrNull() ?: 0.0
                val isLocalPeak = bar.smoothAmplitude > maxNeighbor * MIN_PEAK_RATIO

                val stabilityConfidence = if (history.size >= 10) {
                    val recentAvg = history.takeLast(10).average()
                    (recentAvg - 0.6).coerceIn(0.0, 0.3) / 0.3
                } else 0.0

                val peakConfidence = (bar.smoothAmplitude - maxNeighbor) / bar.smoothAmplitude
                val persistenceConfidence = min(persistenceTime / FEEDBACK_PERSISTENCE_MS.toDouble(), 1.0)

                val totalConfidence = (stabilityConfidence * 0.4 +
                        peakConfidence * 0.3 +
                        persistenceConfidence * 0.3)

                if (persistenceTime > FEEDBACK_PERSISTENCE_MS &&
                    isStable &&
                    isLocalPeak &&
                    totalConfidence > 0.65) {

                    bar.isFeedback = true

                    detectedTones.add(
                        DetectedTone(
                            frequency = bar.centerFreq,
                            amplitude = bar.smoothAmplitude,
                            barIndex = bar.index,
                            isFeedback = true,
                            persistenceMs = persistenceTime,
                            confidence = totalConfidence
                        )
                    )
                } else if (persistenceTime > FEEDBACK_PERSISTENCE_MS / 2 && totalConfidence > 0.4) {
                    detectedTones.add(
                        DetectedTone(
                            frequency = bar.centerFreq,
                            amplitude = bar.smoothAmplitude,
                            barIndex = bar.index,
                            isFeedback = false,
                            persistenceMs = persistenceTime,
                            confidence = totalConfidence
                        )
                    )
                }
            } else {
                if (bar.smoothAmplitude < FEEDBACK_THRESHOLD * 0.65) {
                    bar.feedbackStartTime = null
                    bar.isFeedback = false
                }
            }
        }

        detectedTones.sortByDescending { it.confidence * it.amplitude }
    }

    private fun updatePeaks() {
        barsData.forEach { bar ->
            if (bar.isFeedbackFreq) {
                if (bar.smoothAmplitude > bar.peakAmplitude) {
                    bar.peakAmplitude = bar.smoothAmplitude
                } else {
                    bar.peakAmplitude = maxOf(0.0, bar.peakAmplitude - peakDecayRate)
                }
            } else {
                bar.peakAmplitude = maxOf(0.0, bar.peakAmplitude - peakDecayRate * 2)
            }
        }
    }

    private fun fft(real: FloatArray, imag: FloatArray) {
        val n = real.size
        val bits = (ln(n.toDouble()) / ln(2.0)).toInt()

        val jIndices = IntArray(n)
        for (i in 0 until n) {
            var j = 0
            for (k in 0 until bits) {
                j = (j shl 1) or ((i shr k) and 1)
            }
            jIndices[i] = j
        }

        val tempReal = real.copyOf()
        val tempImag = imag.copyOf()
        for (i in 0 until n) {
            real[i] = tempReal[jIndices[i]]
            imag[i] = tempImag[jIndices[i]]
        }

        var size = 2
        while (size <= n) {
            val halfSize = size / 2
            val angleStep = (-2.0 * PI / size).toFloat()

            for (i in 0 until n step size) {
                for (j in 0 until halfSize) {
                    val angle = angleStep * j
                    val wReal = cos(angle)
                    val wImag = sin(angle)

                    val tReal = wReal * real[i + j + halfSize] - wImag * imag[i + j + halfSize]
                    val tImag = wReal * imag[i + j + halfSize] + wImag * real[i + j + halfSize]

                    real[i + j + halfSize] = real[i + j] - tReal
                    imag[i + j + halfSize] = imag[i + j] - tImag
                    real[i + j] += tReal
                    imag[i + j] += tImag
                }
            }
            size *= 2
        }
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        if (barsData.isEmpty()) return

        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)

        drawGrid(canvas)

        val barWidth = width / (BAR_COUNT * BAR_SPACING_FACTOR)
        val barSpacing = (width - barWidth * BAR_COUNT) / (BAR_COUNT + 1)

        val barGeometries = drawInactiveBars(canvas, barWidth, barSpacing)
        drawActiveBars(canvas, barGeometries)
        drawPeakIndicators(canvas, barGeometries)
        drawFeedbackIndicators(canvas, barGeometries)
        drawTonesLabels(canvas, barGeometries)
    }

    private fun drawGrid(canvas: Canvas) {
        val gridLevels = listOf(0.2f, 0.4f, 0.6f, 0.8f)
        gridLevels.forEach { level ->
            val y = height - (height * level)
            gridPaint.alpha = when {
                level == 0.6f -> 40
                level == 0.5f -> 30
                else -> 20
            }
            canvas.drawLine(0f, y, width.toFloat(), y, gridPaint)
        }

        val feedbackY = height - (height * FEEDBACK_THRESHOLD.toFloat())
        val feedbackLinePaint = Paint(gridPaint).apply {
            color = Colors.DANGER
            strokeWidth = 2f
            alpha = 100
            pathEffect = DashPathEffect(floatArrayOf(12f, 8f), 0f)
        }
        canvas.drawLine(0f, feedbackY, width.toFloat(), feedbackY, feedbackLinePaint)
    }

    private fun drawInactiveBars(canvas: Canvas, barWidth: Float, barSpacing: Float):
            List<Pair<BarData, RectF>> {

        return barsData.map { bar ->
            val barHeight = (bar.smoothAmplitude.pow(0.65) * height * 0.88).toFloat()
            val left = barSpacing + bar.index * (barWidth + barSpacing)
            val top = height - barHeight

            val rect = RectF(left, top.coerceAtMost(height.toFloat()), left + barWidth, height.toFloat())

            barInactivePaint.alpha = if (bar.isFeedbackFreq) 40 else 20
            canvas.drawRoundRect(rect, BAR_RADIUS, BAR_RADIUS, barInactivePaint)

            bar to rect
        }
    }

    private fun drawActiveBars(
        canvas: Canvas,
        barGeometries: List<Pair<BarData, RectF>>
    ) {
        barGeometries.forEach { (bar, rect) ->
            if (bar.smoothAmplitude > MIN_THRESHOLD) {
                val barColor = getBarColor(bar.smoothAmplitude, bar.isFeedback)
                val intensity = bar.smoothAmplitude.toFloat()

                if (bar.isFeedbackFreq) {
                    val glowIntensity = if (bar.isFeedback) 80 else 50
                    glowPaint.color = barColor
                    glowPaint.alpha = (intensity * glowIntensity).toInt().coerceIn(20, glowIntensity)
                    canvas.drawRoundRect(rect, BAR_RADIUS, BAR_RADIUS, glowPaint)
                }

                val barPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                    shader = LinearGradient(
                        0f, rect.top, 0f, rect.bottom,
                        adjustColorBrightness(barColor, 1.15f),
                        adjustColorBrightness(barColor, 0.7f),
                        Shader.TileMode.CLAMP
                    )
                    val alpha = if (bar.isFeedbackFreq) {
                        (intensity * 255).toInt().coerceIn(120, 255)
                    } else {
                        (intensity * 200).toInt().coerceIn(80, 200)
                    }
                    this.alpha = alpha
                }
                canvas.drawRoundRect(rect, BAR_RADIUS, BAR_RADIUS, barPaint)

                if (rect.height() > 20f && intensity > 0.3f) {
                    val highlightPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                        color = Color.WHITE
                        alpha = (intensity * 50).toInt().coerceIn(20, 50)
                    }
                    val highlightRect = RectF(rect.left + 2, rect.top + 2, rect.right - 2, rect.top + 4)
                    canvas.drawRoundRect(highlightRect, 2f, 2f, highlightPaint)
                }

                if (bar.isFeedback) {
                    val pulsePhase = (System.currentTimeMillis() % 1000) / 1000f
                    val pulseAlpha = (sin(pulsePhase * 2 * PI) * 40 + 60).toInt()

                    val pulsePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                        style = Paint.Style.STROKE
                        strokeWidth = 3f
                        color = Colors.FEEDBACK
                        alpha = pulseAlpha
                    }
                    canvas.drawRoundRect(
                        RectF(rect.left - 2, rect.top - 2, rect.right + 2, rect.bottom + 2),
                        BAR_RADIUS + 2, BAR_RADIUS + 2,
                        pulsePaint
                    )
                }
            }
        }
    }

    private fun drawPeakIndicators(
        canvas: Canvas,
        barGeometries: List<Pair<BarData, RectF>>
    ) {
        barGeometries.forEach { (bar, rect) ->
            if (bar.isFeedbackFreq && bar.peakAmplitude > MIN_THRESHOLD * 1.5) {
                val peakHeight = (bar.peakAmplitude.pow(0.65) * height * 0.88).toFloat()
                val peakY = height - peakHeight

                if (peakY < rect.top - 4f) {
                    peakLinePaint.color = getBarColor(bar.peakAmplitude, bar.isFeedback)
                    peakLinePaint.alpha = if (bar.isFeedback) 220 else 160
                    canvas.drawLine(
                        rect.left + 1,
                        peakY,
                        rect.right - 1,
                        peakY,
                        peakLinePaint
                    )
                }
            }
        }
    }

    private fun drawFeedbackIndicators(
        canvas: Canvas,
        barGeometries: List<Pair<BarData, RectF>>
    ) {
        barsData.filter { it.isFeedback }.forEach { bar ->
            val rect = barGeometries[bar.index].second

            feedbackIndicatorPaint.color = Colors.FEEDBACK
            feedbackIndicatorPaint.alpha = 200

            canvas.drawLine(
                rect.left + rect.width() / 2,
                rect.top - 10f,
                rect.left + rect.width() / 2,
                rect.top - 30f,
                feedbackIndicatorPaint
            )

            val warningPath = Path().apply {
                val cx = rect.left + rect.width() / 2
                val top = rect.top - 40f
                moveTo(cx, top)
                lineTo(cx - 8f, top + 12f)
                lineTo(cx + 8f, top + 12f)
                close()
            }

            val warningPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Colors.FEEDBACK
                style = Paint.Style.FILL
                alpha = 220
            }
            canvas.drawPath(warningPath, warningPaint)
        }
    }

    private fun drawTonesLabels(canvas: Canvas, barGeometries: List<Pair<BarData, RectF>>) {
        detectedTones.take(3).forEachIndexed { index, tone ->
            val rect = barGeometries[tone.barIndex].second

            val freqLabel = when {
                tone.frequency >= 1000 -> "%.1fk Hz".format(tone.frequency / 1000)
                else -> "%.0f Hz".format(tone.frequency)
            }

            val statusLabel = when {
                tone.isFeedback -> "ACOPLE (${(tone.confidence * 100).toInt()}%)"
                tone.persistenceMs > FEEDBACK_PERSISTENCE_MS / 2 -> "POSIBLE (${(tone.confidence * 100).toInt()}%)"
                else -> ""
            }

            val mainBounds = Rect()
            textPaint.getTextBounds(freqLabel, 0, freqLabel.length, mainBounds)

            val statusBounds = Rect()
            if (statusLabel.isNotEmpty()) {
                smallTextPaint.getTextBounds(statusLabel, 0, statusLabel.length, statusBounds)
            }

            val padding = 16f
            val rectWidth = max(mainBounds.width(), statusBounds.width()) + padding * 2
            val rectHeight = mainBounds.height() + statusBounds.height() + padding * 2.5f
            val centerX = rect.left + rect.width() / 2

            val labelTop = height * 0.08f + index * (rectHeight + 10f)
            val labelBottom = labelTop + rectHeight

            val bgPaint = if (tone.isFeedback) feedbackBgPaint else freqBgPaint
            canvas.drawRoundRect(
                centerX - rectWidth / 2,
                labelTop,
                centerX + rectWidth / 2,
                labelBottom,
                14f, 14f,
                bgPaint
            )

            val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                style = Paint.Style.STROKE
                strokeWidth = 2f
                color = getBarColor(tone.amplitude, tone.isFeedback)
                alpha = 180
            }
            canvas.drawRoundRect(
                centerX - rectWidth / 2,
                labelTop,
                centerX + rectWidth / 2,
                labelBottom,
                14f, 14f,
                borderPaint
            )

            canvas.drawText(
                freqLabel,
                centerX,
                labelTop + padding + mainBounds.height(),
                textPaint
            )

            if (statusLabel.isNotEmpty()) {
                val statusPaint = Paint(smallTextPaint).apply {
                    color = if (tone.isFeedback) Colors.FEEDBACK else Colors.WARNING
                    textSize = 18f
                }
                canvas.drawText(
                    statusLabel,
                    centerX,
                    labelTop + padding + mainBounds.height() + statusBounds.height() + 8f,
                    statusPaint
                )
            }

            if (rect.top > labelBottom + 10f) {
                connectorPaint.color = getBarColor(tone.amplitude, tone.isFeedback)
                connectorPaint.alpha = 160
                canvas.drawLine(
                    centerX, labelBottom,
                    centerX, rect.top,
                    connectorPaint
                )
            }
        }
    }


    private fun adjustColorBrightness(color: Int, factor: Float): Int {
        return Color.rgb(
            (Color.red(color) * factor).toInt().coerceIn(0, 255),
            (Color.green(color) * factor).toInt().coerceIn(0, 255),
            (Color.blue(color) * factor).toInt().coerceIn(0, 255)
        )
    }

    fun getFeedbackFrequencies(): List<Double> {
        return barsData.filter { it.isFeedback }.map { it.centerFreq }
    }

    fun hasActiveFeedback(): Boolean {
        return barsData.any { it.isFeedback }
    }

    fun reset() {
        barsData.forEach { bar ->
            bar.amplitude = 0.0
            bar.smoothAmplitude = 0.0
            bar.peakAmplitude = 0.0
            bar.feedbackStartTime = null
            bar.isFeedback = false
        }
        detectedTones.clear()
        amplitudeHistory.forEach { it.clear() }
        primaryFreq = null
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
    }
}