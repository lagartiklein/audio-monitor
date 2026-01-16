package com.cepalabsfree.fichatech.fichatecnica

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.util.TypedValue
import android.view.MotionEvent
import android.view.ViewParent
import androidx.appcompat.widget.AppCompatSeekBar

class VerticalSeekBar : AppCompatSeekBar {

    private var lastProgress = 0
    private var isUserInteracting = false
    private val thumbRadiusDp = 18f  // Reducido un poco
    private var thumbRadiusPx = 0f
    private val trackWidthDp = 8f   // Reducido un poco
    private var trackWidthPx = 0f

    // Márgenes/padding ampliados para más espacio alrededor del control
    private val verticalPaddingDp = 32f  // Aumentado de 32f a 40f
    private var verticalPaddingPx = 0f
    private val horizontalPaddingDp = 16f  // Aumentado de 16f a 28f
    private var horizontalPaddingPx = 0f

    // Colores para el efecto progresivo (verde -> amarillo -> rojo)
    private val colorLow = Color.parseColor("#4CAF50")    // Verde
    private val colorMid = Color.parseColor("#FFC107")    // Amarillo
    private val colorHigh = Color.parseColor("#F44336")   // Rojo

    private var onSeekBarChangeListener: OnSeekBarChangeListener? = null

    // Shader para el efecto de gradiente
    private var progressShader: LinearGradient? = null
    private var progressPaint: Paint = Paint()

    constructor(context: Context) : super(context) { init() }
    constructor(context: Context, attrs: AttributeSet?) : super(context, attrs) { init() }
    constructor(context: Context, attrs: AttributeSet?, defStyleAttr: Int) : super(context, attrs, defStyleAttr) { init() }

