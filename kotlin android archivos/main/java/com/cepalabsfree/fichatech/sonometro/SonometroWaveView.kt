package com.cepalabsfree.fichatech.sonometro

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import android.view.animation.DecelerateInterpolator
import androidx.appcompat.app.AppCompatDelegate
import kotlin.math.*

/**
 * SonometroWaveView - Vista especializada para mediciones estéreo de sonómetro
 * Características: dos ondas estéreo, animaciones suaves, modo claro/oscuro automático
 */
class SonometroWaveView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    // === CONFIGURACIÓN ===
    companion object {
        private const val BUFFER_SIZE = 200
        private const val ANIMATION_DURATION = 150L
        private const val PEAK_DECAY_RATE = 0.92f
        private const val SMOOTHING_FACTOR = 8f

        // Márgenes
        private const val PADDING_TOP = 20f
        private const val PADDING_BOTTOM = 60f
        private const val PADDING_SIDES = 16f
        private const val WAVE_SPACING = 40f

        // Interfaz para colores
        interface Colors {
            val COLOR_BG_START: Int
            val COLOR_BG_END: Int
            val COLOR_GRID: Int
            val COLOR_CENTER_LINE: Int
            val COLOR_TEXT_PRIMARY: Int
            val COLOR_TEXT_SECONDARY: Int
            val COLOR_WAVE_LEFT: Int
            val COLOR_WAVE_RIGHT: Int
            val DB_COLOR_SAFE: Int
            val DB_COLOR_WARNING: Int
            val DB_COLOR_DANGER: Int
            val DB_COLOR_CRITICAL: Int
        }

        // Colores Modo Oscuro
        private object DarkColors : Colors {
            override val COLOR_BG_START = Color.parseColor("#0D1117")
            override val COLOR_BG_END = Color.parseColor("#161B22")
            override val COLOR_GRID = Color.parseColor("#1E3A3E")
            override val COLOR_CENTER_LINE = Color.parseColor("#334A6572")
            override val COLOR_TEXT_PRIMARY = Color.parseColor("#FFFFFF")
            override val COLOR_TEXT_SECONDARY = Color.parseColor("#80FFFFFF")
            override val COLOR_WAVE_LEFT = Color.parseColor("#00D9FF")
            override val COLOR_WAVE_RIGHT = Color.parseColor("#FF4081")

            override val DB_COLOR_SAFE = Color.parseColor("#10B981")
            override val DB_COLOR_WARNING = Color.parseColor("#F59E0B")
            override val DB_COLOR_DANGER = Color.parseColor("#EF4444")
            override val DB_COLOR_CRITICAL = Color.parseColor("#DC2626")
        }

        // Colores Modo Claro
        private object LightColors : Colors {
            override val COLOR_BG_START = Color.parseColor("#FFFFFF")
            override val COLOR_BG_END = Color.parseColor("#F5F5F5")
            override val COLOR_GRID = Color.parseColor("#E0E0E0")
            override val COLOR_CENTER_LINE = Color.parseColor("#BDBDBD")
            override val COLOR_TEXT_PRIMARY = Color.parseColor("#212121")
            override val COLOR_TEXT_SECONDARY = Color.parseColor("#616161")
            override val COLOR_WAVE_LEFT = Color.parseColor("#0097A7")
            override val COLOR_WAVE_RIGHT = Color.parseColor("#C2185B")

            override val DB_COLOR_SAFE = Color.parseColor("#27AE60")
            override val DB_COLOR_WARNING = Color.parseColor("#E67E22")
            override val DB_COLOR_DANGER = Color.parseColor("#E74C3C")
            override val DB_COLOR_CRITICAL = Color.parseColor("#C0392B")
        }
    }

    // === DETECCIÓN DE TEMA ===
    private var isDarkMode = true
    private var currentColors: Colors = DarkColors

    // === BUFFERS CIRCULARES (ESTÉREO) ===
    private val waveBufferLeft = FloatArray(BUFFER_SIZE)
    private val waveBufferRight = FloatArray(BUFFER_SIZE)
    private var bufferIndex = 0
    private var bufferCount = 0

    // === ANIMACIÓN ===
    private var currentDisplayValueLeft = 0f
    private var targetDisplayValueLeft = 0f
    private var currentDisplayValueRight = 0f
    private var targetDisplayValueRight = 0f

    private val smoothingAnimator = ValueAnimator().apply {
        duration = ANIMATION_DURATION
        interpolator = DecelerateInterpolator()
        addUpdateListener {
            val progress = it.animatedFraction
            currentDisplayValueLeft = targetDisplayValueLeft * progress + currentDisplayValueLeft * (1 - progress)
            currentDisplayValueRight = targetDisplayValueRight * progress + currentDisplayValueRight * (1 - progress)
            invalidate()
        }
    }

    // === PICOS Y ESTADÍSTICAS ===
    private var peakValueLeft = 0f
    private var peakDecayLeft = 0f
    private var peakValueRight = 0f
    private var peakDecayRight = 0f

    private var averageValueLeft = 0f
    private var averageValueRight = 0f
    private var minValueLeft = 120f
    private var maxValueLeft = 0f
    private var minValueRight = 120f
    private var maxValueRight = 0f

    // === RUTAS Y PINTURAS ===
    private val wavePathLeft = Path()
    private val fillPathLeft = Path()
    private val wavePathRight = Path()
    private val fillPathRight = Path()
    private val smoothPointsLeft = ArrayList<PointF>(BUFFER_SIZE)
    private val smoothPointsRight = ArrayList<PointF>(BUFFER_SIZE)

    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 1f
        style = Paint.Style.STROKE
    }

    private val centerLinePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 2f
        style = Paint.Style.STROKE
    }

    private val waveLinePaintLeft = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val waveLinePaintRight = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val fillPaintLeft = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val fillPaintRight = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val peakPaintLeft = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 3f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(10f, 5f), 0f)
    }

    private val peakPaintRight = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 3f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(10f, 5f), 0f)
    }

    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 52f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
        textAlign = Paint.Align.CENTER
    }

    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 18f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)
        textAlign = Paint.Align.CENTER
    }

    private val channelLabelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 14f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
        textAlign = Paint.Align.CENTER
    }

    private val statsPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 16f
        typeface = Typeface.create(Typeface.MONOSPACE, Typeface.NORMAL)
    }

    private val alertPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    init {
        updateTheme()
    }

    private fun updateTheme() {
        isDarkMode = AppCompatDelegate.getDefaultNightMode() != AppCompatDelegate.MODE_NIGHT_NO
        currentColors = if (isDarkMode) DarkColors else LightColors

        // Actualizar colores de pinturas
        gridPaint.color = currentColors.COLOR_GRID
        centerLinePaint.color = currentColors.COLOR_CENTER_LINE
        textPaint.color = currentColors.COLOR_TEXT_PRIMARY
        labelPaint.color = currentColors.COLOR_TEXT_SECONDARY
        channelLabelPaint.color = currentColors.COLOR_TEXT_PRIMARY
        statsPaint.color = currentColors.COLOR_TEXT_SECONDARY

        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val width = width.toFloat()
        val height = height.toFloat()

        // Verificar si cambió el tema
        updateTheme()

        // Fondo
        drawBackground(canvas, width, height)

        // Área de gráfico
        val graphAreaLeft = RectF(
            PADDING_SIDES,
            PADDING_TOP,
            width - PADDING_SIDES,
            height / 2 - WAVE_SPACING / 2
        )

        val graphAreaRight = RectF(
            PADDING_SIDES,
            height / 2 + WAVE_SPACING / 2,
            width - PADDING_SIDES,
            height - PADDING_BOTTOM
        )

        // Dibuja elementos canal izquierdo (LEFT)
        drawChannelLabel(canvas, graphAreaLeft, "L - LEFT", currentColors.COLOR_WAVE_LEFT)
        drawGrid(canvas, graphAreaLeft)
        if (bufferCount > 2) {
            drawWaveform(canvas, graphAreaLeft, true)
            drawPeakLine(canvas, graphAreaLeft, true)
        }
        drawAlertZones(canvas, graphAreaLeft)

        // Dibuja elementos canal derecho (RIGHT)
        drawChannelLabel(canvas, graphAreaRight, "R - RIGHT", currentColors.COLOR_WAVE_RIGHT)
        drawGrid(canvas, graphAreaRight)
        if (bufferCount > 2) {
            drawWaveform(canvas, graphAreaRight, false)
            drawPeakLine(canvas, graphAreaRight, false)
        }
        drawAlertZones(canvas, graphAreaRight)

        // Dibuja panel inferior con estadísticas
        drawStatistics(canvas, width, height)
    }

    private fun drawBackground(canvas: Canvas, width: Float, height: Float) {
        bgPaint.shader = LinearGradient(
            0f, 0f, 0f, height,
            currentColors.COLOR_BG_START,
            currentColors.COLOR_BG_END,
            Shader.TileMode.CLAMP
        )
        canvas.drawRect(0f, 0f, width, height, bgPaint)
    }

    private fun drawChannelLabel(canvas: Canvas, area: RectF, label: String, color: Int) {
        channelLabelPaint.color = color
        canvas.drawText(label, area.left + 30f, area.top - 5f, channelLabelPaint)
    }

    private fun drawGrid(canvas: Canvas, area: RectF) {
        val dbLevels = floatArrayOf(30f, 50f, 70f, 85f, 100f, 120f)

        dbLevels.forEach { dbLevel ->
            val normalizedY = 1f - (dbLevel / 120f)
            val y = area.top + area.height() * normalizedY

            gridPaint.alpha = when (dbLevel) {
                85f -> 60
                100f -> 50
                else -> 25
            }

            canvas.drawLine(area.left, y, area.right, y, gridPaint)

            // Etiquetas de dB
            labelPaint.alpha = 150
            labelPaint.textAlign = Paint.Align.RIGHT
            canvas.drawText(
                "${dbLevel.toInt()} dB",
                area.left - 10f,
                y + 6f,
                labelPaint
            )
        }

        // Línea central (70 dB - seguro)
        val centerY = area.top + area.height() * (1f - 70f / 120f)
        canvas.drawLine(area.left, centerY, area.right, centerY, centerLinePaint)
    }

    private fun drawWaveform(canvas: Canvas, area: RectF, isLeft: Boolean) {
        val pointsToShow = minOf(bufferCount, 150)

        if (isLeft) {
            generateSmoothPoints(pointsToShow, area, true)
            val avgDb = calculateAverageDb(pointsToShow, true)
            val waveColor = getColorForDb(avgDb)

            waveLinePaintLeft.color = waveColor
            waveLinePaintLeft.setShadowLayer(
                15f, 0f, 2f,
                Color.argb(80, Color.red(waveColor), Color.green(waveColor), Color.blue(waveColor))
            )

            fillPaintLeft.shader = LinearGradient(
                0f, area.top, 0f, area.bottom,
                Color.argb(60, Color.red(waveColor), Color.green(waveColor), Color.blue(waveColor)),
                Color.argb(10, Color.red(waveColor), Color.green(waveColor), Color.blue(waveColor)),
                Shader.TileMode.CLAMP
            )

            drawSmoothCurve(canvas, area, smoothPointsLeft, wavePathLeft, fillPathLeft, waveLinePaintLeft, fillPaintLeft)
        } else {
            generateSmoothPoints(pointsToShow, area, false)
            val avgDb = calculateAverageDb(pointsToShow, false)
            val waveColor = getColorForDb(avgDb)

            waveLinePaintRight.color = waveColor
            waveLinePaintRight.setShadowLayer(
                15f, 0f, 2f,
                Color.argb(80, Color.red(waveColor), Color.green(waveColor), Color.blue(waveColor))
            )

            fillPaintRight.shader = LinearGradient(
                0f, area.top, 0f, area.bottom,
                Color.argb(60, Color.red(waveColor), Color.green(waveColor), Color.blue(waveColor)),
                Color.argb(10, Color.red(waveColor), Color.green(waveColor), Color.blue(waveColor)),
                Shader.TileMode.CLAMP
            )

            drawSmoothCurve(canvas, area, smoothPointsRight, wavePathRight, fillPathRight, waveLinePaintRight, fillPaintRight)
        }
    }

    private fun generateSmoothPoints(pointsToShow: Int, area: RectF, isLeft: Boolean) {
        val points = if (isLeft) smoothPointsLeft else smoothPointsRight
        val buffer = if (isLeft) waveBufferLeft else waveBufferRight

        points.clear()

        for (i in 0 until pointsToShow) {
            val bufferIdx = (bufferIndex - pointsToShow + i + BUFFER_SIZE) % BUFFER_SIZE
            val x = area.left + (i.toFloat() / pointsToShow) * area.width()
            val dbValue = buffer[bufferIdx].coerceIn(0f, 120f)
            val normalizedY = 1f - (dbValue / 120f)
            val y = area.top + area.height() * normalizedY

            points.add(PointF(x, y))
        }
    }

    private fun drawSmoothCurve(
        canvas: Canvas,
        area: RectF,
        points: List<PointF>,
        wavePath: Path,
        fillPath: Path,
        linePaint: Paint,
        paint: Paint
    ) {
        if (points.size < 2) return

        wavePath.reset()
        fillPath.reset()

        wavePath.moveTo(points[0].x, points[0].y)
        fillPath.moveTo(points[0].x, points[0].y)

        for (i in 0 until points.size - 1) {
            val p0 = points[maxOf(i - 1, 0)]
            val p1 = points[i]
            val p2 = points[i + 1]
            val p3 = points[minOf(i + 2, points.size - 1)]

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

        canvas.drawPath(fillPath, paint)
        canvas.drawPath(wavePath, linePaint)
    }

    private fun drawPeakLine(canvas: Canvas, area: RectF, isLeft: Boolean) {
        val peakDecay = if (isLeft) peakDecayLeft else peakDecayRight
        val peakValue = if (isLeft) peakValueLeft else peakValueRight
        val paintPeak = if (isLeft) peakPaintLeft else peakPaintRight

        if (peakDecay < 10f) return

        val normalizedY = 1f - (peakDecay / 120f)
        val y = area.top + area.height() * normalizedY

        paintPeak.color = getColorForDb(peakDecay)
        paintPeak.alpha = (200 * (peakDecay / peakValue).coerceIn(0f, 1f)).toInt()

        canvas.drawLine(area.left, y, area.right, y, paintPeak)
    }

    private fun drawAlertZones(canvas: Canvas, area: RectF) {
        drawZone(canvas, area, 0f, 70f, Color.argb(8, 16, 185, 129))
        drawZone(canvas, area, 70f, 85f, Color.argb(8, 245, 158, 11))
        drawZone(canvas, area, 85f, 100f, Color.argb(8, 239, 68, 68))
        drawZone(canvas, area, 100f, 120f, Color.argb(10, 220, 38, 38))
    }

    private fun drawZone(canvas: Canvas, area: RectF, minDb: Float, maxDb: Float, color: Int) {
        val topNorm = 1f - (maxDb / 120f)
        val bottomNorm = 1f - (minDb / 120f)

        val top = area.top + area.height() * topNorm
        val bottom = area.top + area.height() * bottomNorm

        alertPaint.color = color
        canvas.drawRect(area.left, top, area.right, bottom, alertPaint)
    }


    private fun drawStatistics(canvas: Canvas, width: Float, height: Float) {
        val panelTop = height - PADDING_BOTTOM + 5f

        // Fondo panel
        val panelBgPaint = Paint().apply {
            color = if (isDarkMode)
                Color.argb(100, 20, 30, 50)
            else
                Color.argb(50, 200, 200, 200)
            style = Paint.Style.FILL
        }
        canvas.drawRect(0f, panelTop, width, height, panelBgPaint)

        // Línea separadora
        canvas.drawLine(0f, panelTop, width, panelTop, centerLinePaint)

        // Estadísticas en cuatro columnas
        val col1X = width * 0.125f
        val col2X = width * 0.375f
        val col3X = width * 0.625f
        val col4X = width * 0.875f
        val textY = panelTop + 18f
        val valueY = textY + 16f

        // LEFT - AVG
        statsPaint.color = currentColors.COLOR_WAVE_LEFT
        statsPaint.textAlign = Paint.Align.CENTER
        canvas.drawText("LEFT AVG", col1X, textY, statsPaint)
        statsPaint.textSize = 18f
        canvas.drawText("%.1f".format(averageValueLeft), col1X, valueY, statsPaint)

        // LEFT - PEAK
        statsPaint.color = currentColors.COLOR_TEXT_SECONDARY
        statsPaint.textSize = 16f
        canvas.drawText("PEAK", col2X, textY, statsPaint)
        statsPaint.color = currentColors.COLOR_WAVE_LEFT
        statsPaint.textSize = 18f
        canvas.drawText("%.1f".format(peakValueLeft), col2X, valueY, statsPaint)

        // RIGHT - AVG
        statsPaint.color = currentColors.COLOR_WAVE_RIGHT
        statsPaint.textSize = 16f
        canvas.drawText("RIGHT AVG", col3X, textY, statsPaint)
        statsPaint.textSize = 18f
        canvas.drawText("%.1f".format(averageValueRight), col3X, valueY, statsPaint)

        // RIGHT - PEAK
        statsPaint.color = currentColors.COLOR_TEXT_SECONDARY
        statsPaint.textSize = 16f
        canvas.drawText("PEAK", col4X, textY, statsPaint)
        statsPaint.color = currentColors.COLOR_WAVE_RIGHT
        statsPaint.textSize = 18f
        canvas.drawText("%.1f".format(peakValueRight), col4X, valueY, statsPaint)
    }

    // === MÉTODOS PÚBLICOS ===

    fun updateDecibelValues(dbValueLeft: Double, dbValueRight: Double) {
        val dbLeftFloat = dbValueLeft.coerceIn(0.0, 120.0).toFloat()
        val dbRightFloat = dbValueRight.coerceIn(0.0, 120.0).toFloat()

        // Actualizar buffers
        waveBufferLeft[bufferIndex] = dbLeftFloat
        waveBufferRight[bufferIndex] = dbRightFloat
        bufferIndex = (bufferIndex + 1) % BUFFER_SIZE
        if (bufferCount < BUFFER_SIZE) bufferCount++

        // Actualizar estadísticas
        updateStatistics(dbLeftFloat, true)
        updateStatistics(dbRightFloat, false)

        // Animar transición
        targetDisplayValueLeft = dbLeftFloat
        targetDisplayValueRight = dbRightFloat
        smoothingAnimator.cancel()
        smoothingAnimator.setFloatValues(0f, 1f)
        smoothingAnimator.start()

        invalidate()
    }

    private fun updateStatistics(dbFloat: Float, isLeft: Boolean) {
        if (isLeft) {
            // Pico LEFT
            if (dbFloat > peakValueLeft) {
                peakValueLeft = dbFloat
                peakDecayLeft = dbFloat
            } else {
                peakDecayLeft = peakDecayLeft * PEAK_DECAY_RATE
                peakDecayLeft = maxOf(peakDecayLeft, dbFloat * 0.8f)
            }

            minValueLeft = minOf(minValueLeft, dbFloat)
            maxValueLeft = maxOf(maxValueLeft, dbFloat)

            if (bufferCount > 0) {
                var sum = 0f
                for (i in 0 until bufferCount) {
                    sum += waveBufferLeft[i]
                }
                averageValueLeft = sum / bufferCount
            }
        } else {
            // Pico RIGHT
            if (dbFloat > peakValueRight) {
                peakValueRight = dbFloat
                peakDecayRight = dbFloat
            } else {
                peakDecayRight = peakDecayRight * PEAK_DECAY_RATE
                peakDecayRight = maxOf(peakDecayRight, dbFloat * 0.8f)
            }

            minValueRight = minOf(minValueRight, dbFloat)
            maxValueRight = maxOf(maxValueRight, dbFloat)

            if (bufferCount > 0) {
                var sum = 0f
                for (i in 0 until bufferCount) {
                    sum += waveBufferRight[i]
                }
                averageValueRight = sum / bufferCount
            }
        }
    }

    fun reset() {
        waveBufferLeft.fill(0f)
        waveBufferRight.fill(0f)
        bufferIndex = 0
        bufferCount = 0
        currentDisplayValueLeft = 0f
        targetDisplayValueLeft = 0f
        currentDisplayValueRight = 0f
        targetDisplayValueRight = 0f
        peakValueLeft = 0f
        peakDecayLeft = 0f
        peakValueRight = 0f
        peakDecayRight = 0f
        averageValueLeft = 0f
        averageValueRight = 0f
        minValueLeft = 120f
        maxValueLeft = 0f
        minValueRight = 120f
        maxValueRight = 0f
        smoothingAnimator.cancel()
        invalidate()
    }

    // === UTILIDADES ===

    private fun getColorForDb(db: Float): Int {
        return when {
            db < 70f -> currentColors.DB_COLOR_SAFE
            db < 85f -> currentColors.DB_COLOR_WARNING
            db < 100f -> currentColors.DB_COLOR_DANGER
            else -> currentColors.DB_COLOR_CRITICAL
        }
    }

    private fun calculateAverageDb(pointsToShow: Int, isLeft: Boolean): Float {
        val buffer = if (isLeft) waveBufferLeft else waveBufferRight
        var sum = 0f
        for (i in 0 until pointsToShow) {
            val idx = (bufferIndex - pointsToShow + i + BUFFER_SIZE) % BUFFER_SIZE
            sum += buffer[idx]
        }
        return sum / pointsToShow
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        smoothingAnimator.cancel()
    }
}