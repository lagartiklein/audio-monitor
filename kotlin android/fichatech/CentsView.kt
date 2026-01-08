package com.cepalabsfree.fichatech

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View

class CentsView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    // Líneas de referencia con gradiente
    private val refLinePaint = Paint().apply {
        color = Color.WHITE
        strokeWidth = 3f
        style = Paint.Style.STROKE
        isAntiAlias = true
        alpha = 180
    }

    // Etiquetas de referencia
    private val textPaint = Paint().apply {
        color = Color.WHITE
        textSize = 38f
        isAntiAlias = true
        textAlign = Paint.Align.CENTER
        typeface = Typeface.DEFAULT_BOLD
        alpha = 200
    }

    // Indicador de desviación (barra y círculo)
    private val deviationPaint = Paint().apply {
        color = Color.parseColor("#FFFF4081")
        strokeWidth = 10f
        style = Paint.Style.STROKE
        isAntiAlias = true
        setShadowLayer(12f, 0f, 0f, Color.parseColor("#AAFF4081"))
    }
    private val deviationCirclePaint = Paint().apply {
        color = Color.parseColor("#FFFF4081")
        style = Paint.Style.FILL
        isAntiAlias = true
        setShadowLayer(12f, 0f, 0f, Color.parseColor("#AAFF4081"))
    }

    // Flecha central estilizada
    private val arrowPaint = Paint().apply {
        color = Color.YELLOW
        strokeWidth = 6f
        style = Paint.Style.STROKE
        isAntiAlias = true
    }

    private var cents: Int = 0

    fun updateCents(cents: Int) {
        this.cents = cents
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val w = width.toFloat()
        val h = height.toFloat()

        // Líneas de referencia y etiquetas
        val centerX = w / 2
        val baseY = h * 0.78f
        val lineLen = 36f
        val grad = LinearGradient(0f, baseY, w, baseY, Color.WHITE, Color.LTGRAY, Shader.TileMode.CLAMP)
        refLinePaint.shader = grad

        for (i in -5..5) {
            val x = centerX + i * (w * 0.08f)
            val top = if (i % 5 == 0) baseY - lineLen * 1.7f else baseY - lineLen
            canvas.drawLine(x, baseY, x, top, refLinePaint)
            if (i != 0) {
                canvas.drawText(
                    "${i * 10}",
                    x,
                    top - 16f,
                    textPaint
                )
            }
        }
        // Etiqueta central "0"
        textPaint.color = Color.parseColor("#FF00BCD4")
        canvas.drawText("0", centerX, baseY - lineLen * 2.2f, textPaint)
        textPaint.color = Color.WHITE

        // Flecha central estilizada
        val arrowY = h * 0.93f
        val arrowSize = 28f
        val arrowPath = Path().apply {
            moveTo(centerX, arrowY)
            lineTo(centerX - arrowSize, arrowY - arrowSize)
            moveTo(centerX, arrowY)
            lineTo(centerX + arrowSize, arrowY - arrowSize)
            moveTo(centerX, baseY)
            lineTo(centerX, arrowY - arrowSize / 2)
        }
        canvas.drawPath(arrowPath, arrowPaint)

        // Indicador de desviación
        val deviationX = centerX + cents * (w * 0.008f)
        canvas.drawLine(deviationX, baseY - lineLen * 2.3f, deviationX, arrowY - arrowSize, deviationPaint)
        canvas.drawCircle(deviationX, baseY - lineLen * 2.3f, 14f, deviationCirclePaint)
    }
}
