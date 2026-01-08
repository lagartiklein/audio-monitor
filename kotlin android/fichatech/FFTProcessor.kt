package com.cepalabsfree.fichatech.sonometro



import kotlin.math.*



/**

 * Procesador FFT centralizado para evitar duplicaciÃ³n y mejorar eficiencia

 * Incluye ventanas de anÃ¡lisis y ponderaciÃ³n A-weighting

 */

class FFTProcessor(private val fftSize: Int = 2048) {



    companion object {

        private const val SAMPLE_RATE = 44100.0

    }



    // Datos reutilizables

    data class FFTResult(

        val magnitudes: FloatArray,

        val phases: FloatArray,

        val frequencyBins: FloatArray,

        val dominantFrequency: Float,

        val spectralCentroid: Float

    )



    // Buffers reutilizables (evitar GC)

    private val real = FloatArray(fftSize)

    private val imag = FloatArray(fftSize)

    private val magnitudes = FloatArray(fftSize / 2)

    private val phases = FloatArray(fftSize / 2)

    private val frequencyBins = FloatArray(fftSize / 2)



    // Ventanas pre-calculadas

    private val hammingWindow = FloatArray(fftSize)

    private val blackmanHarrisWindow = FloatArray(fftSize)

    private val hannWindow = FloatArray(fftSize)



    // Coeficientes A-weighting pre-calculados por bin

    private val aWeightingCoefficients = FloatArray(fftSize / 2)



    init {

        initializeWindows()

        initializeFrequencyBins()

        calculateAWeightingCoefficients()

    }



    private fun initializeWindows() {

        for (i in 0 until fftSize) {

            val n = fftSize - 1

            val index = i.toFloat()



            // Hamming

            hammingWindow[i] = 0.54f - 0.46f * cos(2f * PI.toFloat() * i / n)



            // Blackman-Harris (mejor rechazo de lÃ³bulos laterales)

            val a0 = 0.35875f

            val a1 = 0.48829f

            val a2 = 0.14128f

            val a3 = 0.01168f

            blackmanHarrisWindow[i] = (a0 - a1 * cos(2 * PI * i / n) +

                    a2 * cos(4 * PI * i / n) - a3 * cos(6 * PI * i / n)).toFloat()



            // Hann (buena para anÃ¡lisis general)

            hannWindow[i] = 0.5f * (1f - cos(2f * PI.toFloat() * i / n))

        }

    }



    private fun initializeFrequencyBins() {

        for (i in frequencyBins.indices) {

            frequencyBins[i] = (i * SAMPLE_RATE / fftSize).toFloat()

        }

    }



    /**

     * Calcula coeficientes de ponderaciÃ³n A segÃºn ITU-R 468

     * Para mediciones de ruido mÃ¡s realistas segÃºn percepciÃ³n humana

     */

    private fun calculateAWeightingCoefficients() {

        for (i in aWeightingCoefficients.indices) {

            val freq = frequencyBins[i].toDouble()



            if (freq < 10.0) {

                aWeightingCoefficients[i] = 0f

                continue

            }



            // FÃ³rmula de A-weighting

            val f2 = freq * freq

            val f4 = f2 * f2



            val num = 12194.0 * 12194.0 * f4

            val den = (f2 + 20.6 * 20.6) *

                    sqrt((f2 + 107.7 * 107.7) * (f2 + 737.9 * 737.9)) *

                    (f2 + 12194.0 * 12194.0)



            val ra = num / den

            val aWeight = 20.0 * log10(ra) + 2.0 // Normalizado a 0dB a 1kHz



            // Convertir dB a ganancia lineal

            aWeightingCoefficients[i] = 10f.pow((aWeight / 20.0).toFloat())

        }

    }



    /**

     * Procesa buffer de audio con ventana especificada

     */

    fun process(

        buffer: ShortArray,

        size: Int = buffer.size,

        windowType: WindowType = WindowType.BLACKMAN_HARRIS,

        applyAWeighting: Boolean = false

    ): FFTResult {



        val samplestoProcess = minOf(size, fftSize)



        // Aplicar ventana y convertir a float

        val window = when(windowType) {

            WindowType.HAMMING -> hammingWindow

            WindowType.BLACKMAN_HARRIS -> blackmanHarrisWindow

            WindowType.HANN -> hannWindow

            WindowType.NONE -> null

        }



        for (i in 0 until fftSize) {

            if (i < samplestoProcess) {

                val sample = buffer[i].toFloat() / 32768f // Normalizar a [-1, 1]

                real[i] = if (window != null) sample * window[i] else sample

            } else {

                real[i] = 0f // Zero-padding

            }

            imag[i] = 0f

        }



        // Realizar FFT

        fft(real, imag)



        // Calcular magnitudes y fases

        var maxMagnitude = 0f

        var maxBin = 0

        var spectralSum = 0f

        var weightedFreqSum = 0f



        for (i in magnitudes.indices) {

            val re = real[i]

            val im = imag[i]

            var magnitude = sqrt(re * re + im * im)



            // Aplicar A-weighting si se solicita

            if (applyAWeighting) {

                magnitude *= aWeightingCoefficients[i]

            }



            magnitudes[i] = magnitude

            phases[i] = atan2(im, re)



            // Tracking para frecuencia dominante y centroide

            if (magnitude > maxMagnitude) {

                maxMagnitude = magnitude

                maxBin = maxBin

            }



            spectralSum += magnitude

            weightedFreqSum += magnitude * frequencyBins[i]

        }



        val dominantFreq = frequencyBins[maxBin]

        val spectralCentroid = if (spectralSum > 0f) weightedFreqSum / spectralSum else 0f



        return FFTResult(

            magnitudes = magnitudes.copyOf(),

            phases = phases.copyOf(),

            frequencyBins = frequencyBins.copyOf(),

            dominantFrequency = dominantFreq,

            spectralCentroid = spectralCentroid

        )

    }



