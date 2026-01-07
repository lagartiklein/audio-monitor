package com.cepalabsfree.fichatech.audiostream

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Process
import android.util.Log
import android.view.View
import android.widget.*
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.cepalabsfree.fichatech.R
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import kotlin.math.pow

class NativeAudioStreamActivity : AppCompatActivity() {

    companion object {

        private const val TAG = "AudioStreamRF"

        private const val PREFS_NAME = "AudioStreamPrefs"

        private const val KEY_LAST_IP = "last_ip"

        private const val KEY_LAST_PORT = "last_port"

        private const val KEY_MASTER_VOLUME = "master_volume"
    }

    private lateinit var audioClient: NativeAudioClient

    private lateinit var audioRenderer: OboeAudioRenderer

    private lateinit var audioManager: AudioManager

    // UI Components

    private lateinit var statusText: TextView

    private lateinit var ipEditText: EditText

    private lateinit var portEditText: EditText

    private lateinit var connectButton: Button

    private lateinit var masterVolumeSeekBar: SeekBar

    private lateinit var masterVolumeText: TextView

    private lateinit var muteButton: Button

    private lateinit var latencyText: TextView

    // private lateinit var rfStatusText: TextView

    // private lateinit var webControlText: TextView

    private lateinit var infoText: TextView

    private var isConnected = false

    private var isConnecting = false

    private var isMuted = false

    private var masterVolumeDb = 0f

    // Foreground Service

    private var audioService: AudioStreamForegroundService? = null

    private var serviceBound = false

    private val serviceConnection =
        object : android.content.ServiceConnection {

            override fun onServiceConnected(name: ComponentName, service: IBinder) {

                val binder = service as AudioStreamForegroundService.AudioStreamBinder

                audioService = binder.getService()

                serviceBound = true

                audioService?.onDisconnectRequested = { lifecycleScope.launch { disconnect() } }
            }

            override fun onServiceDisconnected(name: android.content.ComponentName?) {

                audioService = null

                serviceBound = false
            }
        }

    private val uiHandler = Handler(Looper.getMainLooper())

    private var metricsUpdateRunnable: Runnable? = null

    private val channelViews: MutableMap<Int, ChannelView> =
        mutableMapOf() // Asegúrate de poblar esto según tus canales

    private val monitorReceiver =
        object : BroadcastReceiver() {

