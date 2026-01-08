package com.cepalabsfree.fichatech.sonometro

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import kotlin.math.*

/**
 * Ecualizador FFT moderno con ondas suaves y diseño atractivo
 * Versión mejorada con filtro de ruido adaptativo inteligente
 */
class EqualizerFFTView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    // === CONFIGURACIÓN DE AUDIO ===
    private val sampleRate = 44100f
    private val fftSize = 2048
    private val minFreq = 40f
    private val maxFreq = 20000f

    // === DATOS DE FFT ===
    private var currentMagnitudes = FloatArray(fftSize / 2)
    private var smoothedMagnitudes = FloatArray(fftSize / 2)

    // === FRECUENCIAS ===
    private val displayFrequencies = listOf(
        40, 80, 200, 500, 1000, 2000, 5000, 10000, 16000, 20000
    )

    private val curvePoints = 120

    // === COLORES MODERNOS ===
    private val bgColorStart = Color.parseColor("#0F1419")
    private val bgColorEnd = Color.parseColor("#1A1F2E")

    private val waveColors = intArrayOf(
        Color.parseColor("#00F5FF"),
        Color.parseColor("#00D9FF"),
        Color.parseColor("#00B8FF"),
        Color.parseColor("#4D94FF"),
        Color.parseColor("#8B6CFF"),
        Color.parseColor("#C44DFF"),
        Color.parseColor("#FF3D9D")
    )

    // === PARÁMETROS MEJORADOS ===
    private val smoothingFactor = 0.25f // MEJORADO: más suavizado
    private var maxDb = -40f
    private var minDb = -100f

    // Filtro de ruido adaptativo mejorado
    private var noiseFloor = -85f // MEJORADO: más estricto
    private val noiseGateThreshold = -78f // MEJORADO: más estricto
    private var adaptiveNoiseFloor = FloatArray(fftSize / 2) { -85f }
    private val noiseAdaptRate = 0.002f // MEJORADO: adaptación más precisa

    private var isActive = true

    // === PAINTS ===
    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        setColor(Color.argb(25, 255, 255, 255))
        strokeWidth = 1f
        style = Paint.Style.STROKE
    }

    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        setColor(Color.argb(200, 255, 255, 255))
        textSize = 26f
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }

    private val waveLinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val waveFillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        maskFilter = BlurMaskFilter(15f, BlurMaskFilter.Blur.NORMAL)
    }

    private val labelBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    // === MÉTODOS PÚBLICOS ===

    fun updateFFT(magnitudes: FloatArray) {
        if (!isActive) return

        val size = minOf(magnitudes.size, currentMagnitudes.size)
        System.arraycopy(magnitudes, 0, currentMagnitudes, 0, size)

        // ✅ MEJORADO: Filtro de ruido adaptativo con histéresis
        for (i in 0 until size) {
            val rawMag = currentMagnitudes[i]

            val currentDb = if (rawMag > 0f) 20f * log10(rawMag) else -120f

            // Actualizar piso de ruido con histéresis
            if (currentDb < adaptiveNoiseFloor[i]) {
                // Ruido: actualización rápida hacia abajo
                adaptiveNoiseFloor[i] = adaptiveNoiseFloor[i] * 0.99f + currentDb * 0.01f
            } else {
                // Señal: actualización muy lenta hacia arriba
                adaptiveNoiseFloor[i] = adaptiveNoiseFloor[i] + noiseAdaptRate * (currentDb - adaptiveNoiseFloor[i])
            }

            // Noise gate con transición suave
            val gateThreshold = adaptiveNoiseFloor[i] + 18f
            val gatedMag = if (currentDb > gateThreshold) {
                val distance = currentDb - gateThreshold
                val gainReduction = if (distance < 10f) {
                    (distance / 10f).pow(0.7f)
                } else {
                    1f
                }
                rawMag * gainReduction
            } else {
                rawMag * 0.05f
            }

            smoothedMagnitudes[i] = smoothedMagnitudes[i] * (1f - smoothingFactor) +
                    gatedMag * smoothingFactor
        }

        invalidate()
    }

    fun setMeasurementEnabled(enabled: Boolean) {
        isActive = enabled
        if (!enabled) reset()
        invalidate()
    }

    fun reset() {
        currentMagnitudes.fill(0f)
        smoothedMagnitudes.fill(0f)
        adaptiveNoiseFloor.fill(-85f)
        maxDb = -40f
        minDb = -100f
        invalidate()
    }

    fun setSensitivity(sensitivity: Float) {
        noiseFloor = -85f - (sensitivity * 15f)
    }

    // === DIBUJO ===

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        drawBackground(canvas)
        drawGrid(canvas)
        updateDynamicRange()
        drawSpectrum(canvas)
        drawFrequencyLabels(canvas)
    }

    private fun drawBackground(canvas: Canvas) {
        bgPaint.shader = LinearGradient(
            0f, 0f, 0f, height.toFloat(),
            bgColorStart, bgColorEnd,
            Shader.TileMode.CLAMP
        )
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)

        bgPaint.shader = RadialGradient(
            width / 2f, height / 2.5f, width * 0.7f,
            Color.argb(12, 80, 120, 255),
            Color.TRANSPARENT,
            Shader.TileMode.CLAMP
        )
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)
    }

    private fun drawGrid(canvas: Canvas) {
        val margin = 50f
        val gridStep = (height - margin * 2) / 4f

        for (i in 0..4) {
            val y = margin + i * gridStep
            gridPaint.alpha = if (i == 4) 40 else 20
            canvas.drawLine(margin, y, width - margin, y, gridPaint)
        }

        val gridFrequencies = listOf(40, 80, 200, 500, 1000, 2000, 5000, 10000, 16000)
        gridFrequencies.forEach { freq ->
            val x = freqToX(freq.toFloat())
            if (x >= margin && x <= width - margin) {
                gridPaint.alpha = 18
                canvas.drawLine(x, margin, x, height - margin, gridPaint)
            }
        }
    }

    private fun updateDynamicRange() {
        var currentMaxValue = 0f

        for (i in smoothedMagnitudes.indices) {
            if (smoothedMagnitudes[i] > currentMaxValue &&
                smoothedMagnitudes[i] > adaptiveNoiseFloor[i] * 2f) {
                currentMaxValue = smoothedMagnitudes[i]
            }
        }

        if (currentMaxValue > 0f) {
            val currentDb = 20f * log10(currentMaxValue)
            val targetMaxDb = (currentDb + 15f).coerceIn(-35f, 0f)
            maxDb = maxDb * 0.92f + targetMaxDb * 0.08f

            val contentDynamicRange = if (currentDb > -50f) 60f else 50f
            minDb = maxDb - contentDynamicRange
        }
    }

    private fun drawSpectrum(canvas: Canvas) {
        val margin = 50f
        val plotHeight = height - margin * 2
        val plotWidth = width - margin * 2

        val points = mutableListOf<PointF>()
        var currentMaxValue = 0f

        for (i in 0 until curvePoints) {
            val t = i / (curvePoints - 1f)
            val freq = minFreq * ((maxFreq / minFreq).pow(t))

            val magnitude = getMagnitudeAt(freq)
            currentMaxValue = maxOf(currentMaxValue, magnitude)

            val db = if (magnitude > 0f) 20f * log10(magnitude) else minDb

            val x = freqToX(freq)
            val normalizedDb = ((db - minDb) / (maxDb - minDb)).coerceIn(0f, 1f)
            val y = (height - margin) - (normalizedDb * plotHeight * 0.85f)

            points.add(PointF(x, y))
        }

        if (points.size < 2) return

        val smoothPoints = smoothCurve(points)

        drawFill(canvas, smoothPoints, margin)
        drawLine(canvas, smoothPoints)
    }

    private fun drawFill(canvas: Canvas, points: List<PointF>, margin: Float) {
        val fillPath = Path()
        fillPath.moveTo(points[0].x, height - margin)

        points.forEach { fillPath.lineTo(it.x, it.y) }
        fillPath.lineTo(points.last().x, height - margin)
        fillPath.close()

        waveFillPaint.shader = LinearGradient(
            0f, margin, 0f, height - margin,
            Color.argb(70, 0, 150, 255),
            Color.argb(10, 50, 80, 180),
            Shader.TileMode.CLAMP
        )
        canvas.drawPath(fillPath, waveFillPaint)
    }

    private fun drawLine(canvas: Canvas, points: List<PointF>) {
        val linePath = Path()
        linePath.moveTo(points[0].x, points[0].y)
        points.forEach { linePath.lineTo(it.x, it.y) }

        waveLinePaint.shader = LinearGradient(
            50f, 0f, width - 50f, 0f,
            waveColors,
            null,
            Shader.TileMode.CLAMP
        )
        canvas.drawPath(linePath, waveLinePaint)
    }

    private fun drawFrequencyLabels(canvas: Canvas) {
        val margin = 50f
        var previousX = -1000f

        displayFrequencies.forEach { freq ->
            val x = freqToX(freq.toFloat())

            if (x > margin + 10f && x < width - margin - 10f) {
                val label = formatFrequency(freq.toFloat())

                val bounds = Rect()
                textPaint.getTextBounds(label, 0, label.length, bounds)
                val labelWidth = bounds.width() + 20f

                if (x - previousX > labelWidth * 0.8f) {
                    val padding = 10f

                    labelBgPaint.shader = LinearGradient(
                        x, height - 45f, x, height - 15f,
                        Color.argb(130, 30, 40, 60),
                        Color.argb(80, 20, 30, 50),
                        Shader.TileMode.CLAMP
                    )

                    canvas.drawRoundRect(
                        x - bounds.width() / 2 - padding,
                        height - 45f,
                        x + bounds.width() / 2 + padding,
                        height - 15f,
                        12f, 12f,
                        labelBgPaint
                    )

                    textPaint.textSize = 24f
                    canvas.drawText(label, x, height - 22f, textPaint)

                    previousX = x
                }
            }
        }
    }

    // === UTILIDADES ===

    private fun getMagnitudeAt(freq: Float): Float {
        if (freq < minFreq || freq > maxFreq) return 0f

        val bin = (freq * fftSize / sampleRate).toInt()
        if (bin < 0 || bin >= smoothedMagnitudes.size) return 0f

        val binFloat = freq * fftSize / sampleRate
        val frac = binFloat - bin

        val mag1 = smoothedMagnitudes[bin]
        val mag2 = if (bin + 1 < smoothedMagnitudes.size) {
            smoothedMagnitudes[bin + 1]
        } else mag1

        return mag1 * (1f - frac) + mag2 * frac
    }

    private fun freqToX(freq: Float): Float {
        val margin = 50f
        val plotWidth = width - margin * 2
        val clampedFreq = freq.coerceIn(minFreq, maxFreq)
        val t = (ln(clampedFreq) - ln(minFreq)) / (ln(maxFreq) - ln(minFreq))
        return margin + t * plotWidth
    }

    private fun smoothCurve(points: List<PointF>): List<PointF> {
        if (points.size < 4) return points

        val result = mutableListOf<PointF>()
        result.add(points[0])

        for (i in 0 until points.size - 1) {
            val p0 = points[maxOf(0, i - 1)]
            val p1 = points[i]
            val p2 = points[i + 1]
            val p3 = points[minOf(points.size - 1, i + 2)]

            for (t in 0..3) {
                val tt = t / 3f
                val tt2 = tt * tt
                val tt3 = tt2 * tt

                val q1 = -tt3 + 2f * tt2 - tt
                val q2 = 3f * tt3 - 5f * tt2 + 2f
                val q3 = -3f * tt3 + 4f * tt2 + tt
                val q4 = tt3 - tt2

                val x = 0.5f * (p0.x * q1 + p1.x * q2 + p2.x * q3 + p3.x * q4)
                val y = 0.5f * (p0.y * q1 + p1.y * q2 + p2.y * q3 + p3.y * q4)

                result.add(PointF(x, y))
            }
        }

        result.add(points.last())
        return result
    }

    private fun formatFrequency(freq: Float): String {
        return when {
            freq >= 1000f -> {
                val k = freq / 1000f
                if (k == k.toInt().toFloat()) "${k.toInt()}k" else "%.1fk".format(k)
            }
            else -> "${freq.toInt()}"
        }
    }

    data class PointF(val x: Float, val y: Float)
}