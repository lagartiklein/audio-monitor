package com.cepalabsfree.fichatech.recording

import android.content.Context
import android.media.MediaRecorder
import android.os.Handler
import com.cepalabsfree.fichatech.WaveformView
import java.io.IOException

class RecordingManager(
    private val context: Context,
    private val waveformView: WaveformView,
    private val handler: Handler,
    private val startTimer: () -> Unit,
    private val stopTimer: () -> Unit
) {
    private var mediaRecorder: MediaRecorder? = null
    private var isRecording = false
    var outputFilePath: String? = null
    private val updateInterval = 100L // Intervalo de actualización de la onda

    private val updateWaveformRunnable = object : Runnable {
        override fun run() {
            if (isRecording) {
                val maxAmplitude = mediaRecorder?.maxAmplitude ?: 0
                waveformView.addAmplitude(maxAmplitude.toFloat())
                handler.postDelayed(this, updateInterval)
            }
        }
    }

    fun startRecording(recordingName: String) {
        if (isRecording) {
            return
        }

        val recordingStorage = RecordingStorage(context)
        val recordingFile = recordingStorage.getNewRecordingFile(recordingName)
        outputFilePath = recordingFile.absolutePath

        mediaRecorder = MediaRecorder().apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setAudioEncodingBitRate(128000)
            setAudioSamplingRate(44100)
            setOutputFile(recordingFile.absolutePath)
            try {
                prepare()
                start()
                isRecording = true
                startTimer()
                waveformView.startRecording()
                handler.post(updateWaveformRunnable)
            } catch (e: IOException) {
                e.printStackTrace()
            }
        }
    }

    fun stopRecording() {
        if (!isRecording) {
            return
        }

        mediaRecorder?.apply {
            stop()
            release()
        }
        mediaRecorder = null
        isRecording = false
        stopTimer()
        waveformView.stopRecording()
        handler.removeCallbacks(updateWaveformRunnable)
    }

    fun release() {
        if (isRecording) {
            stopRecording()
        }
    }
}