            override fun onReceive(context: Context?, intent: Intent?) {

                if (intent?.action == AudioStreamForegroundService.ACTION_CHANNEL_MONITOR_UPDATE
                ) {

                    val jsonStr = intent.getStringExtra("channelStates") ?: return

                    val json = JSONObject(jsonStr)

                    for (key in json.keys()) {

                        val channel = key.toIntOrNull() ?: continue

                        val state = json.getJSONObject(key)

                        val rms = state.optDouble("rmsLevel", 0.0).toFloat()

                        val peak = state.optDouble("peakLevel", 0.0).toFloat()

                        val isActive = state.optBoolean("isActive", false)

                        channelViews[channel]?.updateMonitor(rms, peak, isActive)
                    }
                }
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {

        super.onCreate(savedInstanceState)

        // ✅ Modo inmersivo: dibujar detrás de la barra de estado y navegación
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        }

        // ✅ OPTIMIZACIÓN LATENCIA FASE 1: Prioridad urgente de audio
        // Reduce jitter y variabilidad en timing (~0.5-1ms)
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

        // Evita recreación de la actividad al rotar: mantiene la conexión y el audio
        requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT

        enableEdgeToEdge()

        setContentView(R.layout.activity_native_receiver)

        setupEdgeToEdgeInsets()

        configureAudioSystemForLowLatency()

        initializeViews()

        initializeAudioComponents()

        loadSessionPreferences()

        startMetricsUpdates()

        // Solicitar permiso de notificaciones (Android 13+)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {

            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) !=
                android.content.pm.PackageManager.PERMISSION_GRANTED
            ) {

                requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 100)
            }
        }

        Log.d(TAG, "✅ Activity creada - RECEPTOR PURO (Control desde Web) - FIXED")
    }

    // ✅ Evita recreación de la actividad al cambiar de orientación (mantiene conexión RF)

    private fun configureAudioSystemForLowLatency() {

        try {

            audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager

            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

            val sampleRateStr = audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)

            val framesPerBufferStr =
                audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)

            val optimalSampleRate = sampleRateStr?.toIntOrNull() ?: 48000

            val optimalBufferSize = framesPerBufferStr?.toIntOrNull() ?: 128

            Log.d(TAG, "🎵 Sistema de audio configurado:")

            Log.d(TAG, "   Sample Rate óptimo: $optimalSampleRate Hz")

            Log.d(TAG, "   Buffer óptimo: $optimalBufferSize frames")
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

        // rfStatusText = findViewById(R.id.rfStatusText)

        // webControlText = findViewById(R.id.webControlText)

        infoText = findViewById(R.id.infoText)

        connectButton.setOnClickListener {
            if (isConnected) {

                disconnect()
            } else {

                connectToServer()
            }
        }

        // Control de volumen master

        masterVolumeSeekBar.max = 72 // -60dB a +12dB

        masterVolumeSeekBar.progress = 60 // 0dB por defecto

        masterVolumeSeekBar.setOnSeekBarChangeListener(
            object : SeekBar.OnSeekBarChangeListener {

                override fun onProgressChanged(
                    seekBar: SeekBar?,
                    progress: Int,
                    fromUser: Boolean
                ) {

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

        // ✅ NUEVO: Listener para recrear streams (long press en latency)

        latencyText.setOnLongClickListener {
            if (isConnected) {

                audioRenderer.recreateAllStreams()

                showToast("🔄 Recreando streams de audio...")
            }

            true
        }

        statusText.text = "FICHATECH RETRO"

        connectButton.text = "Conectar"

        muteButton.text = "Audio ON"
    }

    private fun initializeAudioComponents() {

        audioClient =
            NativeAudioClient().apply {
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

                // ✅ NUEVO: Recibir actualizaciones de canal desde web
                onChannelUpdate = { channel, gainDb, pan, active ->
                    lifecycleScope.launch(Dispatchers.Main) {
                        if (!isFinishing && !isDestroyed) {
                            channelViews[channel]?.let { view ->
                                gainDb?.let {
                                    val gainLinear = dbToLinear(it)
                                    view.setGainLinear(gainLinear, fromServer = true)
                                    audioRenderer.updateChannelGain(channel, it)
                                }
                                pan?.let {
                                    view.setPan(it, fromServer = true)
                                    audioRenderer.updateChannelPan(channel, it)
                                }
                                active?.let {
                                    view.setActive(it, fromServer = true)
                                    audioRenderer.setChannelActive(channel, it)
                                }
                            }
                            Log.d(
                                TAG,
                                "✅ Canal $channel actualizado desde web: gain=${gainDb}dB pan=$pan"
                            )
                        }
                    }
                }

                // ✅ NUEVO: Recibir actualización de ganancia maestra desde web
                onMasterGainUpdate = { gainDb ->
                    lifecycleScope.launch(Dispatchers.Main) {
                        if (!isFinishing && !isDestroyed) {
                            masterVolumeDb = gainDb
                            audioRenderer.setMasterGain(gainDb)
                            masterVolumeSeekBar.progress = (gainDb + 60).toInt()
                            masterVolumeText.text = String.format("%.0f dB", gainDb)
                            Log.d(TAG, "✅ Master gain actualizado desde web: ${gainDb}dB")
                        }
                    }
                }

                // ✅ NUEVO: Recibir estado completo de mezcla desde web
                onMixStateUpdate = { mixState ->
                    lifecycleScope.launch(Dispatchers.Main) {
                        if (!isFinishing && !isDestroyed) {
                            val channels = mixState["channels"] as? List<Int> ?: emptyList()
                            val gains = mixState["gains"] as? Map<Int, Float> ?: emptyMap()
                            val pans = mixState["pans"] as? Map<Int, Float> ?: emptyMap()

                            // Aplicar todos los cambios
                            for (ch in 0 until 8) {
                                val isActive = channels.contains(ch)
                                channelViews[ch]?.setActive(isActive, fromServer = true)
                                audioRenderer.setChannelActive(ch, isActive)

                                if (isActive) {
                                    gains[ch]?.let { gainLinear ->
                                        val gainDb = linearToDb(gainLinear)
                                        channelViews[ch]?.setGainLinear(
                                            gainLinear,
                                            fromServer = true
                                        )
                                        audioRenderer.updateChannelGain(ch, gainDb)
                                    }
                                    pans[ch]?.let { pan ->
                                        channelViews[ch]?.setPan(pan, fromServer = true)
                                        audioRenderer.updateChannelPan(ch, pan)
                                    }
                                }
                            }

                            // Master gain si existe
                            (mixState["master_gain"] as? Float)?.let { gainLinear ->
                                val gainDb = linearToDb(gainLinear)
                                masterVolumeDb = gainDb
                                audioRenderer.setMasterGain(gainDb)
                                masterVolumeSeekBar.progress = (gainDb + 60).toInt()
                                masterVolumeText.text = String.format("%.0f dB", gainDb)
                            }

                            Log.d(
                                TAG,
                                "✅ Mix state completo actualizado desde web: ${channels.size} canales"
                            )
                        }
                    }
                }
            }

        // ✅ FIXED: Sin Context - Auto-recreación en fallos

        audioRenderer = OboeAudioRenderer().apply { setMasterGain(masterVolumeDb) }
    }

    private fun saveSessionPreferences() {

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        prefs.edit().apply {
            putString(KEY_LAST_IP, ipEditText.text.toString())

            putString(KEY_LAST_PORT, portEditText.text.toString())

            putFloat(KEY_MASTER_VOLUME, masterVolumeDb)

            apply()
        }

        Log.d(TAG, "💾 Sesión guardada")
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

        Log.d(TAG, "📂 Sesión cargada")
    }

    private fun toggleMute() {

        isMuted = !isMuted

        if (isMuted) {

            audioRenderer.setMasterGain(-60f)

            muteButton.text = "Audio OFF"

            muteButton.setBackgroundColor(getColor(android.R.color.holo_red_dark))
        } else {

            audioRenderer.setMasterGain(masterVolumeDb)

            muteButton.text = "Audio ON"

            muteButton.setBackgroundColor(getColor(android.R.color.holo_green_dark))
        }
    }

    private fun connectToServer() {

        if (isConnecting) {

            showToast("⚠️ Ya se está conectando")

            return
        }

        val serverIp = ipEditText.text.toString().trim()

        if (serverIp.isEmpty()) {

            showToast("⚠️ Ingresa una dirección IP")

            return
        }

        val serverPort = portEditText.text.toString().toIntOrNull() ?: 5101

        Log.d(TAG, "🔌 Conectando a $serverIp:$serverPort...")

        isConnecting = true

        connectButton.isEnabled = false

        connectButton.text = "Conectando..."

        statusText.text = "Buscando señal..."

        lifecycleScope.launch {
            try {

                val success = audioClient.connect(serverIp, serverPort)

                if (success) {

                    startForegroundService()

                    saveSessionPreferences()

                    delay(500L)

                    withContext(Dispatchers.Main) {
                        showToast("✅ RF Online - Control desde Web - FIXED")
                    }
                }
            } catch (e: Exception) {

                Log.e(TAG, "❌ Error conectando: ${e.message}", e)

                withContext(Dispatchers.Main) { showError("Error de conexión:\n${e.message}") }
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
            // Eliminado: webControlText.text = "🌐 Control desde WEB ✅"
            // Eliminado: webControlText.setTextColor(getColor(android.R.color.holo_green_light))

            // ✅ NUEVO: Mostrar versión del servidor

            val serverVersion = info["server_version"] as? String

            if (serverVersion != null) {

                infoText.text =
                            "• Conecta a la misma red WiFi que el servidor.\n" +
                            "• Mantén el punto de acceso cerca del escenario."

            }
        }
    }

    private fun handleAudioData(audioData: NativeAudioClient.FloatAudioData) {

        audioData.activeChannels.forEachIndexed { channelIndex, channelNumber ->
            val channelAudio = audioData.audioData[channelIndex]

            if (channelAudio.isNotEmpty()) {

                audioRenderer.renderChannelRF(channelNumber, channelAudio, audioData.samplePosition)
            }
        }
    }

    private fun updateConnectionStatus(connected: Boolean, message: String) {

        isConnected = connected

        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread

            if (connected) {

                statusText.text = "$message"

                statusText.setTextColor(getColor(android.R.color.holo_green_light))

                connectButton.text = "Desconectar"

                connectButton.setBackgroundColor(getColor(android.R.color.holo_green_dark))

                updateServiceNotification("Recibiendo", "FICHATECH RETRO")
            } else {

                statusText.text = message

                statusText.setTextColor(getColor(android.R.color.holo_orange_light))

                connectButton.text = "Conectar"

                connectButton.setBackgroundColor(getColor(android.R.color.holo_red_light))

                updateServiceNotification("📡 Buscando señal", message)
            }
        }
    }

    private fun disconnect() {

        audioClient.disconnect("Desconexión manual")

        stopForegroundService()

        runOnUiThread {
            statusText.text = "OFFLINE"

            connectButton.text = "Conectar"

            saveSessionPreferences()
        }
    }

    private fun startForegroundService() {

        try {

            val serviceIntent =
                Intent(this, AudioStreamForegroundService::class.java).apply {
                    action = AudioStreamForegroundService.ACTION_START
                }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {

                startForegroundService(serviceIntent)
            } else {

                startService(serviceIntent)
            }

            bindService(serviceIntent, serviceConnection, Context.BIND_AUTO_CREATE)
        } catch (e: Exception) {

            Log.e(TAG, "❌ Error iniciando foreground service: ${e.message}", e)
        }
    }

    private fun stopForegroundService() {

        try {

            if (serviceBound) {

                unbindService(serviceConnection)

                serviceBound = false
            }

            val serviceIntent = Intent(this, AudioStreamForegroundService::class.java)

            stopService(serviceIntent)
        } catch (e: Exception) {

            Log.e(TAG, "⚠️ Error deteniendo servicio: ${e.message}")
        }
    }

    private fun updateServiceNotification(status: String, details: String) {

        audioService?.updateNotification(status, details)
    }

    private fun startMetricsUpdates() {

        metricsUpdateRunnable =
            object : Runnable {

                override fun run() {

                    runOnUiThread {
                        if (isFinishing || isDestroyed) {

                            stopMetricsUpdates()

                            return@runOnUiThread
                        }

                        if (isConnected) {

                            val latency = audioRenderer.getLatencyMs()

                            latencyText.text = "${latency.toInt()} ms"

                            latencyText.setTextColor(
                                when {
                                    latency < 15 ->
                                        getColor(android.R.color.holo_green_light)
                                    latency < 30 ->
                                        getColor(android.R.color.holo_orange_light)
                                    else -> getColor(android.R.color.holo_red_light)
                                }
                            )

                            // rfStatusText.text = audioClient.getRFStatus()

                            // ✅ NUEVO: Detectar si hay streams con fallos

                            val stats = audioRenderer.getRFStats()

                            val totalFailures = stats["total_failures"] as? Int ?: 0

                            if (totalFailures > 5) {

                                statusText.text = "⚠️ Streams con errores (long press latencia)"

                                statusText.setTextColor(
                                    getColor(android.R.color.holo_orange_light)
                                )
                            }
                        } else {

                            latencyText.text = "-- ms"

                            // rfStatusText.text = audioClient.getRFStatus()
                        }
                    }

                    uiHandler.postDelayed(this, 100)
                }
            }

        uiHandler.post(metricsUpdateRunnable!!)
    }

    private fun stopMetricsUpdates() {

        metricsUpdateRunnable?.let {
            uiHandler.removeCallbacks(it)

            metricsUpdateRunnable = null
        }
    }

    private fun showError(message: String) {

        if (isFinishing || isDestroyed) return

        runOnUiThread { Toast.makeText(this, message, Toast.LENGTH_LONG).show() }
    }

    private fun showToast(message: String) {

        runOnUiThread {
            if (!isFinishing && !isDestroyed) {

                Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        registerReceiver(
            monitorReceiver,
            IntentFilter(AudioStreamForegroundService.ACTION_CHANNEL_MONITOR_UPDATE),
            Context.RECEIVER_NOT_EXPORTED
        )
    }

    override fun onPause() {

        super.onPause()

        // Para evitar el error de registro de broadcast en Android 13+ (API 33),
        // se debe usar el flag Context.RECEIVER_NOT_EXPORTED o Context.RECEIVER_EXPORTED
        // tanto al registrar como al desregistrar el receiver.
        unregisterReceiver(monitorReceiver)
    }

    override fun onDestroy() {

        super.onDestroy()

        stopMetricsUpdates()

        // No desconectar ni detener el servicio aquí, para que la transmisión siga al rotar

        audioRenderer.release()

        saveSessionPreferences()
    }

    private fun dbToLinear(db: Float): Float = 10.0f.pow(db / 20.0f)

    private fun linearToDb(linear: Float): Float =
        if (linear > 0) 20.0f * Math.log10(linear.toDouble()).toFloat() else -60f

    /**
     *
     * Configura Edge-to-Edge y padding para status bar/notch igual que MainActivity
     */
    private fun setupEdgeToEdgeInsets() {

        val mainContainer = findViewById<View>(R.id.native_audio_root)

        if (mainContainer != null) {

            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(mainContainer) { view, windowInsets ->
                // Para máxima compatibilidad con modo inmersivo, NO aplicar padding superior/inferior
                view.setPadding(
                    view.paddingLeft,
                    0,
                    view.paddingRight,
                    0
                )

                windowInsets
            }
        }
    }

    // ✅ UI: barras del sistema visibles para controles de volumen y notificaciones

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemUI()
    }

    private fun hideSystemUI() {
        val controller = androidx.core.view.WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }
}