    private fun init() {
        thumbRadiusPx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            thumbRadiusDp,
            resources.displayMetrics
        )
        trackWidthPx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            trackWidthDp,
            resources.displayMetrics
        )
        verticalPaddingPx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            verticalPaddingDp,
            resources.displayMetrics
        )
        horizontalPaddingPx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            horizontalPaddingDp,
            resources.displayMetrics
        )

        progressPaint.isAntiAlias = true
        progressPaint.style = Paint.Style.FILL
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        // Crear el shader de gradiente cuando se conoce el tamaño (considerando padding)
        val drawableHeight = h - 2 * verticalPaddingPx
        progressShader = LinearGradient(
            0f, h.toFloat() - verticalPaddingPx, 0f, verticalPaddingPx,
            intArrayOf(colorHigh, colorMid, colorLow),
            floatArrayOf(0f, 0.5f, 1f),
            Shader.TileMode.CLAMP
        )
    }

    override fun onDraw(c: Canvas) {
        val paint = Paint().apply {
            isAntiAlias = true
            style = Paint.Style.FILL
        }

        val width = width.toFloat()
        val height = height.toFloat()

        // Área dibujable considerando padding
        val drawableLeft = horizontalPaddingPx
        val drawableRight = width - horizontalPaddingPx
        val drawableTop = verticalPaddingPx
        val drawableBottom = height - verticalPaddingPx
        val drawableHeight = drawableBottom - drawableTop

        // Centro horizontal dentro del área dibujable
        val centerX = (drawableLeft + drawableRight) / 2

        // 1. Dibujar el TRACK (canal) de fondo con efecto de profundidad
        val trackLeft = centerX - trackWidthPx / 2
        val trackRight = centerX + trackWidthPx / 2

        // Track de fondo con gradiente sutil
        val trackGradient = LinearGradient(
            trackLeft, drawableTop, trackRight, drawableBottom,
            Color.parseColor("#666666"), Color.parseColor("#888888"),
            Shader.TileMode.CLAMP
        )
        paint.shader = trackGradient
        c.drawRoundRect(
            trackLeft - 2, drawableTop, trackRight + 2, drawableBottom,
            6f, 6f, paint
        )
        paint.shader = null

        // 2. Dibujar el PROGRESO con efecto de gradiente dinámico
        val progressRatio = progress.toFloat() / max
        val progressHeight = drawableHeight * progressRatio

        // Calcular color basado en el progreso (más intenso según el nivel)
        val dynamicColor = getDynamicColor(progressRatio)

        // Crear gradiente para el progreso
        val progressGradient = LinearGradient(
            trackLeft, drawableBottom - progressHeight, trackRight, drawableBottom,
            adjustColorBrightness(dynamicColor, 0.8f), // Más oscuro abajo
            dynamicColor, // Color principal
            Shader.TileMode.CLAMP
        )
        progressPaint.shader = progressGradient

        // Dibujar progreso con bordes redondeados
        c.drawRoundRect(
            trackLeft, drawableBottom - progressHeight, trackRight, drawableBottom,
            4f, 4f, progressPaint
        )
        progressPaint.shader = null

        // 3. Dibujar el THUMB (control deslizante) - Diseño moderno
        val thumbY = drawableBottom - progressHeight

        // Sombra del thumb
        paint.color = 0x60000000.toInt()
        c.drawCircle(centerX, thumbY + 3, thumbRadiusPx + 2, paint)

        // Thumb principal con gradiente amarillo
        val thumbGradient = RadialGradient(
            centerX, thumbY, thumbRadiusPx,
            Color.parseColor("#FFFF00"), // Amarillo brillante
            Color.parseColor("#FFA000"), // Amarillo oscuro
            Shader.TileMode.CLAMP
        )
        paint.shader = thumbGradient
        c.drawCircle(centerX, thumbY, thumbRadiusPx, paint)
        paint.shader = null

        // Highlight del thumb
        paint.color = 0x80FFFFFF.toInt()
        c.drawCircle(
            centerX - thumbRadiusPx * 0.3f,
            thumbY - thumbRadiusPx * 0.3f,
            thumbRadiusPx * 0.5f,
            paint
        )

        // 4. Dibujar marcas de referencia con diseño moderno
        paint.color = 0x40FFFFFF.toInt()
        paint.strokeWidth = 2f
        paint.style = Paint.Style.STROKE

        // Marcas principales cada 25%
        val markPositions = floatArrayOf(0.25f, 0.5f, 0.75f)
        markPositions.forEach { position ->
            val markY = drawableTop + (drawableHeight * position)
            // Línea más larga para marcas principales
            c.drawLine(trackLeft - 5, markY, trackRight + 5, markY, paint)
        }

        // Marcas secundarias cada 12.5%
        paint.strokeWidth = 1f
        paint.color = 0x20FFFFFF.toInt()
        for (i in 1..7) {
            if (i % 2 != 0) continue // Saltar las posiciones que ya dibujamos
            val markY = drawableTop + (drawableHeight * (i * 0.125f))
            c.drawLine(trackLeft - 3, markY, trackRight + 3, markY, paint)
        }

        // 5. Efecto de brillo en el borde del track
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 1f
        paint.color = 0x30FFFFFF.toInt()
        c.drawRoundRect(
            trackLeft - 2, drawableTop, trackRight + 2, drawableBottom,
            6f, 6f, paint
        )
    }

    private fun getDynamicColor(progress: Float): Int {
        return when {
            progress < 0.33 -> {
                // Verde a Amarillo
                interpolateColor(colorLow, colorMid, progress / 0.33f)
            }
            progress < 0.66 -> {
                // Amarillo a Naranja
                interpolateColor(colorMid, Color.parseColor("#FF9800"), (progress - 0.33f) / 0.33f)
            }
            else -> {
                // Naranja a Rojo
                interpolateColor(Color.parseColor("#FF9800"), colorHigh, (progress - 0.66f) / 0.34f)
            }
        }
    }

    private fun interpolateColor(color1: Int, color2: Int, factor: Float): Int {
        val factorClamped = factor.coerceIn(0f, 1f)
        val a = (Color.alpha(color1) + (Color.alpha(color2) - Color.alpha(color1)) * factorClamped).toInt()
        val r = (Color.red(color1) + (Color.red(color2) - Color.red(color1)) * factorClamped).toInt()
        val g = (Color.green(color1) + (Color.green(color2) - Color.green(color1)) * factorClamped).toInt()
        val b = (Color.blue(color1) + (Color.blue(color2) - Color.blue(color1)) * factorClamped).toInt()
        return Color.argb(a, r, g, b)
    }

    private fun adjustColorBrightness(color: Int, factor: Float): Int {
        val r = (Color.red(color) * factor).toInt().coerceIn(0, 255)
        val g = (Color.green(color) * factor).toInt().coerceIn(0, 255)
        val b = (Color.blue(color) * factor).toInt().coerceIn(0, 255)
        return Color.rgb(r, g, b)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!isEnabled) return false

        // Calcular la posición actual del thumb considerando padding
        val progressRatio = progress.toFloat() / max
        val drawableTop = verticalPaddingPx
        val drawableBottom = height - verticalPaddingPx
        val drawableHeight = drawableBottom - drawableTop
        val thumbY = drawableBottom - (drawableHeight * progressRatio)

        val centerX = width / 2f

        // Área de touch solo alrededor del thumb (más generosa para mejor UX)
        val touchExpansion = thumbRadiusPx * 3f
        val thumbRect = RectF(
            centerX - thumbRadiusPx - touchExpansion,
            thumbY - thumbRadiusPx - touchExpansion,
            centerX + thumbRadiusPx + touchExpansion,
            thumbY + thumbRadiusPx + touchExpansion
        )

        // Solo procesar touch si está dentro del área del thumb
        if (!thumbRect.contains(event.x, event.y)) {
            return false
        }

        val parent: ViewParent? = parent

        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                isUserInteracting = true
                parent?.requestDisallowInterceptTouchEvent(true)
                updateProgressFromTouch(event)
                onSeekBarChangeListener?.onStartTrackingTouch(this)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                // ✅ PERMITIR MOVIMIENTO EN CUALQUIER LUGAR MIENTRAS isUserInteracting = true
                if (isUserInteracting) {
                    updateProgressFromTouch(event)
                    onSeekBarChangeListener?.onProgressChanged(this, progress, true)
                    return true
                }
                return false
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                isUserInteracting = false
                parent?.requestDisallowInterceptTouchEvent(false)
                onSeekBarChangeListener?.onStopTrackingTouch(this)
                performClick()
                return true
            }
        }
        return false
    }

    private fun updateProgressFromTouch(event: MotionEvent) {
        val h = height
        if (h <= 0) return

        // Considerar el padding vertical en el cálculo del progreso
        val drawableTop = verticalPaddingPx + thumbRadiusPx
        val drawableBottom = h - verticalPaddingPx - thumbRadiusPx
        val drawableHeight = drawableBottom - drawableTop

        if (drawableHeight <= 0) return

        val y = event.y.coerceIn(drawableTop, drawableBottom)
        val relativeY = y - drawableTop
        val progress = (max * (1f - relativeY / drawableHeight)).toInt().coerceIn(0, max)

        if (progress != lastProgress) {
            lastProgress = progress
            setProgress(progress)
            invalidate()
            onSeekBarChangeListener?.onProgressChanged(this, progress, true)
        }
    }

    override fun setProgress(progress: Int) {
        if (this.progress != progress || isUserInteracting) {
            super.setProgress(progress)
        }
    }

    override fun performClick(): Boolean {
        return super.performClick()
    }

    override fun setOnSeekBarChangeListener(l: OnSeekBarChangeListener?) {
        onSeekBarChangeListener = l
    }
}