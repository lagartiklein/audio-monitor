package com.cepalabsfree.fichatech.audiostream

import android.util.Log
import java.util.zip.Inflater

/**
 * ✅ AudioDecompressor - Descompresión Opus/Zlib para ultra baja latencia
 * Compatible con compresión server-side (audio_compression.py)
 *
 * Opus: Reduce ancho de banda ~96% con calidad profesional
 * Zlib: Reduce ancho de banda ~50% (fallback)
 */
object AudioDecompressor {
    private const val TAG = "AudioDecompressor"

    // ✅ Flags para detectar audio comprimido
    const val FLAG_COMPRESSED = 1
    const val FLAG_UNCOMPRESSED = 0

    private val inflater = Inflater()
    private var opusInitialized = false

    init {
        // ✅ Cargar librería nativa (fichatech_audio incluye Opus)
        try {
            System.loadLibrary("fichatech_audio")
            Log.i(TAG, "✅ Native library loaded successfully")
        } catch (e: UnsatisfiedLinkError) {
            Log.w(TAG, "⚠️ Native library not available: ${e.message}")
        }
    }

    /**
     * ✅ Inicializar decoder Opus
     * Debe llamarse ANTES de usar descompresión Opus
     */
    fun initOpusDecoder(sampleRate: Int, channels: Int) {
        try {
            initOpusDecoderNative(sampleRate, channels)
            opusInitialized = true
            Log.i(TAG, "✅ Opus decoder inicializado: ${sampleRate}Hz, ${channels}ch")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error inicializando Opus: ${e.message}")
            opusInitialized = false
        }
    }

    private external fun initOpusDecoderNative(sampleRate: Int, channels: Int)

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
     * Procesar audio packet - descomprimir según método
     */
    fun processAudioPacket(audioData: ByteArray, compressionMethod: String = "none"): FloatArray {
        return when (compressionMethod.lowercase()) {
            "opus" -> decompressOpus(audioData, 48000, 2)
            "zlib" -> decompressZlib(audioData)
            "none" -> pcm16ToFloat32(audioData)
            else -> {
                Log.w(TAG, "Unknown compression method: $compressionMethod, using none")
                pcm16ToFloat32(audioData)
            }
        }
    }

    /**
     * ✅ Descomprimir audio Opus usando JNI
     */
    private external fun decompressOpusNative(compressedData: ByteArray, sampleRate: Int, channels: Int): FloatArray

    /**
     * ✅ Liberar recursos Opus
     */
    private external fun releaseOpusDecoder()

    /**
     * ✅ Obtener versión de Opus
     */
    external fun getOpusVersion(): String

    /**
     * Descomprimir audio Opus con fallback a Zlib
     */
    private fun decompressOpus(compressedData: ByteArray, sampleRate: Int, channels: Int): FloatArray {
        if (!opusInitialized) {
            Log.w(TAG, "⚠️ Opus no inicializado, usando Zlib fallback")
            return decompressZlib(compressedData)
        }

        return try {
            decompressOpusNative(compressedData, sampleRate, channels)
        } catch (e: UnsatisfiedLinkError) {
            Log.w(TAG, "⚠️ Opus JNI not available, falling back to Zlib: ${e.message}")
            decompressZlib(compressedData)
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error decompressing Opus: ${e.message}")
            FloatArray(0)
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

        // ✅ Liberar decoder Opus
        if (opusInitialized) {
            try {
                releaseOpusDecoder()
                opusInitialized = false
                Log.d(TAG, "🧹 Opus decoder released")
            } catch (e: Exception) {
                Log.w(TAG, "Error releasing Opus: ${e.message}")
            }
        }
    }
}