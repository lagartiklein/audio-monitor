package com.cepalabsfree.fichatech.tuner

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.app.ActivityCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlin.math.*
import kotlin.math.log2
import kotlin.math.sqrt

class Tuner(a4: Float = 440f) {
    private val middleA = a4
    private val semitone = 69
    private val bufferSize = 4096
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var previousFrequency: Float = 0f
    var onNoteDetected: ((Note, Float) -> Unit)? = null

    // Frecuencias de referencia para cada nota
    private val referenceFrequencies = mapOf(
        "C0" to 16.35f, "C#0" to 17.32f, "D0" to 18.35f, "D#0" to 19.45f, "E0" to 20.6f,
        "F0" to 21.83f, "F#0" to 23.12f, "G0" to 24.5f, "G#0" to 25.96f, "A0" to 27.5f,
        "A#0" to 29.14f, "B0" to 30.87f, "C1" to 32.7f, "C#1" to 34.65f, "D1" to 36.71f,
        "D#1" to 38.89f, "E1" to 41.2f, "F1" to 43.65f, "F#1" to 46.25f, "G1" to 49f,
        "G#1" to 51.91f, "A1" to 55f, "A#1" to 58.27f, "B1" to 61.74f, "C2" to 65.41f,
        "C#2" to 69.3f, "D2" to 73.42f, "D#2" to 77.78f, "E2" to 82.41f, "F2" to 87.31f,
        "F#2" to 92.5f, "G2" to 98f, "G#2" to 103.83f, "A2" to 110f, "A#2" to 116.54f,
        "B2" to 123.47f, "C3" to 130.81f, "C#3" to 138.59f, "D3" to 146.83f, "D#3" to 155.56f,
        "E3" to 164.81f, "F3" to 174.61f, "F#3" to 185f, "G3" to 196f, "G#3" to 207.65f,
        "A3" to 220f, "A#3" to 233.08f, "B3" to 246.94f, "C4" to 261.63f, "C#4" to 277.18f,
        "D4" to 293.66f, "D#4" to 311.13f, "E4" to 329.63f, "F4" to 349.23f, "F#4" to 369.99f,
        "G4" to 392f, "G#4" to 415.3f, "A4" to 440f, "A#4" to 466.16f, "B4" to 493.88f,
        "C5" to 523.25f, "Do6" to 1046.5f, "Do#6" to 1108.73f, "Re6" to 1174.66f, "Re#6" to 1244.51f,
        "Mi6" to 1318.51f, "Fa6" to 1396.91f, "Fa#6" to 1479.98f, "Sol6" to 1567.98f,
        "Sol#6" to 1661.22f, "La6" to 1760.0f, "La#6" to 1864.66f, "Si6" to 1975.53f, "Do7" to 2093.0f,
        "Do#7" to 2217.46f, "Re7" to 2349.32f, "Re#7" to 2489.02f, "Mi7" to 2637.02f,
        "Fa7" to 2793.83f, "Fa#7" to 2959.96f, "Sol7" to 3135.96f, "Sol#7" to 3322.44f,
        "La7" to 3520.0f, "La#7" to 3729.31f, "Si7" to 3951.07f, "Do8" to 4186.01f
    )

    fun start(context: Context) {
        val minBufferSize = AudioRecord.getMinBufferSize(
            44100, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )

        // ✅ Solo verificar el permiso - El Fragment debe solicitarlo antes
        if (ActivityCompat.checkSelfPermission(
                context,
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            // ✅ No solicitar permisos desde aquí - solo registrar error
            android.util.Log.e("Tuner", "Permiso RECORD_AUDIO no concedido. El Fragment debe solicitarlo antes de llamar a start().")
            return
        }

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC, 44100,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, minBufferSize
        )
        audioRecord?.startRecording()
        isRecording = true

        CoroutineScope(Dispatchers.Default).launch {
            val buffer = ShortArray(bufferSize)
            while (isRecording) {
                val read = audioRecord?.read(buffer, 0, bufferSize) ?: 0
                if (read > 0) {
                    val frequency = detectPitch(buffer, read)
                    val db = calculateDb(buffer, read)
                    if (frequency != null && frequency != previousFrequency) {
                        previousFrequency = frequency
                        val note = getNoteDetails(frequency)
                        onNoteDetected?.invoke(note, db.toFloat())
                    }
                }
            }
        }
    }

    fun stop() {
        isRecording = false
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
    }

    private fun detectPitch(buffer: ShortArray, read: Int): Float? {
        val size = read / 2
        val audioData = FloatArray(size)
        for (i in 0 until size) {
            audioData[i] = (buffer[i * 2] / 32768.0f)
        }
        val pitchDetection = PitchDetection(audioData)
        return pitchDetection.detectPitch()
    }

    private fun calculateDb(buffer: ShortArray, read: Int): Double {
        var sum = 0.0
        for (i in 0 until read) {
            sum += (buffer[i] * buffer[i]).toDouble()
        }
        val rms = sqrt(sum / read)
        return 20 * log10(rms / 32768.0)
    }

    private fun getNoteDetails(frequency: Float): Note {
        // Buscar la nota más cercana a la frecuencia detectada
        var closestNote = ""
        var closestFrequency = Float.MAX_VALUE
        for ((note, refFrequency) in referenceFrequencies) {
            val diff = kotlin.math.abs(frequency - refFrequency)
            if (diff < closestFrequency) {
                closestFrequency = diff
                closestNote = note
            }
        }

        // Calcular el octavo de la nota
        val octave = (12 * log2(frequency / 440.0) + 69).toInt() / 12 - 1
        val cents = (1200 * log2(frequency / referenceFrequencies[closestNote]!!)).toInt()
        return Note(
            name = closestNote,
            frequency = frequency,
            octave = octave,
            value = semitone + (12 * log2(frequency / middleA)).toInt(),
            cents = cents
        )
    }
}

data class Note(
    val name: String,
    val frequency: Float,
    val octave: Int,
    val value: Int,
    val cents: Int
)
