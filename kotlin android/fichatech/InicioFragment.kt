package com.cepalabsfree.fichatech

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.RequiresPermission
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.cepalabsfree.fichatech.sonometro.BpmView
import com.cepalabsfree.fichatech.sonometro.EqualizerFFTView
import com.cepalabsfree.fichatech.sonometro.EqualizerView
import com.cepalabsfree.fichatech.sonometro.FFTProcessor
import com.cepalabsfree.fichatech.sonometro.WaveView
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlin.math.max
import kotlin.math.pow

class InicioFragment : Fragment() {
    private var pinkNoisePlayer: MediaPlayer? = null
    private var isPinkNoisePlaying: Boolean = false

    // ========== NUEVO: PROCESADOR FFT CENTRALIZADO ==========
    private val fftProcessor = FFTProcessor(FFT_PROCESSOR_SIZE)

    // ========== CACHE DE RESULTADOS FFT ==========
    private var lastFFTResult: FFTProcessor.FFTResult? = null

    // ========== AUDIO COMPONENTS ==========
    private var audioRecord: AudioRecord? = null
    private var mediaPlayer: MediaPlayer? = null

    // ========== UI COMPONENTS ==========
    private lateinit var waveView: WaveView
    private lateinit var bpmView: BpmView
    private lateinit var tvDecibelValue: TextView
    private lateinit var tvLufsValue: TextView
    private lateinit var tvRmsValue: TextView
    private lateinit var equalizerView: EqualizerFFTView
    private lateinit var tunerView: EqualizerView

    // ========== RACK COMPONENTS ==========
    private lateinit var btnToggleMeasurements: MaterialButton
    private lateinit var tvBpmRack: TextView

    // ========== STATE MANAGEMENT ==========
    private var isRecording = false
    private var currentNoise: Int? = null
    private var measurementStartTime: Long = 0

    // ========== BPM DETECTION ==========
    private var lastPeakTime = 0L
    private val bpmBuffer = mutableListOf<Long>()
    private var currentBPM = 60.0
    private var peakThreshold = 0.15
    private var lastAmplitude = 0.0

