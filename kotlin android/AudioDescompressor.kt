package com.cepalabsfree.fichatech.audiostream

import android.util.Log
import java.util.zip.Inflater

/**
 * ✅ AudioDecompressor - Descompresión Zlib para ultra baja latencia
 * Compatible con compresión server-side (audio_compression.py)
 *
 * Reduce ancho de banda ~50% (Zlib) sin pérdida perceptible de calidad
 */
object AudioDecompressor {
    private const val TAG = "AudioDecompressor"

    // ✅ Flags para detectar audio comprimido
    const val FLAG_COMPRESSED = 1
    const val FLAG_UNCOMPRESSED = 0

    private val inflater = Inflater()

    /**
     * Descomprimir audio Zlib del servidor
     *
     * Formato esperado:
     * [4 bytes: tamaño original big-endian] + [datos Zlib comprimidos]
     *
     * @param compressedData: ByteArray con header y datos comprimidos
     * @return FloatArray descomprimido (PCM int16 → float32)
     */
    fun decompressZlib(compressedData: ByteArray): FloatArray {
        if (compressedData.size < 4) {
            Log.w(TAG, "Invalid compressed data - size ${compressedData.size} < 4")
            return FloatArray(0)
        }

        return try {
            // Leer header: tamaño original (4 bytes big-endian)
            val originalSize = ((compressedData[0].toInt() and 0xFF) shl 24) or
                    ((compressedData[1].toInt() and 0xFF) shl 16) or
                    ((compressedData[2].toInt() and 0xFF) shl 8) or
                    (compressedData[3].toInt() and 0xFF)

            if (originalSize <= 0 || originalSize > 1000000) {
                Log.w(TAG, "Invalid original size: $originalSize")
                return FloatArray(0)
            }

            // Descomprimir Zlib
            inflater.reset()
            inflater.setInput(compressedData, 4, compressedData.size - 4)

            val decompressed = ByteArray(originalSize)
            val uncompressedSize = inflater.inflate(decompressed)

            if (uncompressedSize != originalSize) {
                Log.w(TAG, "Size mismatch: $uncompressedSize vs $originalSize")
                return FloatArray(0)
            }

            // Convertir PCM int16 a float32
            pcm16ToFloat32(decompressed)

        } catch (e: Exception) {
            Log.e(TAG, "Decompression error: ${e.message}", e)
            FloatArray(0)
        }
    }

    /**
     * Convertir PCM int16 (little-endian) a float32 [-1.0, 1.0]
     */
    private fun pcm16ToFloat32(pcmData: ByteArray): FloatArray {
        val floatArray = FloatArray(pcmData.size / 2)

        for (i in pcmData.indices step 2) {
            if (i + 1 >= pcmData.size) break

            // Little-endian PCM int16
            val byte0 = pcmData[i].toInt() and 0xFF
            val byte1 = pcmData[i + 1].toInt() and 0xFF
            val pcmValue = (byte1 shl 8) or byte0

            // Convertir a int16 signed
            val sample = pcmValue.toShort()

            // Normalizar a float32
            floatArray[i / 2] = sample.toFloat() / 32768.0f
        }

        return floatArray
    }

    /**
     * Detectar si audio está comprimido por el flag en el packet
     */
    fun isCompressed(flags: Int): Boolean {
        return (flags and FLAG_COMPRESSED) != 0
    }

    /**
     * Procesar audio packet - descomprimir si es necesario
     */
    fun processAudioPacket(audioData: ByteArray, isCompressed: Boolean): FloatArray {
        return if (isCompressed) {
            decompressZlib(audioData)
        } else {
            // Audio sin comprimir - convertir directamente de bytes a float
            pcm16ToFloat32(audioData)
        }
    }

    /**
     * Limpiar recursos
     */
    fun release() {
        try {
            inflater.end()
        } catch (e: Exception) {
            Log.w(TAG, "Error releasing inflater")
        }
    }
}
