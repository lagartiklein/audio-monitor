package com.cepalabsfree.fichatech.audiostream

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.media.AudioManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.util.Log
import android.view.View
import android.view.ViewTreeObserver
import android.view.WindowManager
import android.widget.*
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.cepalabsfree.fichatech.R
import com.cepalabsfree.fichatech.audiostream.AudioDeviceChangeListener
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.AdView
import com.google.android.gms.ads.MobileAds
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.isActive
import kotlin.math.*

/**
 * ✅ AudioStream Activity SIMPLIFICADO
 * - Sin Foreground Service
 * - Audio se detiene al salir de la Activity
 * - Gestión directa de WakeLocks
 */
class NativeAudioStreamActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "AudioStreamRF"
        private const val PREFS_NAME = "AudioStreamPrefs"
        private const val KEY_LAST_IP = "last_ip"
        private const val KEY_LAST_PORT = "last_port"
        private const val KEY_MASTER_VOLUME = "master_volume"

        private const val METRICS_UPDATE_INTERVAL_MS = 250L
    }

    private lateinit var audioClient: NativeAudioClient
    private lateinit var audioRenderer: OboeAudioRenderer
    private lateinit var audioManager: AudioManager
    private lateinit var audioFocusManager: AudioFocusManager

    private lateinit var statusText: TextView
    private lateinit var ipEditText: EditText
    private lateinit var portEditText: EditText
    private lateinit var connectButton: Button
    private lateinit var masterVolumeSeekBar: SeekBar
    private lateinit var masterVolumeText: TextView
    private lateinit var muteButton: Button
    private lateinit var latencyText: TextView
    private lateinit var infoText: TextView
    private lateinit var ultraLowLatencySwitch: Switch

    // ✅ Elementos de bloqueo de pantalla
    private lateinit var lockSlider: FrameLayout
    private lateinit var lockIcon: TextView
    private lateinit var lockTrack: View
    private lateinit var lockInstructionText: TextView
    private lateinit var screenLockOverlay: View
    private lateinit var lockBarContainer: RelativeLayout
    private lateinit var nativeAudioContainer: LinearLayout

    private var isScreenLocked = false
    private var sliderStartX = 0f
    private var sliderMaxX = 0f
    private var globalLayoutListener: ViewTreeObserver.OnGlobalLayoutListener? = null
    private var isCurrentOrientation = Configuration.ORIENTATION_PORTRAIT

    private var isConnected = false
    private var isConnecting = false
    private var isMuted = false
    private var masterVolumeDb = 0f

    private var isMetricsActive = false

    private val uiHandler = Handler(Looper.getMainLooper())
    private var metricsUpdateRunnable: Runnable? = null

    // Nueva variable para el WakeLock del slider de bloqueo
    private var lockWakeLock: android.os.PowerManager.WakeLock? = null

    // Variable para el tamaño del buffer
    private var bufferSizeFrames: Int = 128 // Valor por defecto normal

    // Variables de reconexión automática y cambio de audio
    private var autoReconnectJob: Job? = null
    private var audioDeviceChangeListener: AudioDeviceChangeListener? = null
    private var lastConnectionAttempt: Long = 0
    private var connectionAttempts: Int = 0
    private val MAX_CONNECTION_ATTEMPTS = 5
    private val CONNECTION_RETRY_DELAY_MS = 500L

    // Buffer reutilizable para interleaving estéreo
    private var reusableInterleavedBuffer: FloatArray? = null

    // Job para renovar el WakeLock parcialmente
    private var wakeLockRenewJob: Job? = null

    // AdMob
    private lateinit var adViewAudioStream: AdView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        }

        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
        enableEdgeToEdge()
        hideSystemUI()
        setContentView(R.layout.activity_native_receiver)
        setupEdgeToEdgeInsets()
        configureAudioSystemForLowLatency()
        initializeViews()
        initializeAudioComponents()
        loadSessionPreferences()

        // AdMob
        adViewAudioStream = findViewById(R.id.adViewAudioStream)
        MobileAds.initialize(this) {}
        val adRequest = AdRequest.Builder().build()
        adViewAudioStream.loadAd(adRequest)
    }

    private fun configureAudioSystemForLowLatency() {
        try {
            audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

            val sampleRateStr = audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)
            val framesPerBufferStr = audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)
            val optimalSampleRate = sampleRateStr?.toIntOrNull() ?: 48000
            val optimalBufferSize = framesPerBufferStr?.toIntOrNull() ?: 128

            Log.d(TAG, "🎵 Sistema: $optimalSampleRate Hz, buffer=$optimalBufferSize frames")
        } catch (e: Exception) {
            Log.e(TAG, "Error configurando sistema de audio: ${e.message}")
        }
    }

    @SuppressLint("SetTextI18n")
    private fun initializeViews() {
        statusText = findViewById(R.id.statusText)
        ipEditText = findViewById(R.id.ipEditText)
        portEditText = findViewById(R.id.portEditText)
        connectButton = findViewById(R.id.connectButton)
        masterVolumeSeekBar = findViewById(R.id.masterVolumeSeekBar)
        masterVolumeText = findViewById(R.id.masterVolumeText)
        muteButton = findViewById(R.id.muteButton)
        latencyText = findViewById(R.id.latencyText)
        infoText = findViewById(R.id.infoText)
        ultraLowLatencySwitch = findViewById(R.id.ultraLowLatencySwitch)

        // ✅ Inicializar elementos de bloqueo ANTES de setupLockSlider
        lockSlider = findViewById(R.id.lockSlider)
        lockIcon = findViewById(R.id.lockIcon)
        lockTrack = findViewById(R.id.lockTrack)
        lockInstructionText = findViewById(R.id.lockInstructionText)
        screenLockOverlay = findViewById(R.id.screenLockOverlay)
        lockBarContainer = findViewById(R.id.lockBarContainer)
        nativeAudioContainer = findViewById(R.id.native_audio_container)

        // Al abrir la actividad, el candado debe estar desbloqueado
        lockSlider.setBackgroundColor(android.graphics.Color.parseColor("#FF4081"))
        lockIcon.text = "\uD83D\uDD13"  // 🔓 Unicode correcto

        // ✅ Configurar slider DESPUÉS de que todas las vistas estén inicializadas
        setupLockSlider()

        connectButton.setOnClickListener {
            if (isConnected) {
                disconnect()
            } else {
                connectToServer()
            }
        }

        masterVolumeSeekBar.max = 72
        masterVolumeSeekBar.progress = 60
        masterVolumeSeekBar.setOnSeekBarChangeListener(
            object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                    masterVolumeDb = (progress - 60).toFloat()
                    masterVolumeText.text = String.format("%.0f dB", masterVolumeDb)
                    audioRenderer.setMasterGain(if (isMuted) -60f else masterVolumeDb)
                }
                override fun onStartTrackingTouch(seekBar: SeekBar?) {}
                override fun onStopTrackingTouch(seekBar: SeekBar?) {
                    saveSessionPreferences()
                }
            }
        )

        muteButton.setOnClickListener { toggleMute() }

        latencyText.setOnLongClickListener {
            if (isConnected) {
                audioRenderer.recreateAllStreams()
            }
            true
        }

        statusText.text = "FICHATECH RETRO"
        connectButton.text = "Conectar"
        muteButton.text = "Audio ON"

        ultraLowLatencySwitch.isChecked = false
        ultraLowLatencySwitch.setOnCheckedChangeListener { _, isChecked ->
            bufferSizeFrames = if (isChecked) 32 else 128
            if (isConnected) {
                audioRenderer.setBufferSize(bufferSizeFrames)
            }
        }
    }

    private fun initializeAudioComponents() {
        audioFocusManager = AudioFocusManager(this)

        audioClient = NativeAudioClient(this).apply {
            onAudioData = { audioData -> handleAudioData(audioData) }
            onConnectionStatus = { connected, message ->
                updateConnectionStatus(connected, message)
            }
            onServerInfo = { info -> handleServerInfo(info) }
            onError = { error ->
                lifecycleScope.launch {
                    if (!isFinishing && !isDestroyed) {
                        showError("Error: $error")
                    }
                }
            }
            onMasterGainUpdate = { gainDb ->
                lifecycleScope.launch(Dispatchers.Main) {
                    if (!isFinishing && !isDestroyed) {
                        masterVolumeDb = gainDb
                        audioRenderer.setMasterGain(gainDb)
                        masterVolumeSeekBar.progress = (gainDb + 60).toInt()
                        masterVolumeText.text = String.format("%.0f dB", gainDb)
                    }
                }
            }
            onMixStateUpdate = { mixState ->
                lifecycleScope.launch(Dispatchers.Main) {
                    if (!isFinishing && !isDestroyed) {
                        (mixState["master_gain"] as? Float)?.let { gainLinear ->
                            val gainDb = linearToDb(gainLinear)
                            masterVolumeDb = gainDb
                            audioRenderer.setMasterGain(gainDb)
                            masterVolumeSeekBar.progress = (gainDb + 60).toInt()
                            masterVolumeText.text = String.format("%.0f dB", gainDb)
                        }
                    }
                }
            }
        }

        audioRenderer = OboeAudioRenderer(this).apply { setMasterGain(masterVolumeDb) }

        // ✅ Registrar listener para cambio de dispositivo de audio
        audioDeviceChangeListener = AudioDeviceChangeListener {
            Log.d(TAG, "🔊 Cambio de dispositivo de audio detectado")
            if (isConnected) {
                restartAudioEngine()
            }
        }
        audioDeviceChangeListener?.register(this)
    }

    private fun saveSessionPreferences() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().apply {
            putString(KEY_LAST_IP, ipEditText.text.toString())
            putString(KEY_LAST_PORT, portEditText.text.toString())
            putFloat(KEY_MASTER_VOLUME, masterVolumeDb)
            apply()
        }
    }

    private fun loadSessionPreferences() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val lastIp = prefs.getString(KEY_LAST_IP, "")
        val lastPort = prefs.getString(KEY_LAST_PORT, "5101")
        val savedVolume = prefs.getFloat(KEY_MASTER_VOLUME, 0f)

        if (!lastIp.isNullOrEmpty()) {
            ipEditText.setText(lastIp)
        }
        if (!lastPort.isNullOrEmpty()) {
            portEditText.setText(lastPort)
        }

        masterVolumeDb = savedVolume
        masterVolumeSeekBar.progress = (savedVolume + 60).toInt()
        masterVolumeText.text = String.format("%.0f dB", savedVolume)
    }

    private fun toggleMute() {
        isMuted = !isMuted
        if (isMuted) {
            audioRenderer.setMasterGain(-60f)
            muteButton.text = "Audio OFF"
            muteButton.setBackgroundColor(android.graphics.Color.parseColor("#FF4081"))
            muteButton.setTextColor(android.graphics.Color.WHITE)
        } else {
            audioRenderer.setMasterGain(masterVolumeDb)
            muteButton.text = "Audio ON"
            muteButton.setBackgroundColor(android.graphics.Color.BLACK)
            muteButton.setTextColor(android.graphics.Color.WHITE)
        }
    }

    private fun connectToServer() {
        if (isConnecting) {
            return
        }

        val serverIp = ipEditText.text.toString().trim()
        if (serverIp.isEmpty()) {
            showToast("⚠️ Ingresa una dirección IP")
            return
        }

        val serverPort = portEditText.text.toString().toIntOrNull() ?: 5101

        isConnecting = true
        connectButton.isEnabled = false
        connectButton.text = "Conectando..."
        statusText.text = "Buscando señal..."

        lifecycleScope.launch {
            try {
                audioFocusManager.requestAudioFocus()
                audioRenderer.acquirePartialWakeLock(applicationContext)
                audioRenderer.setBufferSize(bufferSizeFrames)

                val success = audioClient.connect(serverIp, serverPort)
                if (success) {
                    saveSessionPreferences()
                    delay(500L)
                    withContext(Dispatchers.Main) {
                        showToast("Online")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error conectando: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    showError("Error de conexión:\n${e.message}")
                    audioRenderer.releaseWakeLock()
                    audioFocusManager.abandonAudioFocus()
                }
            } finally {
                withContext(Dispatchers.Main) {
                    isConnecting = false
                    connectButton.isEnabled = true
                    connectButton.text = if (isConnected) "Desconectar" else "Conectar"
                }
            }
        }
    }

    private fun handleServerInfo(info: Map<String, Any>) {
        runOnUiThread {
            val serverVersion = info["server_version"] as? String
            if (serverVersion != null) {
                infoText.text = "• Conecta a la misma red WiFi que el servidor.\n" +
                        "• Mantén el punto de acceso cerca del escenario."
            }
        }
    }

    private fun handleAudioData(audioData: NativeAudioClient.FloatAudioData) {
        if (audioData.audioData.size >= 2) {
            val samplesPerChannel = audioData.samplesPerChannel
            val requiredSize = samplesPerChannel * 2
            if (reusableInterleavedBuffer == null || reusableInterleavedBuffer!!.size < requiredSize) {
                reusableInterleavedBuffer = FloatArray(requiredSize)
            }
            val interleaved = reusableInterleavedBuffer!!
            for (s in 0 until samplesPerChannel) {
                interleaved[s * 2] = audioData.audioData[0][s]
                interleaved[s * 2 + 1] = audioData.audioData[1][s]
            }
            audioRenderer.renderStereo(interleaved, audioData.samplePosition)
        }
    }

    private fun updateConnectionStatus(connected: Boolean, message: String) {
        isConnected = connected

        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread

            if (connected) {
                statusText.text = message
                statusText.setTextColor(android.graphics.Color.WHITE)
                connectButton.text = "Desconectar"
                connectButton.setBackgroundColor(android.graphics.Color.parseColor("#FF4081"))
                connectButton.setTextColor(android.graphics.Color.WHITE)
                connectionAttempts = 0
                autoReconnectJob?.cancel()

                try {
                    audioRenderer.acquirePartialWakeLock(applicationContext)
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ No se pudo adquirir PartialWakeLock: ${e.message}")
                }

                try {
                    window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                } catch (_: Exception) {}

                wakeLockRenewJob?.cancel()
                wakeLockRenewJob = lifecycleScope.launch {
                    try {
                        while (isActive && isConnected) {
                            delay(5 * 60 * 1000L)
                            audioRenderer.renewPartialWakeLock()
                            Log.d(TAG, "🔋 PartialWakeLock renovado")
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "⚠️ Error renovando wakeLock: ${e.message}")
                    }
                }

            } else {
                statusText.text = message
                statusText.setTextColor(android.graphics.Color.WHITE)
                connectButton.text = "Conectar"
                connectButton.setBackgroundColor(android.graphics.Color.BLACK)
                connectButton.setTextColor(android.graphics.Color.WHITE)

                if ((message.contains("BUSCANDO") || message.contains("perdida")) &&
                    autoReconnectJob?.isActive != true) {
                    startAutoReconnect()
                }

                wakeLockRenewJob?.cancel()
                wakeLockRenewJob = null
                try {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                } catch (_: Exception) {}
            }
        }
    }

    private fun disconnect() {
        audioClient.disconnect("Desconexión manual")
        audioRenderer.releaseWakeLock()
        audioFocusManager.abandonAudioFocus()

        runOnUiThread {
            statusText.text = "OFFLINE"
            connectButton.text = "Conectar"
            saveSessionPreferences()
        }
    }

    private fun startMetricsUpdates() {
        if (isMetricsActive) return

        isMetricsActive = true

        metricsUpdateRunnable = object : Runnable {
            override fun run() {
                if (!isFinishing && !isDestroyed && isMetricsActive) {
                    runOnUiThread {
                        if (isConnected) {
                            val latency = audioRenderer.getLatencyMs()
                            latencyText.text = "${latency.toInt()} ms"
                            latencyText.setTextColor(
                                when {
                                    latency < 15 -> getColor(android.R.color.white)
                                    latency < 30 -> getColor(android.R.color.holo_orange_light)
                                    else -> getColor(android.R.color.holo_red_light)
                                }
                            )

                            if (System.currentTimeMillis() % 10000 < METRICS_UPDATE_INTERVAL_MS) {
                                val stats = audioRenderer.getRFStats()
                                val totalFailures = stats["total_failures"] as? Int ?: 0

                                if (totalFailures > 5) {
                                    statusText.text = "⚠️ Streams con errores (long press latencia)"
                                    statusText.setTextColor(getColor(android.R.color.holo_orange_light))
                                }
                            }
                        } else {
                            latencyText.text = "-- ms"
                        }
                    }

                    if (isMetricsActive) {
                        uiHandler.postDelayed(this, METRICS_UPDATE_INTERVAL_MS)
                    }
                }
            }
        }

        uiHandler.post(metricsUpdateRunnable!!)
        Log.d(TAG, "👁️ Métricas INICIADAS (cada ${METRICS_UPDATE_INTERVAL_MS}ms)")
    }

    private fun stopMetricsUpdates() {
        isMetricsActive = false

        metricsUpdateRunnable?.let {
            uiHandler.removeCallbacks(it)
            metricsUpdateRunnable = null
        }

        Log.d(TAG, "🛑 Métricas DETENIDAS")
    }

    private fun showError(message: String) {
        if (isFinishing || isDestroyed) return
        runOnUiThread {
            Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        }
    }

    private fun showToast(message: String) {
        runOnUiThread {
            if (!isFinishing && !isDestroyed) {
                Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
            }
        }
    }

    /**
     * Sincroniza el estado visual del slider y overlay según isScreenLocked
     */
    private fun syncLockSliderState() {
        if (!::lockSlider.isInitialized || !::lockTrack.isInitialized || !::lockIcon.isInitialized) return

        recalculateLockDimensions()
        updateLockSliderVisuals()

        if (isScreenLocked) {
            screenLockOverlay.visibility = View.VISIBLE
            screenLockOverlay.alpha = 1f
            screenLockOverlay.setBackgroundColor(android.graphics.Color.BLACK)
            screenLockOverlay.bringToFront()
            lockBarContainer.bringToFront()
            screenLockOverlay.isClickable = true
            screenLockOverlay.isFocusable = true
            lockInstructionText.text = "◀ Desliza para desbloquear"
            adViewAudioStream.visibility = View.GONE
        } else {
            screenLockOverlay.visibility = View.GONE
            screenLockOverlay.alpha = 1f
            screenLockOverlay.isClickable = false
            screenLockOverlay.isFocusable = false
            lockInstructionText.text = "Desliza para bloquear ▶"
            adViewAudioStream.visibility = View.VISIBLE
        }
    }

    /**
     * Actualiza la posición y fondo del slider según el estado de bloqueo
     */
    private fun updateLockSliderVisuals() {
        if (!::lockSlider.isInitialized || !::lockTrack.isInitialized || !::lockIcon.isInitialized) return

        try {
            sliderStartX = lockTrack.x
            val maxValidX = (lockTrack.x + sliderMaxX).coerceAtMost(lockTrack.x + lockTrack.width - lockSlider.width)

            if (isScreenLocked) {
                lockSlider.x = maxValidX
                lockSlider.setBackgroundColor(android.graphics.Color.BLACK)
                lockIcon.text = "\uD83D\uDD12"  // 🔒 Unicode correcto
                Log.d(TAG, "🔒 Slider sincronizado - posición locked")
            } else {
                lockSlider.x = lockTrack.x
                lockSlider.setBackgroundColor(android.graphics.Color.parseColor("#FF4081"))
                lockIcon.text = "\uD83D\uDD13"  // 🔓 Unicode correcto
                Log.d(TAG, "🔓 Slider sincronizado - posición unlocked")
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error actualizando visuals: ${e.message}")
        }
    }

    private fun acquireLockWakeLock() {
        if (lockWakeLock == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            lockWakeLock = pm.newWakeLock(
                android.os.PowerManager.SCREEN_BRIGHT_WAKE_LOCK or android.os.PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "fichatech:LockSliderWakeLock"
            )
        }
        if (lockWakeLock?.isHeld != true) {
            lockWakeLock?.acquire(60_000L)
            Log.d(TAG, "🔓 WakeLock de slider adquirido (timeout 60s)")
        }
    }

    private fun releaseLockWakeLock() {
        if (lockWakeLock?.isHeld == true) {
            lockWakeLock?.release()
            Log.d(TAG, "🌙 WakeLock de slider liberado")
        }
    }

    override fun onResume() {
        super.onResume()
        startMetricsUpdates()

        if (globalLayoutListener != null && lockTrack.viewTreeObserver.isAlive) {
            try {
                lockTrack.viewTreeObserver.removeOnGlobalLayoutListener(globalLayoutListener)
            } catch (e: Exception) {
                Log.w(TAG, "Advertencia al remover listener previo: ${e.message}")
            }
        }

        globalLayoutListener = ViewTreeObserver.OnGlobalLayoutListener {
            try {
                if (lockTrack.viewTreeObserver.isAlive) {
                    lockTrack.viewTreeObserver.removeOnGlobalLayoutListener(globalLayoutListener)
                }
            } catch (e: Exception) {
                Log.w(TAG, "Advertencia al remover listener: ${e.message}")
            }

            lockTrack.post {
                syncLockSliderState()
            }
            Log.d(TAG, "👁️ Listener - Layout listo, slider sincronizado")
        }

        lockTrack.viewTreeObserver.addOnGlobalLayoutListener(globalLayoutListener)
        Log.d(TAG, "👁️ Activity visible - monitoreo activo")

        adViewAudioStream.resume()
        adViewAudioStream.visibility = View.VISIBLE
    }

    override fun onPause() {
        super.onPause()
        stopMetricsUpdates()

        globalLayoutListener?.let { existing ->
            if (lockTrack.viewTreeObserver.isAlive) {
                try {
                    lockTrack.viewTreeObserver.removeOnGlobalLayoutListener(existing)
                } catch (e: Exception) {
                    Log.w(TAG, "Advertencia al remover listener en onPause: ${e.message}")
                }
            }
            globalLayoutListener = null
        }

        if (isConnected) {
            disconnect()
        }
        Log.d(TAG, "🤤 Activity pausada - monitoreo detenido, stream detenido")

        adViewAudioStream.pause()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopMetricsUpdates()

        autoReconnectJob?.cancel()
        audioDeviceChangeListener?.unregister(this)

        if (isConnected) {
            disconnect()
        }

        wakeLockRenewJob?.cancel()
        wakeLockRenewJob = null

        audioRenderer.release()
        audioFocusManager.abandonAudioFocus()
        saveSessionPreferences()
        releaseLockWakeLock()

        adViewAudioStream.destroy()

        Log.d(TAG, "💀 Activity destruida - recursos liberados")
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)

        val newOrientation = if (newConfig.orientation == Configuration.ORIENTATION_LANDSCAPE) {
            Configuration.ORIENTATION_LANDSCAPE
        } else {
            Configuration.ORIENTATION_PORTRAIT
        }

        if (newOrientation != isCurrentOrientation) {
            isCurrentOrientation = newOrientation
            val orientationName = if (newOrientation == Configuration.ORIENTATION_LANDSCAPE) "LANDSCAPE" else "PORTRAIT"
            Log.d(TAG, "📄 Rotación detectada: $orientationName")

            lockTrack.post {
                syncLockSliderState()
                try {
                    val leftX = lockTrack.x
                    val rightX = (lockTrack.x + sliderMaxX).coerceAtMost(lockTrack.x + lockTrack.width - lockSlider.width)

                    // Cancelar animación previa
                    lockSlider.animate().cancel()

                    if (isScreenLocked) {
                        lockSlider.animate().x(rightX).setDuration(120).start()
                    } else {
                        lockSlider.animate().x(leftX).setDuration(120).start()
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Error forzando posición tras rotación: ${e.message}")
                }
                Log.d(TAG, "✅ Slider sincronizado tras rotación")
            }
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemUI()
    }

    private fun hideSystemUI() {
        val controller = androidx.core.view.WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    private fun linearToDb(linear: Float): Float =
        if (linear > 0) 20.0f * Math.log10(linear.toDouble()).toFloat() else -60f

    private fun setupEdgeToEdgeInsets() {
        val mainContainer = findViewById<View>(R.id.native_audio_root)
        if (mainContainer != null) {
            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(mainContainer) { view, windowInsets ->
                view.setPadding(view.paddingLeft, 0, view.paddingRight, 0)
                windowInsets
            }
        }
    }

    /**
     * ✅ Recalcular dimensiones del slider
     */
    private fun recalculateLockDimensions() {
        if (!::lockTrack.isInitialized || !::lockSlider.isInitialized) return

        try {
            sliderStartX = lockTrack.x
            val trackWidth = lockTrack.width.toFloat()
            val sliderWidth = lockSlider.width.toFloat()
            sliderMaxX = (trackWidth - sliderWidth).coerceAtLeast(0f)

            Log.d(
                TAG,
                "🔒 Lock Dimensions - Track: ${trackWidth.toInt()}px, Slider: ${sliderWidth.toInt()}px, MaxX: ${sliderMaxX.toInt()}px"
            )
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error calculando dimensiones: ${e.message}")
        }
    }

    /**
     * ✅ Configurar barra deslizante de bloqueo
     */
    @SuppressLint("ClickableViewAccessibility")
    private fun setupLockSlider() {
        lockSlider.post {
            recalculateLockDimensions()
        }

        lockSlider.setOnTouchListener { view, event ->
            when (event.action) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    recalculateLockDimensions()
                    sliderStartX = view.x
                    true
                }
                android.view.MotionEvent.ACTION_MOVE -> {
                    val trackLocation = IntArray(2)
                    lockTrack.getLocationOnScreen(trackLocation)
                    val trackLeftOnScreen = trackLocation[0].toFloat()
                    val pointerRelToTrack = event.rawX - trackLeftOnScreen
                    val desiredX = lockTrack.x + pointerRelToTrack - view.width / 2f
                    val minX = lockTrack.x
                    val maxX = (lockTrack.x + sliderMaxX).coerceAtMost(lockTrack.x + lockTrack.width - view.width)
                    val newX = desiredX.coerceIn(minX, maxX)
                    view.x = newX
                    lockInstructionText.alpha = 0.8f
                    true
                }
                android.view.MotionEvent.ACTION_UP -> {
                    val finalX = view.x
                    val progress = if (sliderMaxX > 0) {
                        ((finalX - lockTrack.x) / sliderMaxX).coerceIn(0f, 1f)
                    } else {
                        0f
                    }

                    if (isScreenLocked) {
                        if (progress < 0.15f) {
                            unlockScreen()
                        } else {
                            val targetX = (lockTrack.x + sliderMaxX).coerceAtMost(lockTrack.x + lockTrack.width - view.width)
                            view.animate().cancel()
                            view.animate()
                                .x(targetX)
                                .setDuration(200)
                                .start()
                            lockSlider.setBackgroundColor(android.graphics.Color.BLACK)
                            lockInstructionText.alpha = 1f
                        }
                    } else {
                        if (progress > 0.85f) {
                            lockScreen()
                            lockSlider.postDelayed({
                                lockSlider.isEnabled = true
                            }, 300)
                        } else {
                            view.animate().cancel()
                            view.animate()
                                .x(lockTrack.x)
                                .setDuration(200)
                                .start()
                            lockSlider.setBackgroundColor(android.graphics.Color.parseColor("#FF4081"))
                            lockInstructionText.alpha = 1f
                        }
                    }
                    true
                }
                else -> false
            }
        }
    }

    private fun lockScreen() {
        isScreenLocked = true
        lockTrack.post {
            syncLockSliderState()
        }
        acquireLockWakeLock()
        Log.d(TAG, "🔐 Pantalla BLOQUEADA")
    }

    /**
     * ✅ Desbloquear pantalla
     */
    private fun unlockScreen() {
        isScreenLocked = false
        lockTrack.post {
            syncLockSliderState()
        }
        releaseLockWakeLock()
        Log.d(TAG, "🔓 Pantalla DESBLOQUEADA")
    }

    /**
     * ✅ Reconexión automática
     */
    private fun startAutoReconnect() {
        if (autoReconnectJob?.isActive == true) {
            Log.d(TAG, "⏱️ Reconexión ya en progreso")
            return
        }

        if (isConnected) {
            Log.d(TAG, "✅ Ya está conectado, cancelando reconexión automática")
            return
        }

        connectionAttempts = 0
        lastConnectionAttempt = System.currentTimeMillis()

        autoReconnectJob = lifecycleScope.launch {
            while (connectionAttempts < MAX_CONNECTION_ATTEMPTS && !isConnected && !isFinishing && !isDestroyed) {
                delay(CONNECTION_RETRY_DELAY_MS)

                if (isConnected) {
                    Log.d(TAG, "✅ Conexión establecida durante espera, cancelando intentos")
                    return@launch
                }

                connectionAttempts++
                Log.d(TAG, "🔄 Intento de reconexión #$connectionAttempts de $MAX_CONNECTION_ATTEMPTS")

                try {
                    val serverIp = ipEditText.text.toString().trim()
                    val serverPort = portEditText.text.toString().toIntOrNull() ?: 5101

                    if (serverIp.isNotEmpty()) {
                        val success = audioClient.connect(serverIp, serverPort)
                        if (success) {
                            Log.i(TAG, "✅ Reconexión automática exitosa")
                            connectionAttempts = 0
                            return@launch
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ Reconexión #$connectionAttempts falló: ${e.message}")
                }
            }

            if (connectionAttempts >= MAX_CONNECTION_ATTEMPTS && !isFinishing && !isDestroyed && !isConnected) {
                showToast("❌ No se pudo reconectar después de $MAX_CONNECTION_ATTEMPTS intentos")
                Log.e(TAG, "❌ Reconexión automática agotada")
            }
        }
    }

    /**
     * ✅ Reiniciar motor de audio sin destruir la Activity
     */
    private fun restartAudioEngine() {
        Log.d(TAG, "🔄 Reiniciando motor de audio...")
        lifecycleScope.launch(Dispatchers.Main) {
            try {
                audioRenderer.prepareNewEngine(bufferSizeFrames, if (isMuted) -60f else masterVolumeDb)
                audioRenderer.stop()
                audioRenderer.swapToPreparedEngine()
                Log.d(TAG, "✅ Motor de audio reiniciado sin interrupción perceptible")
                showToast("🔊 Audio reiniciado (dispositivo cambiado)")
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error reiniciando motor: ", e)
                showError("Error al reiniciar audio: ${e.message}")
            }
        }
    }

    // --- BroadcastReceiver para pantalla apagada ---
    private val screenOffReceiver = object : android.content.BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == android.content.Intent.ACTION_SCREEN_OFF) {
                Log.d(TAG, "🔐 Pantalla bloqueada - deteniendo transmisión")
                if (isConnected) {
                    disconnect()
                }
            }
        }
    }
}