    // ========== AUDIO CONFIGURATION ==========
    private val sampleRate = 44100
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)

    // ========== BUFFER POOL (OPTIMIZACIÃ“N MEMORIA) ==========
    private val bufferPool = mutableListOf<ShortArray>()

    // ========== CALIBRATION ==========
    private var calibrationOffset = 94.0

    // ========== COROUTINES ==========
    private var recordingJob: Job? = null
    private var bpmUpdateJob: Job? = null
    private val audioChannel = Channel<AudioData>(capacity = 10)

    data class AudioData(val buffer: ShortArray, val size: Int)

    // ========== VIEWMODEL PATTERN SIMPLIFICADO ==========
    private val _decibelLevel = MutableStateFlow(0.0)
    private val decibelLevel = _decibelLevel.asStateFlow()

    // ========== PERMISSIONS ==========
    @SuppressLint("MissingPermission")
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            lifecycleScope.launch {
                delay(500)
                startMeasurements()
            }
        } else {
        }
    }

    // ========== CALIBRATION BY DEVICE ==========
    private fun getDeviceCalibrationOffset(): Double {
        return when (Build.MODEL) {
            // Google Pixel
            "Pixel 6", "Pixel 6 Pro", "Pixel 6a" -> 92.5
            "Pixel 7", "Pixel 7 Pro", "Pixel 7a" -> 93.0
            "Pixel 8", "Pixel 8 Pro" -> 93.5
            // Samsung Galaxy S series
            "SM-G991B", "SM-G996B" -> 94.2 // Galaxy S21/S21+
            "SM-S901B", "SM-S906B" -> 94.5 // Galaxy S22/S22+
            "SM-S911B", "SM-S916B" -> 94.8 // Galaxy S23/S23+
            // Samsung Galaxy A series
            "SM-A525F" -> 91.5 // Galaxy A52
            "SM-A536B" -> 92.0 // Galaxy A53
            // Xiaomi
            "Mi 11", "Mi 11 Pro" -> 92.0
            "Redmi Note 11" -> 90.5
            // OnePlus
            "OnePlus 9", "OnePlus 9 Pro" -> 93.0
            "OnePlus 10 Pro" -> 93.5
            else -> 94.0 // Default seguro
        }
    }

    // ========== BUFFER POOL MANAGEMENT ==========
    private fun getBufferFromPool(): ShortArray {
        return synchronized(bufferPool) {
            bufferPool.removeFirstOrNull() ?: ShortArray(bufferSize)
        }
    }

    private fun recycleBufferToPool(buffer: ShortArray) {
        synchronized(bufferPool) {
            if (bufferPool.size < 10) {
                bufferPool.add(buffer)
            }
        }
    }

    // ========== RACK PERMISSION MANAGEMENT ==========
    private fun showPermissionRequestFromRack() {
        AlertDialog.Builder(requireContext())
            .setTitle("Permiso de Micrófono")
            .setMessage("Esta aplicación necesita acceso al micrófono para medir niveles de sonido, BPM y frecuencias.")
            .setPositiveButton("CONCEDER PERMISO") { _, _ ->
                requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            }
            .setNegativeButton("MÁS TARDE") { dialog, _ ->
                dialog.dismiss()
            }
            .setCancelable(false)
            .show()
    }

    // ========== MEASUREMENTS CONTROL ==========
    private fun toggleMeasurements() {
        if (isRecording) {
            stopMeasurements()
        } else {
            startMeasurements()
        }
    }

    private fun startMeasurements() {
        if (ContextCompat.checkSelfPermission(
                requireContext(),
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            showPermissionRequestFromRack()
            return
        }
        if (isRecording) return
        measurementStartTime = System.currentTimeMillis()
        // ✅ NUEVO: Notificar al WaveView que inició medición
        waveView.setMeasurementActive(true)
        startAudioProcessing()
        btnToggleMeasurements.setBackgroundColor(Color.parseColor("#F44336"))
        btnToggleMeasurements.setIconResource(R.drawable.ic_stop)
    }

    private fun stopMeasurements() {
        isRecording = false
        recordingJob?.cancel()
        // visualizer?.enabled = false
        // ✅ NUEVO: Notificar al WaveView que se pausó
        waveView.setMeasurementActive(false)
        btnToggleMeasurements.setBackgroundColor(Color.parseColor("#000000"))
        btnToggleMeasurements.setIconResource(R.drawable.ic_play)
        (System.currentTimeMillis() - measurementStartTime) / 1000
        waveView.reset()
        equalizerView.reset()
        tunerView.reset()
        bpmView.reset()
        tvDecibelValue.text = "0.0"
        tvLufsValue.text = "0.0"
        tvRmsValue.text = "0.0"
    }

    // ========== BPM DETECTION MEJORADO ==========
    private fun detectBPMImproved(
        buffer: ShortArray,
        size: Int,
        dbLevel: Double,
        fftResult: FFTProcessor.FFTResult?
    ) {
        val amplitude = 10.0.pow(dbLevel / 20.0)
        // âœ… NUEVO: AnÃ¡lisis de energÃ­a espectral
        val kickEnergy = if (fftResult != null) {
            fftProcessor.getEnergyInBand(fftResult, 60f, 100f).toDouble()
        } else {
            0.0
        }
        val snareEnergy = if (fftResult != null) {
            fftProcessor.getEnergyInBand(fftResult, 150f, 250f).toDouble()
        } else {
            0.0
        }
        // CombinaciÃ³n ponderada
        val combinedEnergy = kickEnergy * 0.6 + amplitude * 0.3 + snareEnergy * 0.1
        // Umbral adaptativo
        val adaptiveThreshold = if (kickEnergy > 0.05) {
            peakThreshold * 0.7
        } else {
            peakThreshold * 1.2
        }
        if (combinedEnergy > adaptiveThreshold && combinedEnergy > lastAmplitude * 1.2) {
            val currentTime = System.currentTimeMillis()
            if (currentTime - lastPeakTime > 300) {
                lastPeakTime = currentTime
                bpmBuffer.add(currentTime)
                if (bpmBuffer.size > 20) {
                    bpmBuffer.removeAt(0)
                }
                if (bpmBuffer.size >= 2) {
                    calculateBPMFromBuffer()
                }
            }
        }
        lastAmplitude = combinedEnergy
        lifecycleScope.launch(Dispatchers.Main) {
            bpmView.updateAmplitude(combinedEnergy)
            currentBPM = bpmView.getCurrentBPM()
            tvBpmRack.text = "%.0f".format(currentBPM)
        }
    }

    private fun calculateBPMFromBuffer() {
        if (bpmBuffer.size < 2) {
            currentBPM = 60.0
            return
        }
        val intervals = mutableListOf<Long>()
        for (i in 1 until bpmBuffer.size) {
            intervals.add(bpmBuffer[i] - bpmBuffer[i - 1])
        }
        val validIntervals = intervals.filter { it in 300L..2000L }
        if (validIntervals.isEmpty()) {
            currentBPM = 60.0
            return
        }
        val sorted = validIntervals.sorted()
        val q1 = sorted[sorted.size / 4].toDouble()
        val q3 = sorted[sorted.size * 3 / 4].toDouble()
        val iqr = q3 - q1
        val lowerBound = q1 - 1.5 * iqr
        val upperBound = q3 + 1.5 * iqr
        val filtered = sorted.filter {
            it.toDouble() in lowerBound..upperBound
        }
        if (filtered.isEmpty()) {
            currentBPM = 60.0
            return
        }
        val avgInterval = filtered.average()
        val calculatedBPM = 60000.0 / avgInterval
        currentBPM = (currentBPM * 0.8 + calculatedBPM * 0.2).coerceIn(30.0, 200.0)
        peakThreshold = 0.1 + (currentBPM / 1500.0)
    }

    private fun startBPMUpdateTask() {
        bpmUpdateJob?.cancel()
        bpmUpdateJob = lifecycleScope.launch {
            while (isActive) {
                delay(100)
                withContext(Dispatchers.Main) {
                    tvBpmRack.text = "%.0f".format(currentBPM)
                }
            }
        }
    }

    // ========== AUDIO PROCESSING - REEMPLAZAR EN InicioFragment.kt ==========
    @RequiresPermission(Manifest.permission.RECORD_AUDIO)
    private fun startAudioProcessing() {
        if (isRecording) {
            return
        }
        calibrationOffset = getDeviceCalibrationOffset()
        try {
            try {
                audioRecord?.apply {
                    if (state == AudioRecord.STATE_INITIALIZED) {
                        try {
                            stop()
                        } catch (e: Exception) {
                        }
                    }
                    release()
                }
            } catch (e: Exception) {
            }
            audioRecord = null
            var audioSourceName = "MIC"
            val audioSource = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                try {
                    val minBufferSize = AudioRecord.getMinBufferSize(
                        sampleRate,
                        channelConfig,
                        audioFormat
                    )
                    if (minBufferSize > 0) {
                        audioSourceName = "UNPROCESSED"
                        MediaRecorder.AudioSource.UNPROCESSED
                    } else {
                        audioSourceName = "MIC"
                        MediaRecorder.AudioSource.MIC
                    }
                } catch (e: Exception) {
                    audioSourceName = "MIC"
                    MediaRecorder.AudioSource.MIC
                }
            } else {
                audioSourceName = "MIC"
                MediaRecorder.AudioSource.MIC
            }
            audioRecord = AudioRecord(
                audioSource,
                sampleRate,
                channelConfig,
                audioFormat,
                bufferSize
            )
            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                audioRecord?.release()
                audioRecord = null
                return
            }
            isRecording = true
            audioRecord?.startRecording()
            // ✅ NUEVO: Actualizar información en WaveView
            waveView.setDeviceInfo(
                model = Build.MODEL,
                calibration = calibrationOffset,
                source = audioSourceName,
                measuring = true
            )
            startAudioProcessingCoroutine()
            startBPMUpdateTask()
        } catch (e: IllegalArgumentException) {
            Toast.makeText(context, "Configuración de audio no soportada", Toast.LENGTH_SHORT)
                .show()
            stopMeasurements()
        } catch (e: Exception) {
            Toast.makeText(context, "Error al iniciar grabación", Toast.LENGTH_SHORT).show()
            stopMeasurements()
        }
    }

    // ========== FUNCIÓN AUXILIAR PARA VALIDAR DISPONIBILIDAD ==========
    private fun startAudioProcessingCoroutine() {
        recordingJob?.cancel()
        recordingJob = lifecycleScope.launch(Dispatchers.IO) {
            val producerJob = launch {
                while (isActive && isRecording) {
                    try {
                        val buffer = getBufferFromPool()
                        val read = audioRecord?.read(buffer, 0, bufferSize) ?: 0
                        if (read > 0) {
                            if (!audioChannel.trySend(AudioData(buffer, read)).isSuccess) {
                                recycleBufferToPool(buffer)
                            }
                        } else {
                            recycleBufferToPool(buffer)
                            delay(50)
                        }
                    } catch (e: Exception) {
                        delay(100)
                    }
                }
            }
            var lastUpdateTime = 0L
            for (audioData in audioChannel) {
                if (!isActive) break
                val now = System.currentTimeMillis()
                if (now - lastUpdateTime >= UPDATE_INTERVAL_MS) {
                    lastUpdateTime = now
                    // âœ… MEJORADO: FFT una sola vez
                    val fftResult = if (audioData.size >= FFT_PROCESSOR_SIZE) {
                        fftProcessor.process(
                            audioData.buffer,
                            audioData.size,
                            FFTProcessor.WindowType.BLACKMAN_HARRIS,
                            applyAWeighting = false
                        )
                    } else null
                    lastFFTResult = fftResult
                    // âœ… MEJORADO: dB con A-weighting
                    val db = fftProcessor.calculateWeightedDB(audioData.buffer, audioData.size)
                    val adjustedDb = db + (calibrationOffset - 94.0)
                    val rmsDb = fftProcessor.calculateRMS(audioData.buffer, audioData.size)
                    val lufs = calculateLUFS(rmsDb)
                    _decibelLevel.value = adjustedDb
                    withContext(Dispatchers.Main) {
                        updateUI(adjustedDb, rmsDb, lufs)
                    }
                    detectBPMImproved(audioData.buffer, audioData.size, adjustedDb, fftResult)
                    if (fftResult != null) {
                        withContext(Dispatchers.Main) {
                            equalizerView.updateFFT(fftResult.magnitudes)
                            tunerView.updateAmplitudes(audioData.buffer)
                        }
                    }
                    withContext(Dispatchers.Main) {
                        waveView.updateRawBuffer(
                            audioData.buffer, audioData.size, calibrationOffset
                        )
                    }
                }
                recycleBufferToPool(audioData.buffer)
            }
            producerJob.cancel()
        }
    }

    private fun calculateLUFS(rmsDb: Double): Double {
        return rmsDb - 3.0
    }

    // ========== UI UPDATES ==========
    private fun updateUI(db: Double, rmsDb: Double, lufs: Double) {
        try {
            tvDecibelValue.text = String.format("%.1f", db)
            tvRmsValue.text = String.format("%.1f", rmsDb)
            tvLufsValue.text = String.format("%.1f", lufs)
            tvDecibelValue.setTextColor(
                when {
                    db >= 85 -> Color.RED
                    db >= 70 -> Color.parseColor("#FFA500")
                    db >= 55 -> Color.YELLOW
                    else -> Color.GREEN
                }
            )
        } catch (e: Exception) {
        }
    }

    // ========== NOISE GENERATION ==========
    private fun toggleSound(resId: Int, button: MaterialButton, otherButton: MaterialButton) {
        try {
            val isSameSoundPlaying = (mediaPlayer?.isPlaying == true && currentNoise == resId)
            if (isSameSoundPlaying) {
                mediaPlayer?.apply {
                    try {
                        if (isPlaying) stop()
                    } catch (e: IllegalStateException) {
                    }
                    release()
                }
                mediaPlayer = null
                currentNoise = null
                button.text = if (resId == R.raw.pink_noise) getString(R.string.pink_noise)
                else getString(R.string.white_noise)
            } else {
                mediaPlayer?.apply {
                    try {
                        if (isPlaying) stop()
                    } catch (e: IllegalStateException) {
                    }
                    release()
                }
                mediaPlayer = null
                otherButton.text = if (resId == R.raw.pink_noise) getString(R.string.white_noise)
                else getString(R.string.pink_noise)
                try {
                    mediaPlayer = MediaPlayer.create(requireContext(), resId)?.apply {
                        setOnErrorListener { mp, what, extra ->
                            mediaPlayer = null
                            currentNoise = null
                            button.text =
                                if (resId == R.raw.pink_noise) getString(R.string.pink_noise)
                                else getString(R.string.white_noise)
                            true
                        }
                        isLooping = true
                        setVolume(0.3f, 0.3f)
                        start()
                    }
                    if (mediaPlayer == null) {
                        throw IllegalStateException("MediaPlayer creation failed")
                    }
                    currentNoise = resId
                    button.text = getString(R.string.stop)
                } catch (e: Exception) {
                    mediaPlayer?.release()
                    mediaPlayer = null
                    currentNoise = null
                    button.text = if (resId == R.raw.pink_noise) getString(R.string.pink_noise)
                    else getString(R.string.white_noise)
                    Toast.makeText(context, "Error al reproducir audio", Toast.LENGTH_SHORT).show()
                }
            }
        } catch (e: Exception) {
            Toast.makeText(context, "Error en control de audio", Toast.LENGTH_SHORT).show()
            mediaPlayer?.release()
            mediaPlayer = null
            currentNoise = null
        }
    }

    // ========== LIFECYCLE ==========
    // ========== MODIFICAR onCreateView() ==========
    @SuppressLint("UnsafeRepeatOnLifecycleDetector")
    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View? {
        val view = inflater.inflate(R.layout.fragment_inicio, container, false)
        waveView = view.findViewById(R.id.waveView)
        // ✅ NUEVO: Configurar listener para cambios de modo
        waveView.setOnViewModeChangedListener { mode ->
            // Opcional: Mostrar notificación o cambiar UI según el modo
            when (mode) {
                WaveView.ViewMode.WAVEFORM -> {
                }
                WaveView.ViewMode.COMPRESSOR -> {
                }
                WaveView.ViewMode.SPECTRUM -> {
                }
                WaveView.ViewMode.OSCILLOSCOPE -> {
                }
            }
        }
        tvDecibelValue = view.findViewById(R.id.tvDecibelValue)
        tvLufsValue = view.findViewById(R.id.tvLufsValue)
        tvRmsValue = view.findViewById(R.id.tvRmsValue)
        equalizerView = view.findViewById(R.id.equalizerView)
        tunerView = view.findViewById(R.id.tunerView)
        btnToggleMeasurements = view.findViewById(R.id.btn_toggle_measurements)
        tvBpmRack = view.findViewById(R.id.tvBpmRack)
        btnToggleMeasurements.setOnClickListener {
            if (ContextCompat.checkSelfPermission(
                    requireContext(),
                    Manifest.permission.RECORD_AUDIO
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                showPermissionRequestFromRack()
            } else {
                toggleMeasurements()
            }
        }
        val fabNoise = view.findViewById<View>(R.id.fab_noise)
        fabNoise.setOnClickListener {
            if (!isPinkNoisePlaying) {
                pinkNoisePlayer = MediaPlayer.create(requireContext(), R.raw.pink_noise)
                pinkNoisePlayer?.isLooping = true
                pinkNoisePlayer?.setOnCompletionListener {
                    isPinkNoisePlaying = false
                }
                pinkNoisePlayer?.start()
                isPinkNoisePlaying = true
                Toast.makeText(requireContext(), "Ruido rosa iniciado", Toast.LENGTH_SHORT).show()
            } else {
                pinkNoisePlayer?.stop()
                pinkNoisePlayer?.release()
                pinkNoisePlayer = null
                isPinkNoisePlaying = false
                Toast.makeText(requireContext(), "Ruido rosa detenido", Toast.LENGTH_SHORT).show()
            }
        }
        bpmView = BpmView(requireContext())
        lifecycleScope.launch {
            repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) {
                decibelLevel.collect { db ->
                    if (tunerView.hasActiveFeedback()) {
                        tunerView.getFeedbackFrequencies()
                    }
                }
            }
        }
        tvBpmRack.text = "60"
        // ✅ NUEVO: Inicializar información por defecto en WaveView
        waveView.setDeviceInfo(
            model = Build.MODEL,
            calibration = calibrationOffset,
            source = "MIC",
            measuring = false
        )
        if (isRecording) {
            // Notificar al WaveView
            waveView.setMeasurementActive(true)
        }
        return view
    }

    private suspend fun clearAudioChannel() {
        if (!audioChannel.isClosedForReceive) {
            for (data in audioChannel) {
                recycleBufferToPool(data.buffer)
            }
        }
    }

    override fun onPause() {
        super.onPause()
        stopMeasurements()
    }

    override fun onDestroyView() {
        isRecording = false
        recordingJob?.cancel()
        recordingJob = null
        bpmUpdateJob?.cancel()
        bpmUpdateJob = null
        runBlocking {
            audioChannel.close()
            clearAudioChannel()
        }
        try {
            audioRecord?.apply {
                if (state == AudioRecord.STATE_INITIALIZED) {
                    stop()
                }
                release()
            }
        } catch (e: Exception) {
        }
        audioRecord = null
        try {
            mediaPlayer?.apply {
                if (isPlaying) stop()
                release()
            }
        } catch (e: Exception) {
        }
        mediaPlayer = null
        currentNoise = null
        bpmBuffer.clear()
        bufferPool.clear()
        pinkNoisePlayer?.stop()
        pinkNoisePlayer?.release()
        pinkNoisePlayer = null
        isPinkNoisePlaying = false
        super.onDestroyView()
    }

    companion object {
        private val FFT_PROCESSOR_SIZE = 2048
        private val UPDATE_INTERVAL_MS = 50L
    }
}
