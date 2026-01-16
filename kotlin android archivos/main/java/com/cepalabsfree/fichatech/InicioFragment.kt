package com.cepalabsfree.fichatech

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.RequiresPermission
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.cepalabsfree.fichatech.audiostream.NativeAudioStreamActivity
import com.cepalabsfree.fichatech.sonometro.FFTProcessor
import com.cepalabsfree.fichatech.sonometro.WaveView
import com.google.android.material.button.MaterialButton
import com.google.android.material.floatingactionbutton.FloatingActionButton
import kotlin.math.PI
import kotlin.math.sin
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class InicioFragment : Fragment() {

    // ========== AUDIO COMPONENTS (modo decorativo) ==========
    private var audioRecord: AudioRecord? = null
    private var pinkNoisePlayer: MediaPlayer? = null
    private var isPinkNoisePlaying: Boolean = false

    // ========== UI COMPONENTS ==========
    private lateinit var waveView: WaveView
    private lateinit var btnWebsite: MaterialButton
    private lateinit var btnSonometro: MaterialButton
    private lateinit var btnPlanta: MaterialButton
    private lateinit var btnCanales: MaterialButton
    private lateinit var fabNoise: FloatingActionButton
    private lateinit var btnInstagram: MaterialButton

    // ========== STATE MANAGEMENT ==========
    private var isRecording = false
    private var isSimulated = false
    private val fftProcessor = FFTProcessor(FFT_PROCESSOR_SIZE)

    // ========== AUDIO CONFIGURATION ==========
    private val sampleRate = 44100
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)

    // ========== COROUTINES ==========
    private var decorativeJob: Job? = null
    private var simulatedJob: Job? = null

    // ========== CALIBRATION ==========
    private var calibrationOffset = 94.0

    // ========== PERMISSIONS ==========
    @SuppressLint("MissingPermission")
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            lifecycleScope.launch {
                delay(300)
                startDecorativeMeasurement()
            }
        } else {
            // Mostrar explicación y opción para conceder
            showPermissionRationale()
        }
    }

    @SuppressLint("MissingPermission")
    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val view = inflater.inflate(R.layout.fragment_inicio, container, false)
        initializeViews(view)
        setupListeners()
        setupWindowInsets(view)
        waveView.setDeviceInfo(
            model = Build.MODEL,
            calibration = calibrationOffset,
            source = "DEMO",
            measuring = false
        )
        // Iniciar medición decorativa solo si se tiene permiso
        if (hasAudioPermission()) {
            lifecycleScope.launch {
                delay(500)
                startDecorativeMeasurement()
            }
        } else {
            lifecycleScope.launch {
                delay(500)
                startSimulatedMeasurement()
            }
        }
        // No solicitar permiso automáticamente en la pantalla de bienvenida
        return view
    }

    @SuppressLint("MissingPermission")
    override fun onResume() {
        super.onResume()
        // Activar waveview cada vez que se vuelve a inicio
        if (hasAudioPermission() && !isRecording) {
            lifecycleScope.launch {
                delay(300) // Menor delay para activación rápida
                startDecorativeMeasurement()
            }
        } else if (!hasAudioPermission() && !isSimulated) {
            lifecycleScope.launch {
                delay(300)
                startSimulatedMeasurement()
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun initializeViews(view: View) {
        waveView = view.findViewById(R.id.waveView)
        waveView.setOnClickListener {
            if (!hasAudioPermission()) {
                requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            } else {
                // Permiso ya concedido, opcionalmente iniciar medición si no está activa
                if (!isRecording) {
                    lifecycleScope.launch {
                        startDecorativeMeasurement()
                    }
                }
            }
        }
        btnWebsite = view.findViewById(R.id.btnWebsite)
        btnSonometro = view.findViewById(R.id.btnSonometro)
        btnPlanta = view.findViewById(R.id.btnPlanta)
        btnCanales = view.findViewById(R.id.btnCanales)
        fabNoise = view.findViewById(R.id.fab_noise)
        btnInstagram = view.findViewById(R.id.btnInstagram)
    }

    private fun setupListeners() {
        // Botón sitio web
        btnWebsite.setOnClickListener {
            openWebsite("https://cepalabs.cl/fichatech")
        }


        // FAB ruido rosa
        fabNoise.setOnClickListener {
            togglePinkNoise()
        }

        // Botones de características (navegación)
        btnSonometro.setOnClickListener {
            navigateToMonitor()
        }

        btnPlanta.setOnClickListener {
            navigateToPlanta()
        }

        btnCanales.setOnClickListener {
            navigateToCanales()
        }

        // Botón Instagram
        btnInstagram.setOnClickListener {
            openWebsite("https://www.instagram.com/fichatech.cl/")
        }
    }

    private fun setupWindowInsets(view: View) {
        ViewCompat.setOnApplyWindowInsetsListener(view) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(
                v.paddingLeft,
                systemBars.top,
                v.paddingRight,
                systemBars.bottom
            )
            insets
        }
    }

    /**
     * Solicita permiso de audio para los visores decorativos
     */
    private fun requestAudioPermissionForDecorative() {
        // Siempre mostrar explicación antes de solicitar el permiso
        showPermissionRationale()
    }

    /**
     * Muestra un diálogo explicando por qué se necesita el permiso
     */
    private fun showPermissionRationale() {
        androidx.appcompat.app.AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.permission_title))
            .setMessage(getString(R.string.permission_message))
            .setPositiveButton(getString(R.string.grant_button)) { _, _ ->
                requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            }
            .setNegativeButton(getString(R.string.not_now_button)) { dialog, _ ->
                dialog.dismiss()
                Toast.makeText(context, getString(R.string.visualizers_disabled), Toast.LENGTH_SHORT).show()
            }
            .setCancelable(true)
            .show()
    }

    private fun hasAudioPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            requireContext(),
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * Inicia una medición decorativa de bajo consumo para los mini visores
     */
    @RequiresPermission(Manifest.permission.RECORD_AUDIO)
    private fun startDecorativeMeasurement() {
        if (isRecording || !hasAudioPermission()) return

        // Stop simulated if running
        if (isSimulated) {
            stopSimulatedMeasurement()
        }

        try {
            calibrationOffset = getDeviceCalibrationOffset()

            val audioSource = MediaRecorder.AudioSource.UNPROCESSED

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

            waveView.setMeasurementActive(true)
            waveView.setDeviceInfo(
                model = Build.MODEL,
                calibration = calibrationOffset,
                source = "LIVE",
                measuring = true
            )

            startDecorativeProcessing()

        } catch (e: Exception) {
            stopDecorativeMeasurement()
        }
    }

    /**
     * Procesa audio de forma ligera solo para decoración
     */
    private fun startDecorativeProcessing() {
        decorativeJob?.cancel()
        decorativeJob = lifecycleScope.launch(Dispatchers.IO) {
            val buffer = ShortArray(bufferSize)

            while (isActive && isRecording) {
                try {
                    val read = audioRecord?.read(buffer, 0, bufferSize) ?: 0

                    if (read > 0) {
                        // Cálculos ligeros para los medidores
                        val db = fftProcessor.calculateWeightedDB(buffer, read)
                        val adjustedDb = db + (calibrationOffset - 94.0)

                        withContext(Dispatchers.Main) {
                            waveView.updateDecibelValues(adjustedDb)
                        }
                    }

                    delay(DECORATIVE_UPDATE_INTERVAL_MS)

                } catch (e: Exception) {
                    break
                }
            }
        }
    }

    private fun stopDecorativeMeasurement() {
        if (!isRecording) return

        isRecording = false
        decorativeJob?.cancel()

        try {
            audioRecord?.apply {
                if (state == AudioRecord.STATE_INITIALIZED) {
                    stop()
                }
                release()
            }
        } catch (e: Exception) {
            // Ignorar errores al detener
        }

        audioRecord = null
        waveView.setMeasurementActive(false)
        waveView.reset()
    }

    /**
     * Inicia una medición simulada para mostrar ondas decorativas sin permiso
     */
    private fun startSimulatedMeasurement() {
        if (isSimulated) return

        calibrationOffset = getDeviceCalibrationOffset()

        isSimulated = true
        waveView.setMeasurementActive(true)
        waveView.setDeviceInfo(
            model = Build.MODEL,
            calibration = calibrationOffset,
            source = "SIMULATED",
            measuring = true
        )

        startSimulatedProcessing()
    }

    /**
     * Procesa datos simulados para mostrar ondas decorativas
     */
    private fun startSimulatedProcessing() {
        simulatedJob?.cancel()
        simulatedJob = lifecycleScope.launch(Dispatchers.IO) {
            val buffer = ShortArray(bufferSize)
            var phase = 0.0
            var modulationPhase = 0.0

            while (isActive && isSimulated) {
                // Generar onda sinusoidal con amplitud modulada para simular subida y bajada
                val amplitude = 1000 * (1 + sin(modulationPhase))
                for (i in buffer.indices) {
                    buffer[i] = (amplitude * sin(phase)).toInt().toShort()
                    phase += 2 * PI * 440 / sampleRate
                    if (phase > 2 * PI) phase -= 2 * PI
                }

                // Avanzar la fase de modulación para oscilar la amplitud a 1 Hz
                modulationPhase += 2 * PI * 1.0 * (DECORATIVE_UPDATE_INTERVAL_MS / 1000.0)
                if (modulationPhase > 2 * PI) modulationPhase -= 2 * PI

                // Calcular dB como en la medición real
                val db = fftProcessor.calculateWeightedDB(buffer, buffer.size)
                val adjustedDb = db + (calibrationOffset - 94.0)

                withContext(Dispatchers.Main) {
                    waveView.updateDecibelValues(adjustedDb)
                }

                delay(DECORATIVE_UPDATE_INTERVAL_MS)
            }
        }
    }

    /**
     * Detiene la medición simulada
     */
    private fun stopSimulatedMeasurement() {
        if (!isSimulated) return

        isSimulated = false
        simulatedJob?.cancel()
        waveView.setMeasurementActive(false)
        waveView.reset()
    }

    /**
     * Toggle ruido rosa
     */
    private fun togglePinkNoise() {
        if (!isPinkNoisePlaying) {
            try {
                pinkNoisePlayer = MediaPlayer.create(requireContext(), R.raw.pink_noise)
                pinkNoisePlayer?.isLooping = true
                pinkNoisePlayer?.setVolume(0.3f, 0.3f)
                pinkNoisePlayer?.start()
                isPinkNoisePlaying = true
                Toast.makeText(requireContext(), getString(R.string.pink_noise_started), Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(requireContext(), getString(R.string.error_playing_noise), Toast.LENGTH_SHORT).show()
            }
        } else {
            pinkNoisePlayer?.stop()
            pinkNoisePlayer?.release()
            pinkNoisePlayer = null
            isPinkNoisePlaying = false
            Toast.makeText(requireContext(), getString(R.string.pink_noise_stopped), Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Navega al monitor de audio
     */
    private fun navigateToMonitor() {
        // Navegar directamente a la actividad del monitor de audio (maneja permisos internamente)
        val intent = Intent(requireActivity(), NativeAudioStreamActivity::class.java)
        startActivity(intent)
    }

    /**
     * Navega a la planta de escenario
     */
    private fun navigateToPlanta() {
        parentFragmentManager.beginTransaction()
            .replace(R.id.fragment_container, com.cepalabsfree.fichatech.planta.PlantaEscenarioFragment())
            .addToBackStack(null)
            .commit()
    }

    /**
     * Navega a la lista de canales
     */
    private fun navigateToCanales() {
        parentFragmentManager.beginTransaction()
            .replace(R.id.fragment_container, com.cepalabsfree.fichatech.fichatecnica.FichaTecnicaFragment())
            .addToBackStack(null)
            .commit()
    }

    /**
     * Abre el sitio web
     */
    private fun openWebsite(url: String) {
        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(context, getString(R.string.could_not_open_browser), Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Abre cliente de email
     */
    private fun openEmail(email: String) {
        try {
            val intent = Intent(Intent.ACTION_SENDTO).apply {
                data = Uri.parse("mailto:$email")
                putExtra(Intent.EXTRA_SUBJECT, "Consulta FICHATECH")
            }
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(context, getString(R.string.could_not_open_email_client), Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Obtiene offset de calibración según dispositivo
     */
    private fun getDeviceCalibrationOffset(): Double {
        return when (Build.MODEL) {
            "Pixel 6", "Pixel 6 Pro", "Pixel 6a" -> 92.5
            "Pixel 7", "Pixel 7 Pro", "Pixel 7a" -> 93.0
            "Pixel 8", "Pixel 8 Pro" -> 93.5
            "SM-G991B", "SM-G996B" -> 94.2
            "SM-S901B", "SM-S906B" -> 94.5
            "SM-S911B", "SM-S916B" -> 94.8
            "SM-A525F" -> 91.5
            "SM-A536B" -> 92.0
            "Mi 11", "Mi 11 Pro" -> 92.0
            "Redmi Note 11" -> 90.5
            "OnePlus 9", "OnePlus 9 Pro" -> 93.0
            "OnePlus 10 Pro" -> 93.5
            else -> 94.0
        }
    }

    override fun onPause() {
        super.onPause()
        stopDecorativeMeasurement()
        stopSimulatedMeasurement()
    }

    override fun onDestroyView() {
        stopDecorativeMeasurement()
        stopSimulatedMeasurement()

        pinkNoisePlayer?.stop()
        pinkNoisePlayer?.release()
        pinkNoisePlayer = null
        isPinkNoisePlaying = false

        super.onDestroyView()
    }

    companion object {
        private const val FFT_PROCESSOR_SIZE = 2048
        private const val DECORATIVE_UPDATE_INTERVAL_MS = 100L // Más rápido para fluidez
    }
}