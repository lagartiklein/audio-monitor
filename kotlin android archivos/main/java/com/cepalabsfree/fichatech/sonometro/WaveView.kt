package com.cepalabsfree.fichatech.sonometro

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.*
import android.os.Build
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.animation.DecelerateInterpolator
import kotlin.math.*

class WaveView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    init {
        isFocusable = true
        isFocusableInTouchMode = true
        isClickable = true
        isLongClickable = true
    }

    enum class ViewMode {
        WAVEFORM,
        SPECTRUM,
        OSCILLOSCOPE,
        MINIMAL
    }

    private companion object {
        const val BUFFER_SIZE = 150
        const val ANIMATION_DURATION = 80L
        const val PEAK_DECAY_RATE = 0.95f
        const val SMOOTHING_FACTOR = 6f
        const val MIN_POINTS_TO_DRAW = 2
        const val AVG_SAMPLE_SIZE = 30
        const val MIN_BUFFER_FOR_AVG = 10

        // Padding minimalista
        const val PADDING = 40f
        const val PANEL_HEIGHT = 50f

        // Paleta minimalista monocromática
        val COLOR_BG = Color.parseColor("#000000")
        val COLOR_GRID = Color.parseColor("#0A1A1A")
        val COLOR_LINE = Color.parseColor("#FFFFFF")
        val COLOR_LINE_DIM = Color.parseColor("#808080")
        val COLOR_TEXT = Color.parseColor("#FFFFFF")
        val COLOR_TEXT_DIM = Color.parseColor("#606060")
        val COLOR_ACCENT = Color.parseColor("#FFFFFF")

        val DB_LEVELS = floatArrayOf(120f, 90f, 60f, 30f, 0f)
    }

    private var currentViewMode = ViewMode.WAVEFORM
    private var viewModeChangedListener: ((ViewMode) -> Unit)? = null
    private var touchEnabled = true

    private val waveBuffer = FloatArray(BUFFER_SIZE)
    private var bufferIndex = 0
    private var bufferCount = 0

    private var currentDisplayValue = 0f
    private var targetDisplayValue = 0f
    private val smoothingAnimator = ValueAnimator().apply {
        duration = ANIMATION_DURATION
        interpolator = DecelerateInterpolator()
        addUpdateListener { animator ->
            currentDisplayValue = animator.animatedValue as Float
            invalidate()
        }
    }

    private var peakValue = 0f
    private var peakDecay = 0f

    private val wavePath = Path()
    private val smoothPoints = ArrayList<PointF>(BUFFER_SIZE)

    private var deviceModel = Build.MODEL
    private var calibrationOffset = 94.0
    private var audioSource = "UNPROCESSED"
    private var isMeasuring = false
    private var measurementStartTime = 0L

    // Paints minimalistas
    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_BG
        style = Paint.Style.FILL
    }

    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_GRID
        strokeWidth = 1f
        style = Paint.Style.STROKE
        alpha = 40
    }

    private val wavePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_LINE
        style = Paint.Style.STROKE
        strokeWidth = 2f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_TEXT
        textSize = 72f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)
        letterSpacing = -0.05f
    }

    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_TEXT_DIM
        textSize = 14f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)
        letterSpacing = 0.1f
    }

    private val peakPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_LINE_DIM
        strokeWidth = 1f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(6f, 6f), 0f)
    }

    private val barPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private var fftProcessor: FFTProcessor? = null

    // API pública
    fun setViewMode(mode: ViewMode) {
        currentViewMode = mode
        viewModeChangedListener?.invoke(mode)
        invalidate()
    }

    fun getCurrentViewMode(): ViewMode = currentViewMode

    fun setOnViewModeChangedListener(listener: (ViewMode) -> Unit) {
        viewModeChangedListener = listener
    }

    fun enableTouchModeSwitching(enabled: Boolean) {
        touchEnabled = enabled
    }

    fun nextViewMode() {
        val modes = ViewMode.values()
        val currentIndex = modes.indexOf(currentViewMode)
        val nextIndex = (currentIndex + 1) % modes.size
        setViewMode(modes[nextIndex])
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!touchEnabled) return super.onTouchEvent(event)

        when (event.action) {
            MotionEvent.ACTION_DOWN -> return true
            MotionEvent.ACTION_UP -> {
                nextViewMode()
                performClick()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    fun setDeviceInfo(model: String, calibration: Double, source: String, measuring: Boolean = false) {
        this.deviceModel = model
        this.calibrationOffset = calibration
        this.audioSource = source
        this.isMeasuring = measuring

        if (measuring && measurementStartTime == 0L) {
            measurementStartTime = System.currentTimeMillis()
        } else if (!measuring) {
            measurementStartTime = 0L
        }
        invalidate()
    }

    fun setMeasurementActive(isActive: Boolean) {
        this.isMeasuring = isActive
        if (isActive && measurementStartTime == 0L) {
            measurementStartTime = System.currentTimeMillis()
        } else if (!isActive) {
            measurementStartTime = 0L
        }
        invalidate()
    }

    fun updateRawBuffer(buffer: ShortArray, size: Int, calibrationOffset: Double = 94.0) {
        if (fftProcessor == null) {
            fftProcessor = FFTProcessor(2048)
        }

        val dbValue = fftProcessor!!.calculateWeightedDB(buffer, size) + (calibrationOffset - 94.0)
        val dbFloat = dbValue.coerceIn(0.0, 120.0).toFloat()

        waveBuffer[bufferIndex] = dbFloat
        bufferIndex = (bufferIndex + 1) % BUFFER_SIZE
        if (bufferCount < BUFFER_SIZE) bufferCount++

        targetDisplayValue = dbFloat
        smoothingAnimator.cancel()
        smoothingAnimator.setFloatValues(currentDisplayValue, targetDisplayValue)
        smoothingAnimator.start()

        updatePeakValues(dbFloat)
        invalidate()
    }

    fun updateDecibelValues(dbValue: Double) {
        val dbFloat = dbValue.coerceIn(0.0, 120.0).toFloat()

        waveBuffer[bufferIndex] = dbFloat
        bufferIndex = (bufferIndex + 1) % BUFFER_SIZE
        if (bufferCount < BUFFER_SIZE) bufferCount++

        targetDisplayValue = dbFloat
        smoothingAnimator.cancel()
        smoothingAnimator.setFloatValues(currentDisplayValue, targetDisplayValue)
        smoothingAnimator.start()

        updatePeakValues(dbFloat)
        invalidate()
    }

    private fun updatePeakValues(dbFloat: Float) {
        if (dbFloat > peakValue) {
            peakValue = dbFloat
            peakDecay = dbFloat
        } else {
            peakDecay *= PEAK_DECAY_RATE
            if (peakDecay < peakValue * 0.7f) {
                peakValue = dbFloat
                peakDecay = dbFloat
            }
        }
    }

    fun reset() {
        waveBuffer.fill(0f)
        bufferIndex = 0
        bufferCount = 0
        currentDisplayValue = 0f
        targetDisplayValue = 0f
        peakValue = 0f
        peakDecay = 0f
        measurementStartTime = 0L
        smoothingAnimator.cancel()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val w = width.toFloat()
        val h = height.toFloat()

        canvas.drawRect(0f, 0f, w, h, bgPaint)

        val area = RectF(PADDING, PADDING, w - PADDING, h - PANEL_HEIGHT - PADDING)

        when (currentViewMode) {
            ViewMode.WAVEFORM -> drawWaveformMode(canvas, area, w, h)
            ViewMode.SPECTRUM -> drawSpectrumMode(canvas, area, w, h)
            ViewMode.OSCILLOSCOPE -> drawOscilloscopeMode(canvas, area, w, h)
            ViewMode.MINIMAL -> drawMinimalMode(canvas, area, w, h)
        }

        drawFooter(canvas, w, h)
    }

    // MODO WAVEFORM: Solo línea de onda, sin relleno
    private fun drawWaveformMode(canvas: Canvas, area: RectF, w: Float, h: Float) {
        drawMinimalGrid(canvas, area)

        if (bufferCount > MIN_POINTS_TO_DRAW) {
            drawWaveformLine(canvas, area)
        }

        if (peakDecay > 10f) {
            drawPeakLine(canvas, area)
        }
    }

    // MODO SPECTRUM: Barras verticales simples
    private fun drawSpectrumMode(canvas: Canvas, area: RectF, w: Float, h: Float) {
        if (bufferCount < MIN_POINTS_TO_DRAW) return

        val barCount = 24
        val spacing = 4f
        val totalSpacing = spacing * (barCount - 1)
        val barWidth = (area.width() - totalSpacing) / barCount

        for (i in 0 until barCount) {
            val sampleIndex = (i * bufferCount / barCount).coerceAtMost(bufferCount - 1)
            val bufferIdx = (bufferIndex - sampleIndex - 1 + BUFFER_SIZE) % BUFFER_SIZE
            val value = waveBuffer[bufferIdx].coerceIn(0f, 120f)

            val normalizedValue = (value / 120f).coerceIn(0f, 1f)
            val barHeight = area.height() * normalizedValue * 0.9f

            val left = area.left + i * (barWidth + spacing)
            val top = area.bottom - barHeight
            val right = left + barWidth

            // Opacidad basada en altura
            val alpha = (normalizedValue * 255).toInt().coerceIn(50, 255)
            barPaint.color = Color.argb(alpha, 255, 255, 255)

            canvas.drawRect(left, top, right, area.bottom, barPaint)
        }

        // Label del modo
        labelPaint.textAlign = Paint.Align.LEFT
        canvas.drawText("SPECTRUM", PADDING, PADDING + 20f, labelPaint)
    }

    // MODO OSCILLOSCOPE: Línea centrada
    private fun drawOscilloscopeMode(canvas: Canvas, area: RectF, w: Float, h: Float) {
        drawMinimalGrid(canvas, area)

        // Línea central
        val centerY = area.centerY()
        canvas.drawLine(area.left, centerY, area.right, centerY, gridPaint)

        if (bufferCount < MIN_POINTS_TO_DRAW) return

        val pointsToShow = min(bufferCount, 100)
        val path = Path()

        for (i in 0 until pointsToShow) {
            val bufferIdx = (bufferIndex - pointsToShow + i + BUFFER_SIZE) % BUFFER_SIZE
            val x = area.left + (i.toFloat() / pointsToShow) * area.width()

            val dbValue = waveBuffer[bufferIdx].coerceIn(0f, 120f)
            val normalizedY = 0.5f - (dbValue - 60f) / 240f
            val y = area.top + area.height() * normalizedY.coerceIn(0f, 1f)

            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }

        wavePaint.alpha = 255
        canvas.drawPath(path, wavePaint)

        labelPaint.textAlign = Paint.Align.LEFT
        canvas.drawText("OSCILLOSCOPE", PADDING, PADDING + 20f, labelPaint)
    }

    // MODO MINIMAL: Solo número grande
    private fun drawMinimalMode(canvas: Canvas, area: RectF, w: Float, h: Float) {
        // Número central gigante
        textPaint.textSize = 140f
        textPaint.textAlign = Paint.Align.CENTER

        val centerX = w / 2
        val centerY = area.centerY() + 50f

        canvas.drawText("${currentDisplayValue.toInt()}", centerX, centerY, textPaint)

        labelPaint.textAlign = Paint.Align.CENTER
        canvas.drawText("dB SPL", centerX, centerY + 30f, labelPaint)

        // Peak debajo
        if (peakValue > 0) {
            labelPaint.textSize = 12f
            canvas.drawText("PEAK ${peakValue.toInt()} dB", centerX, centerY + 60f, labelPaint)
            labelPaint.textSize = 14f
        }

        // Resetear tamaño
        textPaint.textSize = 72f
    }

    // Helpers
    private fun drawMinimalGrid(canvas: Canvas, area: RectF) {
        // Solo 3 líneas horizontales
        val lines = 5
        for (i in 0..lines) {
            val y = area.top + (area.height() * i / lines)
            canvas.drawLine(area.left, y, area.right, y, gridPaint)
        }
    }

    private fun drawWaveformLine(canvas: Canvas, area: RectF) {
        val pointsToShow = min(bufferCount, 60)
        if (pointsToShow < MIN_POINTS_TO_DRAW) return

        generateSmoothPoints(pointsToShow, area)

        if (smoothPoints.size < MIN_POINTS_TO_DRAW) return

        wavePath.reset()
        val firstPoint = smoothPoints[0]
        wavePath.moveTo(firstPoint.x, firstPoint.y)

        for (i in 0 until smoothPoints.size - 1) {
            val p0 = smoothPoints[max(i - 1, 0)]
            val p1 = smoothPoints[i]
            val p2 = smoothPoints[i + 1]
            val p3 = smoothPoints[min(i + 2, smoothPoints.size - 1)]

            val cp1x = p1.x + (p2.x - p0.x) / SMOOTHING_FACTOR
            val cp1y = p1.y + (p2.y - p0.y) / SMOOTHING_FACTOR
            val cp2x = p2.x - (p3.x - p1.x) / SMOOTHING_FACTOR
            val cp2y = p2.y - (p3.y - p1.y) / SMOOTHING_FACTOR

            wavePath.cubicTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
        }

        // Intensidad basada en volumen
        val intensity = (currentDisplayValue / 120f).coerceIn(0.3f, 1f)
        wavePaint.alpha = (intensity * 255).toInt()
        canvas.drawPath(wavePath, wavePaint)
    }

    private fun generateSmoothPoints(pointsToShow: Int, area: RectF) {
        smoothPoints.clear()
        for (i in 0 until pointsToShow) {
            val bufferIdx = (bufferIndex - pointsToShow + i + BUFFER_SIZE) % BUFFER_SIZE
            val x = area.right - ((pointsToShow - i - 1).toFloat() / pointsToShow) * area.width()
            val dbValue = waveBuffer[bufferIdx].coerceIn(0f, 120f)
            val normalizedY = 1f - (dbValue / 120f)
            val y = area.top + (area.height() * normalizedY)
            smoothPoints.add(PointF(x, y))
        }
    }

    private fun drawPeakLine(canvas: Canvas, area: RectF) {
        val normalizedY = 1f - (peakDecay / 120f)
        val y = area.top + (area.height() * normalizedY)
        peakPaint.alpha = (180 * (peakDecay / peakValue)).toInt().coerceIn(30, 180)
        canvas.drawLine(area.left, y, area.right, y, peakPaint)
    }

    private fun drawFooter(canvas: Canvas, w: Float, h: Float) {
        val y = h - PANEL_HEIGHT + 10f

        labelPaint.textAlign = Paint.Align.LEFT
        labelPaint.textSize = 11f
        canvas.drawText(deviceModel.uppercase(), PADDING, y, labelPaint)

        labelPaint.textAlign = Paint.Align.CENTER
        val duration = if (isMeasuring && measurementStartTime > 0) {
            System.currentTimeMillis() - measurementStartTime
        } else 0L
        canvas.drawText(formatDuration(duration), w / 2, y, labelPaint)

        labelPaint.textAlign = Paint.Align.RIGHT
        val modeText = when (currentViewMode) {
            ViewMode.WAVEFORM -> "WAVE"
            ViewMode.SPECTRUM -> "SPEC"
            ViewMode.OSCILLOSCOPE -> "SCOPE"
            ViewMode.MINIMAL -> "MIN"
        }
        canvas.drawText(modeText, w - PADDING, y, labelPaint)

        labelPaint.textSize = 14f
    }

    private fun formatDuration(millis: Long): String {
        val seconds = (millis / 1000) % 60
        val minutes = (millis / (1000 * 60)) % 60
        val hours = millis / (1000 * 60 * 60)

        return when {
            hours > 0 -> "%02d:%02d:%02d".format(hours, minutes, seconds)
            minutes > 0 -> "%02d:%02d".format(minutes, seconds)
            else -> "%02ds".format(seconds)
        }
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        smoothingAnimator.cancel()
    }
}