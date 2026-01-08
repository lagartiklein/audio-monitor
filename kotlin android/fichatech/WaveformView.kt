package com.cepalabsfree.fichatech

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View

class WaveformView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private val paint = Paint().apply {
        color = Color.BLUE
        strokeWidth = 2f
        isAntiAlias = true
    }

    private val amplitudes: MutableList<Float> = mutableListOf()
    private var isRecording = false

    fun addAmplitude(amplitude: Float) {
        synchronized(amplitudes) {
            amplitudes.add(amplitude)
            if (amplitudes.size > width / 2) {
                amplitudes.removeAt(0)
            }
        }
        invalidate()
    }

    fun clearAmplitudes() {
        synchronized(amplitudes) {
            amplitudes.clear()
        }
        invalidate()
    }

    fun startRecording() {
        isRecording = true
        clearAmplitudes()
    }

    fun stopRecording() {
        isRecording = false
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val middle = height / 2f
        var curX = 0f
        val zoomFactor = 10 // Aumentamos el divisor para reducir el zoom
        synchronized(amplitudes) {
            amplitudes.forEach { amplitude ->
                val scaledHeight = amplitude / 7
                canvas.drawLine(curX, middle - scaledHeight, curX, middle + scaledHeight, paint)
                curX += 2
            }
        }
    }
}