    /**

     * Calcula dB SPL con A-weighting

     */

    fun calculateWeightedDB(buffer: ShortArray, size: Int = buffer.size): Double {

        val result = process(buffer, size, WindowType.BLACKMAN_HARRIS, applyAWeighting = true)



        // RMS de las magnitudes ponderadas

        var sum = 0.0

        for (i in result.magnitudes.indices) {

            sum += result.magnitudes[i] * result.magnitudes[i]

        }



        val rms = sqrt(sum / result.magnitudes.size)



        if (rms <= 0.0) return -160.0



        // Referencia: 20 ÂµPa = 0 dB SPL

        // CalibraciÃ³n empÃ­rica basada en dispositivo

        val dbFS = 20.0 * log10(rms)

        return dbFS + 94.0 // Offset de calibraciÃ³n (ajustar por dispositivo)

    }



    /**

     * Calcula RMS tradicional sin FFT (mÃ¡s rÃ¡pido para solo dB)

     */

    fun calculateRMS(buffer: ShortArray, size: Int = buffer.size): Double {

        var sum = 0.0

        val limit = minOf(size, buffer.size)



        if (limit == 0) return -160.0



        for (i in 0 until limit) {

            val sample = buffer[i].toDouble()

            sum += sample * sample

        }



        val rms = sqrt(sum / limit)

        return if (rms > 0.0) 20.0 * log10(rms / 32768.0) else -160.0

    }



    /**

     * FFT Cooley-Tukey optimizada con bit-reversal

     */

    private fun fft(real: FloatArray, imag: FloatArray) {

        val n = real.size

        val bits = (ln(n.toDouble()) / ln(2.0)).toInt()



        // Bit-reversal permutation

        for (i in 0 until n) {

            var j = 0

            for (k in 0 until bits) {

                j = (j shl 1) or ((i shr k) and 1)

            }

            if (j > i) {

                // Swap

                var temp = real[i]

                real[i] = real[j]

                real[j] = temp



                temp = imag[i]

                imag[i] = imag[j]

                imag[j] = temp

            }

        }



        // Cooley-Tukey FFT

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

// Add this method to the FFTProcessor class
    /**
     * Calcula la energía en bandas de frecuencia estándar (octavas 1/3)
     */
    fun calculateFrequencyBands(buffer: ShortArray, size: Int, bands: FloatArray): Boolean {
        if (bands.size != 10) return false

        val result = process(buffer, size, WindowType.BLACKMAN_HARRIS, applyAWeighting = false)

        // Definir bandas de frecuencia (octavas 1/3 en Hz)
        val bandFrequencies = arrayOf(
            Pair(22.4f, 44.7f),   // 31.5 Hz (banda 1)
            Pair(44.7f, 89.1f),   // 63 Hz (banda 2)
            Pair(89.1f, 178f),    // 125 Hz (banda 3)
            Pair(178f, 355f),     // 250 Hz (banda 4)
            Pair(355f, 710f),     // 500 Hz (banda 5)
            Pair(710f, 1420f),    // 1 kHz (banda 6)
            Pair(1420f, 2840f),   // 2 kHz (banda 7)
            Pair(2840f, 5680f),   // 4 kHz (banda 8)
            Pair(5680f, 11360f),  // 8 kHz (banda 9)
            Pair(11360f, 20000f)  // 16 kHz (banda 10)
        )

        for (i in bands.indices) {
            val (minFreq, maxFreq) = bandFrequencies[i]
            val energy = getEnergyInBand(result, minFreq, maxFreq)

            // Convertir a dB
            val db = if (energy > 0f) {
                20f * log10(energy) + 94f // Ajuste de calibración
            } else {
                0f
            }

            bands[i] = db.coerceIn(0f, 120f)
        }

        return true
    }

    /**

     * AnÃ¡lisis de energÃ­a por bandas de frecuencia

     */

    fun getEnergyInBand(result: FFTResult, minFreq: Float, maxFreq: Float): Float {

        var energy = 0f

        var count = 0



        for (i in result.frequencyBins.indices) {

            if (result.frequencyBins[i] in minFreq..maxFreq) {

                energy += result.magnitudes[i] * result.magnitudes[i]

                count++

            }

        }



        return if (count > 0) sqrt(energy / count) else 0f

    }



    enum class WindowType {

        HAMMING,

        BLACKMAN_HARRIS,

        HANN,

        NONE

    }

}