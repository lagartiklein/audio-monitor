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
        // ✅ AGREGAR ESTO: Hacer la vista enfocable y clickeable
        isFocusable = true
        isFocusableInTouchMode = true
        isClickable = true
        isLongClickable = true
    }
    // === ENUM PARA MODOS DE VISTA ===
    enum class ViewMode {
        WAVEFORM,       // Vista actual de onda
        COMPRESSOR,     // Vista de compresión
        SPECTRUM,       // Vista de espectro
        OSCILLOSCOPE    // Vista de osciloscopio
    }

    // === CONFIGURACIÓN OPTIMIZADA ===
    private companion object {
        const val BUFFER_SIZE = 150
        const val ANIMATION_DURATION = 80L
        const val PEAK_DECAY_RATE = 0.95f
        const val SMOOTHING_FACTOR = 6f
        const val MIN_POINTS_TO_DRAW = 2
        const val AVG_SAMPLE_SIZE = 30
        const val MIN_BUFFER_FOR_AVG = 10

        // Padding
        const val PADDING_LEFT = 30f
        const val PADDING_RIGHT = 30f
        const val PADDING_TOP = 30f
        const val PADDING_BOTTOM = 70f

        // Colores optimizados
        val COLOR_BACKGROUND_TOP = Color.parseColor("#0D1117")
        val COLOR_BACKGROUND_BOTTOM = Color.parseColor("#000000")
        val COLOR_GRID = Color.parseColor("#1A334D5B")
        val COLOR_CENTER_LINE = Color.parseColor("#334A6572")
        val COLOR_PEAK = Color.parseColor("#FFD54F")
        val COLOR_TEXT_PRIMARY = Color.parseColor("#FFFFFF")
        val COLOR_TEXT_SECONDARY = Color.parseColor("#80FFFFFF")

        // Colores para panel inferior
        val COLOR_PANEL_BG = Color.parseColor("#1A1F2E")
        val COLOR_PANEL_BORDER = Color.parseColor("#334A6572")
        val COLOR_INFO_LABEL = Color.parseColor("#80FFFFFF")
        val COLOR_INFO_VALUE = Color.parseColor("#00D9FF")

        val DB_LEVELS = floatArrayOf(120f, 90f, 60f, 30f, 0f)
    }

    // === VARIABLES PARA MODOS DE VISTA ===
    private var currentViewMode = ViewMode.WAVEFORM
    private var viewModeChangedListener: ((ViewMode) -> Unit)? = null
    private var touchEnabled = true

    // === BUFFER CIRCULAR ===
    private val waveBuffer = FloatArray(BUFFER_SIZE)
    private var bufferIndex = 0
    private var bufferCount = 0

    // === DETECCIÓN DE TRANSITORIOS ===
    private data class TransientEvent(
        val dbValue: Float,
        val timestamp: Long,
        val attack: Float
    )
    private val transientHistory = mutableListOf<TransientEvent>()
    private var lastDbValue = 0f
    private var lastUpdateTime = 0L

    // === ANIMACIÓN SUAVE ===
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

    // === DETECCIÓN DE PICOS ===
    private var peakValue = 0f
    private var peakDecay = 0f

    // === PATHS REUTILIZABLES ===
    private val wavePath = Path()
    private val fillPath = Path()
    private val smoothPoints = ArrayList<PointF>(BUFFER_SIZE)

    // === GRADIENTES CACHEADOS ===
    private var cachedBgGradient: LinearGradient? = null
    private var lastWidth = 0f
    private var lastHeight = 0f

    // Info del dispositivo
    private var deviceModel = Build.MODEL
    private var calibrationOffset = 94.0
    private var audioSource = "UNPROCESSED"
    private var measurementDuration = 0L
    private var measurementStartTime = 0L
    private var isMeasuring = false

    // === PAINTS OPTIMIZADOS ===
    private val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        isDither = true
    }

    private val wavePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        isDither = true
    }

    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        isDither = true
    }

    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_GRID
        strokeWidth = 1f
        style = Paint.Style.STROKE
    }

    private val centerLinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_CENTER_LINE
        strokeWidth = 2f
        style = Paint.Style.STROKE
    }

    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_TEXT_PRIMARY
        textSize = 56f
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        isDither = true
    }

    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_TEXT_SECONDARY
        textSize = 24f
        isDither = true
    }

    private val smallLabelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(96, 255, 255, 255)
        textSize = 20f
        isDither = true
    }

    private val peakPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_PEAK
        strokeWidth = 3f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(8f, 4f), 0f)
    }

    private val transientPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#FF5252")
        strokeWidth = 2f
        style = Paint.Style.STROKE
    }

    // Paints para panel inferior
    private val panelBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_PANEL_BG
        style = Paint.Style.FILL
    }

    private val panelBorderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_PANEL_BORDER
        strokeWidth = 1f
        style = Paint.Style.STROKE
    }

    private val infoPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_INFO_LABEL
        textSize = 18f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)
        isDither = true
    }

    private val infoValuePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = COLOR_INFO_VALUE
        textSize = 18f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
        isDither = true
    }

    // Paints para modos especiales
    private val compressorPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#4CAF50")
        strokeWidth = 3f
        style = Paint.Style.STROKE
    }

    private val spectrumBarPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val oscilloscopePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#00FFAA")
        strokeWidth = 2f
        style = Paint.Style.STROKE
    }

    // === PROCESADOR FFT (OPCIONAL) ===
    private var fftProcessor: FFTProcessor? = null

    // === MAPEO DE COLORES OPTIMIZADO ===
    private data class ColorRange(val threshold: Float, val color: Int)

    private val colorRanges = arrayOf(
        ColorRange(100f, Color.parseColor("#FF5252")),
        ColorRange(85f, Color.parseColor("#FF6E40")),
        ColorRange(70f, Color.parseColor("#FFB74D")),
        ColorRange(50f, Color.parseColor("#FFD54F")),
        ColorRange(30f, Color.parseColor("#66BB6A")),
        ColorRange(0f, Color.parseColor("#42A5F5"))
    )

    // === API PÚBLICA PARA MODOS DE VISTA ===
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

    fun previousViewMode() {
        val modes = ViewMode.values()
        val currentIndex = modes.indexOf(currentViewMode)
        val prevIndex = (currentIndex - 1 + modes.size) % modes.size
        setViewMode(modes[prevIndex])
    }

    // === GESTIÓN DE TACTIL ===
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!touchEnabled) return super.onTouchEvent(event)

        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                // Cambiar color o feedback visual opcional
                return true
            }
            MotionEvent.ACTION_UP -> {
                // Cambiar al siguiente modo
                nextViewMode()
                // Forzar redibujado
                invalidate()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun getColorForDb(db: Float): Int {
        for (range in colorRanges) {
            if (db >= range.threshold) return range.color
        }
        return colorRanges.last().color
    }

    private fun createGradientForDb(db: Float, height: Float): LinearGradient {
        val color = getColorForDb(db)
        val alpha30 = Color.argb(77, Color.red(color), Color.green(color), Color.blue(color))
        val alpha00 = Color.argb(0, Color.red(color), Color.green(color), Color.blue(color))

        return LinearGradient(
            0f, 0f, 0f, height,
            intArrayOf(alpha30, alpha00),
            floatArrayOf(0f, 1f),
            Shader.TileMode.CLAMP
        )
    }

    // Setters para información
    fun setDeviceInfo(
        model: String,
        calibration: Double,
        source: String,
        measuring: Boolean = false
    ) {
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

    // === API PÚBLICA ===

    fun updateRawBuffer(buffer: ShortArray, size: Int, calibrationOffset: Double = 94.0) {
        if (fftProcessor == null) {
            fftProcessor = FFTProcessor(2048)
        }

        val dbValue = fftProcessor!!.calculateWeightedDB(buffer, size) +
                (calibrationOffset - 94.0)

        val dbFloat = dbValue.coerceIn(0.0, 120.0).toFloat()

        val currentTime = System.currentTimeMillis()
        if (lastUpdateTime > 0) {
            val timeDelta = (currentTime - lastUpdateTime).toFloat()
            if (timeDelta > 0) {
                val dbDelta = dbFloat - lastDbValue
                val attack = dbDelta / timeDelta

                if (attack > 0.5f) {
                    transientHistory.add(TransientEvent(dbFloat, currentTime, attack))

                    if (transientHistory.size > 10) {
                        transientHistory.removeAt(0)
                    }
                }
            }
        }

        lastDbValue = dbFloat
        lastUpdateTime = currentTime

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
        transientHistory.clear()
        lastDbValue = 0f
        lastUpdateTime = 0L
        measurementStartTime = 0L
        smoothingAnimator.cancel()
        invalidate()
    }

    // === RENDERIZADO PRINCIPAL ===
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val width = width.toFloat()
        val height = height.toFloat()

        if (cachedBgGradient == null || lastWidth != width || lastHeight != height) {
            cachedBgGradient = LinearGradient(
                0f, 0f, 0f, height,
                intArrayOf(COLOR_BACKGROUND_TOP, COLOR_BACKGROUND_BOTTOM),
                floatArrayOf(0f, 1f),
                Shader.TileMode.CLAMP
            )
            lastWidth = width
            lastHeight = height
        }

        val drawArea = RectF(
            PADDING_LEFT,
            PADDING_TOP,
            width - PADDING_RIGHT,
            height - PADDING_BOTTOM
        )

        drawBackground(canvas, width, height)
        drawGrid(canvas, drawArea)

        // Dibujar según el modo actual
        when (currentViewMode) {
            ViewMode.WAVEFORM -> drawWaveformMode(canvas, drawArea)
            ViewMode.COMPRESSOR -> drawCompressorMode(canvas, drawArea)
            ViewMode.SPECTRUM -> drawSpectrumMode(canvas, drawArea)
            ViewMode.OSCILLOSCOPE -> drawOscilloscopeMode(canvas, drawArea)
        }

        // Dibujar panel inferior
        drawInfoPanel(canvas, width, height)

        // Dibujar indicador de modo actual
        drawModeIndicator(canvas, width, height)
    }

    // === DIBUJADO POR MODOS ===

    private fun drawWaveformMode(canvas: Canvas, area: RectF) {
        if (bufferCount > MIN_POINTS_TO_DRAW) {
            drawWaveform(canvas, area)
        }

        if (peakDecay > 10f) {
            drawPeakIndicator(canvas, area)
        }

        drawTransientIndicators(canvas, area)
        drawAverageValue(canvas, width.toFloat(), height.toFloat())
    }

    private fun drawCompressorMode(canvas: Canvas, area: RectF) {
        if (bufferCount < MIN_POINTS_TO_DRAW) return

        // Dibuja el gráfico de compresión
        val threshold = 80f // dB
        val ratio = 4f // 4:1

        // Dibujar línea de threshold
        val thresholdY = area.top + area.height() * (1 - threshold / 120f)
        canvas.drawLine(area.left, thresholdY, area.right, thresholdY, gridPaint)

        // Dibujar curva de compresión
        val path = Path()

        for (i in 0..100 step 2) {
            val inputDb = i * 1.2f
            val outputDb = if (inputDb > threshold) {
                threshold + (inputDb - threshold) / ratio
            } else {
                inputDb
            }

            val x = area.left + (i / 100f) * area.width()
            val y = area.top + area.height() * (1 - outputDb / 120f)

            if (i == 0) {
                path.moveTo(x, y)
            } else {
                path.lineTo(x, y)
            }
        }

        canvas.drawPath(path, compressorPaint)

        // Dibujar valores actuales si hay datos
        if (bufferCount > 0) {
            val currentDb = waveBuffer[(bufferIndex - 1 + BUFFER_SIZE) % BUFFER_SIZE]
            val compressedDb = if (currentDb > threshold) {
                threshold + (currentDb - threshold) / ratio
            } else {
                currentDb
            }

            val currentX = area.right - 50f
            val currentY = area.top + area.height() * (1 - currentDb / 120f)
            val compressedY = area.top + area.height() * (1 - compressedDb / 120f)

            // Punto de entrada
            canvas.drawCircle(currentX, currentY, 6f, Paint().apply {
                color = Color.RED
                style = Paint.Style.FILL
            })

            // Punto de salida (comprimido)
            canvas.drawCircle(currentX, compressedY, 6f, Paint().apply {
                color = Color.GREEN
                style = Paint.Style.FILL
            })
        }
    }

    private fun drawSpectrumMode(canvas: Canvas, area: RectF) {
        // Verificar condiciones seguras antes de dibujar
        if (bufferCount == 0 || bufferCount < MIN_POINTS_TO_DRAW) {
            // Dibujar un espectro vacío o mensaje
            drawEmptySpectrum(canvas, area)
            return
        }

        val barCount = 32
        val barWidth = area.width() / barCount

        // Usar un bufferCount mínimo de 1 para evitar divisiones por 0
        val safeBufferCount = bufferCount.coerceAtLeast(1)

        for (i in 0 until barCount) {
            // Cálculo seguro del índice
            val sampleIndex = (i * safeBufferCount / barCount) % safeBufferCount

            // Obtener valor con índice seguro
            val bufferIdx = (bufferIndex - sampleIndex - 1 + BUFFER_SIZE) % BUFFER_SIZE
            val value = waveBuffer[bufferIdx].coerceIn(0f, 120f)

            val normalizedValue = (value / 120f).coerceIn(0f, 1f)
            val barHeight = area.height() * normalizedValue * 0.8f

            val left = area.left + i * barWidth
            val top = area.bottom - barHeight
            val right = left + barWidth * 0.8f
            val bottom = area.bottom

            // Color basado en la frecuencia
            val hue = (i.toFloat() / barCount) * 360f
            spectrumBarPaint.color = Color.HSVToColor(floatArrayOf(hue, 0.7f, 1f))

            canvas.drawRect(left, top, right, bottom, spectrumBarPaint)
        }
    }

    private fun drawEmptySpectrum(canvas: Canvas, area: RectF) {
        // Dibujar barras mínimas para mostrar que está funcionando
        val barCount = 32
        val barWidth = area.width() / barCount

        for (i in 0 until barCount) {
            val left = area.left + i * barWidth
            val top = area.bottom - 10f // Altura mínima
            val right = left + barWidth * 0.8f
            val bottom = area.bottom

            val hue = (i.toFloat() / barCount) * 360f
            spectrumBarPaint.color = Color.HSVToColor(floatArrayOf(hue, 0.3f, 0.3f)) // Colores tenues

            canvas.drawRect(left, top, right, bottom, spectrumBarPaint)
        }
    }

    private fun drawOscilloscopeMode(canvas: Canvas, area: RectF) {
        if (bufferCount < MIN_POINTS_TO_DRAW) return

        // Modo osciloscopio
        val pointsToShow = min(bufferCount, 100)
        val path = Path()

        for (i in 0 until pointsToShow) {
            val bufferIdx = (bufferIndex - pointsToShow + i + BUFFER_SIZE) % BUFFER_SIZE
            val x = area.left + (i.toFloat() / pointsToShow) * area.width()

            // Normalizar alrededor del centro
            val dbValue = waveBuffer[bufferIdx].coerceIn(0f, 120f)
            val normalizedY = 0.5f - (dbValue - 60f) / 240f
            val y = area.top + area.height() * normalizedY.coerceIn(0f, 1f)

            if (i == 0) {
                path.moveTo(x, y)
            } else {
                path.lineTo(x, y)
            }
        }

        canvas.drawPath(path, oscilloscopePaint)

        // Dibujar retícula
        drawOscilloscopeGrid(canvas, area)
    }

    private fun drawOscilloscopeGrid(canvas: Canvas, area: RectF) {
        val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.argb(80, 255, 255, 255)
            strokeWidth = 1f
            style = Paint.Style.STROKE
        }

        // Líneas horizontales
        for (i in 0..10) {
            val y = area.top + (area.height() * i / 10f)
            canvas.drawLine(area.left, y, area.right, y, gridPaint)
        }

        // Líneas verticales
        for (i in 0..10) {
            val x = area.left + (area.width() * i / 10f)
            canvas.drawLine(x, area.top, x, area.bottom, gridPaint)
        }
    }

    private fun drawModeIndicator(canvas: Canvas, width: Float, height: Float) {
        val modeText = when (currentViewMode) {
            ViewMode.WAVEFORM -> "WAVEFORM"
            ViewMode.COMPRESSOR -> "COMPRESSOR"
            ViewMode.SPECTRUM -> "SPECTRUM"
            ViewMode.OSCILLOSCOPE -> "OSCILLOSCOPE"
        }

        val indicatorPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.argb(180, 0, 150, 255)
            textSize = 16f
            textAlign = Paint.Align.CENTER
            typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)
        }

        canvas.drawText(modeText, width / 2, PADDING_TOP - 10f, indicatorPaint)
    }

    // === MÉTODOS AUXILIARES EXISTENTES ===
    private fun drawBackground(canvas: Canvas, width: Float, height: Float) {
        backgroundPaint.shader = cachedBgGradient
        canvas.drawRect(0f, 0f, width, height, backgroundPaint)
    }

    private fun drawGrid(canvas: Canvas, area: RectF) {
        val gridHeight = area.height()

        for (dbLevel in DB_LEVELS) {
            val normalizedY = 1f - (dbLevel / 120f)
            val y = area.top + (gridHeight * normalizedY)
            canvas.drawLine(area.left, y, area.right, y, gridPaint)
        }

        val centerY = area.top + (gridHeight * 0.5f)
        canvas.drawLine(area.left, centerY, area.right, centerY, centerLinePaint)
    }

    private fun drawWaveform(canvas: Canvas, area: RectF) {
        val pointsToShow = min(bufferCount, 120)
        if (pointsToShow < MIN_POINTS_TO_DRAW) return

        val avgDb = calculateAverageDb(pointsToShow)
        val waveColor = getColorForDb(avgDb)

        wavePaint.color = waveColor
        wavePaint.setShadowLayer(
            12f, 0f, 0f,
            Color.argb(100, Color.red(waveColor), Color.green(waveColor), Color.blue(waveColor))
        )

        fillPaint.shader = createGradientForDb(avgDb, area.height())

        generateSmoothPoints(pointsToShow, area)
        drawSmoothCurve(canvas, area)
    }

    private fun calculateAverageDb(pointsToShow: Int): Float {
        var sum = 0f
        for (i in 0 until pointsToShow) {
            val idx = (bufferIndex - pointsToShow + i + BUFFER_SIZE) % BUFFER_SIZE
            sum += waveBuffer[idx]
        }
        return sum / pointsToShow
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

    private fun drawSmoothCurve(canvas: Canvas, area: RectF) {
        if (smoothPoints.size < MIN_POINTS_TO_DRAW) return

        wavePath.reset()
        fillPath.reset()

        val firstPoint = smoothPoints[0]
        wavePath.moveTo(firstPoint.x, firstPoint.y)
        fillPath.moveTo(firstPoint.x, firstPoint.y)

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
            fillPath.cubicTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
        }

        fillPath.lineTo(area.right, area.bottom)
        fillPath.lineTo(area.left, area.bottom)
        fillPath.close()

        canvas.drawPath(fillPath, fillPaint)
        canvas.drawPath(wavePath, wavePaint)
    }

    private fun drawPeakIndicator(canvas: Canvas, area: RectF) {
        val normalizedY = 1f - (peakDecay / 120f)
        val y = area.top + (area.height() * normalizedY)

        peakPaint.alpha = (255 * (peakDecay / peakValue)).toInt().coerceIn(0, 255)
        canvas.drawLine(area.left, y, area.right, y, peakPaint)
    }

    private fun drawTransientIndicators(canvas: Canvas, area: RectF) {
        val currentTime = System.currentTimeMillis()

        transientHistory.removeAll { currentTime - it.timestamp > 2000 }

        transientHistory.forEach { transient ->
            val age = (currentTime - transient.timestamp) / 2000f
            val alpha = ((1f - age) * 180).toInt().coerceIn(0, 180)

            val normalizedY = 1f - (transient.dbValue / 120f)
            val y = area.top + (area.height() * normalizedY)

            transientPaint.alpha = alpha

            canvas.drawCircle(area.right - 20f, y, 4f, transientPaint)
        }
    }

    private fun drawAverageValue(canvas: Canvas, width: Float, height: Float) {
        if (bufferCount < MIN_BUFFER_FOR_AVG) return

        val count = min(AVG_SAMPLE_SIZE, bufferCount)
        var sum = 0f

        for (i in 0 until count) {
            val idx = (bufferIndex - count + i + BUFFER_SIZE) % BUFFER_SIZE
            sum += waveBuffer[idx]
        }

        val avg = sum / count

        labelPaint.textAlign = Paint.Align.RIGHT
        labelPaint.textSize = 24f
        labelPaint.color = COLOR_TEXT_SECONDARY
        canvas.drawText("AVG: ${avg.toInt()} dB", width - 20f, height - 110f, labelPaint)
    }

    private fun drawInfoPanel(canvas: Canvas, width: Float, height: Float) {
        val panelHeight = 65f
        val panelTop = height - panelHeight

        // Fondo del panel
        canvas.drawRect(0f, panelTop, width, height, panelBgPaint)

        // Borde superior
        canvas.drawLine(0f, panelTop, width, panelTop, panelBorderPaint)

        val centerY = panelTop + panelHeight / 2 - 8f

        // Tres columnas equidistantes
        val col1X = width * 0.25f
        val col2X = width * 0.5f
        val col3X = width * 0.75f

        // Primera fila
        drawCenteredInfoRow(canvas, col1X, centerY - 12f, "", deviceModel)
        drawCenteredInfoRow(canvas, col2X, centerY - 12f, "", "A (ITU-R 468)")
        drawCenteredInfoRow(canvas, col3X, centerY - 12f, "", audioSource)

        // Segunda fila
        drawCenteredInfoRow(canvas, col1X, centerY + 8f, "", "%.1f dB".format(calibrationOffset))

        val duration = if (isMeasuring && measurementStartTime > 0) {
            System.currentTimeMillis() - measurementStartTime
        } else {
            0L
        }
        drawCenteredInfoRow(canvas, col2X, centerY + 8f, "", formatDuration(duration))
        drawCenteredInfoRow(canvas, col3X, centerY + 8f, "", if (isMeasuring) "● MEASURING" else "○ IDLE")
    }

    private fun drawCenteredInfoRow(canvas: Canvas, centerX: Float, centerY: Float, label: String, value: String) {
        infoPaint.textAlign = Paint.Align.CENTER
        canvas.drawText(label, centerX, centerY, infoPaint)

        infoValuePaint.textAlign = Paint.Align.CENTER
        canvas.drawText(value, centerX, centerY + 16f, infoValuePaint)
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