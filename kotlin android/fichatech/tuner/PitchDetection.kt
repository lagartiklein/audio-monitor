package com.cepalabsfree.fichatech.tuner


import kotlin.math.log2
import kotlin.math.cos
import kotlin.math.PI

// Clase para la detección de tono en datos de audio
class PitchDetection(private val audioData: FloatArray) {
    companion object {
        // Constantes de la clase
        private const val SAMPLE_RATE = 44100 // Frecuencia de muestreo en Hz
        private const val MIN_FREQUENCY = 80f // Frecuencia mínima detectable
        private const val MAX_FREQUENCY = 500f // Frecuencia máxima detectable
    }

    fun detectPitch(): Float? {
        // Aplicar la ventana de Hann a los datos de audio
        val windowedData = applyHannWindow(audioData)

        // Calcular los tamaños mínimo y máximo del período
        val minSize = (SAMPLE_RATE / MAX_FREQUENCY).toInt()
        val maxSize = (SAMPLE_RATE / MIN_FREQUENCY).toInt()

        var maxCorrelation = 0f // Correlación máxima encontrada
        var maxPeriod = 0 // Período correspondiente a la correlación máxima
        var correlation: Float

        // Bucle para calcular la correlación en diferentes períodos
        for (period in minSize until maxSize) {
            correlation = 0f
            // Calcular la correlación para el período actual
            for (i in 0 until windowedData.size - period) {
                correlation += windowedData[i] * windowedData[i + period]
            }
            // Actualizar la correlación máxima si se encuentra una mayor
            if (correlation > maxCorrelation) {
                maxCorrelation = correlation
                maxPeriod = period
            }
        }

        // Calcular la frecuencia correspondiente al período de máxima correlación
        val frequency = SAMPLE_RATE.toFloat() / maxPeriod
        // Comprobar si la frecuencia está dentro del rango permitido y, si es así, interpolarla
        return if (frequency in MIN_FREQUENCY..MAX_FREQUENCY) {
            interpolatePeakFrequency(windowedData, maxPeriod)
        } else {
            null
        }
    }

    private fun applyHannWindow(data: FloatArray): FloatArray {
        val windowedData = FloatArray(data.size)
        for (i in data.indices) {
            // Aplicar la fórmula de la ventana de Hann
            windowedData[i] = data[i] * (0.5f * (1 - cos(2 * PI * i / (data.size - 1)))).toFloat()
        }
        return windowedData
    }

    private fun interpolatePeakFrequency(data: FloatArray, period: Int): Float {
        // Calcular las correlaciones a la izquierda y derecha del pico
        val leftCorrelation = calculateCorrelation(data, period - 1)
        val rightCorrelation = calculateCorrelation(data, period + 1)
        val peakCorrelation = calculateCorrelation(data, period)

        // Calcular el ajuste para la interpolación del pico
        val adjustment = 0.5f * (leftCorrelation - rightCorrelation) / (leftCorrelation - 2 * peakCorrelation + rightCorrelation)
        // Calcular la frecuencia ajustada
        return SAMPLE_RATE.toFloat() / (period + adjustment)
    }

    private fun calculateCorrelation(data: FloatArray, period: Int): Float {
        var correlation = 0f
        // Bucle para calcular la correlación
        for (i in 0 until data.size - period) {
            correlation += data[i] * data[i + period]
        }
        return correlation
    }

    fun calculateCentsDifference(frequency: Float): Int {
        val referenceFrequency = 440f // Frecuencia de referencia A4
        val centsPerOctave = 1200 // Centésimas de tono por octava
        // Calcular la diferencia en centésimas de tono
        val centsDifference = centsPerOctave * log2(frequency / referenceFrequency)
        return centsDifference.toInt() // Devolver la diferencia como un entero
    }
}
