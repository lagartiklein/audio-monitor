package com.cepalabsfree.fichatech.audiostream

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceInfo
import android.media.AudioDeviceCallback
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
import java.util.UUID

class NativeAudioStreamActivity : AppCompatActivity() {

    companion object {
        private const val KEY_DEVICE_UUID = "device_uuid"
        private const val TAG = "AudioStreamRF"

        private const val PREFS_NAME = "AudioStreamPrefs"

        private const val KEY_LAST_IP = "last_ip"

        private const val KEY_LAST_PORT = "last_port"

        private const val KEY_MASTER_VOLUME = "master_volume"
    }

    private lateinit var audioClient: NativeAudioClient

    private lateinit var audioRenderer: OboeAudioRenderer

    private lateinit var audioManager: AudioManager
    private var headphonesConnected = false
    private var wasMutedByHeadphoneLoss = false

    // UI Components

    private lateinit var statusText: TextView

    private lateinit var ipEditText: EditText

    private lateinit var portEditText: EditText

    private lateinit var connectButton: Button

    private lateinit var masterVolumeSeekBar: SeekBar

    private lateinit var masterVolumeText: TextView

    private lateinit var muteButton: Button

    private lateinit var latencyText: TextView

    private lateinit var webControlText: TextView

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

    private val headphoneReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                AudioManager.ACTION_AUDIO_BECOMING_NOISY -> handleHeadsetConnection(false)
                Intent.ACTION_HEADSET_PLUG -> {
                    val state = intent.getIntExtra("state", -1)
                    if (state != -1) handleHeadsetConnection(state == 1)
                }
            }
        }
    }

    private val audioDeviceCallback = object : AudioDeviceCallback() {
        override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>?) {
            handleHeadsetConnection(isHeadphonesConnected())
        }
        override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>?) {
            handleHeadsetConnection(isHeadphonesConnected())
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {

        super.onCreate(savedInstanceState)

        // ✅ OPTIMIZACIÓN LATENCIA FASE 1: Prioridad urgente de audio
        // Reduce jitter y variabilidad en timing (~0.5-1ms)
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

        // Evita recreación de la actividad al rotar: mantiene la conexión y el audio

        requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED

        enableEdgeToEdge()

        setContentView(R.layout.activity_native_receiver)

        // Eliminar ocultamiento automático de la barra de estado
        // No llamar a hideSystemUI ni en onWindowFocusChanged
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

        Log.d(TAG, "✅ Activity creada - Fichatech Monitor")
    }

    // Evita recreación de la actividad al cambiar de orientación

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {

        super.onConfigurationChanged(newConfig)

        // Reaplica UI inmersiva y edge-to-edge

        setupEdgeToEdgeInsets()

        // No se reinicia ni se desconecta nada

    }

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

        webControlText = findViewById(R.id.webControlText)

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

        statusText.text = "FICHATECH MONITOR"

        connectButton.text = "Conectar"

        muteButton.text = "🔊 Audio ON"
    }

    private fun initializeAudioComponents() {
        // Usar instancia singleton para evitar bucle de reconexión
        audioClient = NativeAudioClient.getInstance(getDeviceUUID())
        audioClient.onAudioData = { audioData -> handleAudioData(audioData) }
        audioClient.onConnectionStatus = { connected, message -> updateConnectionStatus(connected, message) }
        audioClient.onServerInfo = { info -> handleServerInfo(info) }
        audioClient.onError = { error ->
            lifecycleScope.launch {
                if (!isFinishing && !isDestroyed) {
                    showError("Error: $error")
                }
            }
        }
        // Solo conectar si no está conectado
        if (!audioClient.isConnected()) {
            connectToServer()
        } else {
            // Si ya está conectado, solo actualiza la UI
            updateConnectionStatus(true, "ONLINE")
        }
        audioRenderer = OboeAudioRenderer().apply { setMasterGain(masterVolumeDb) }
        // Ahora sí, seguro llamar a handleHeadsetConnection
        handleHeadsetConnection(isHeadphonesConnected())
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

            muteButton.text = "🔇 Audio OFF"

            muteButton.setBackgroundColor(getColor(android.R.color.holo_red_dark))
        } else {

            audioRenderer.setMasterGain(masterVolumeDb)

            muteButton.text = "🔊 Audio ON"

            muteButton.setBackgroundColor(getColor(android.R.color.holo_green_dark))
        }
        if (!isMuted) {
            wasMutedByHeadphoneLoss = false
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

        connectButton.text = "🔄 Conectando..."

        statusText.text = "🔄 Buscando señal..."

        lifecycleScope.launch {
            try {

                val success = audioClient.connect(serverIp, serverPort)

                if (success) {

                    startForegroundService()

                    saveSessionPreferences()

                    delay(500L)


                }
            } catch (e: Exception) {

                Log.e(TAG, "❌ Error conectando: ${e.message}", e)

                withContext(Dispatchers.Main) { showError("Error de conexión:\n${e.message}") }
            } finally {

                withContext(Dispatchers.Main) {
                    isConnecting = false

                    connectButton.isEnabled = true

                    connectButton.text = if (isConnected) "🔴 Desconectar" else "⚫ Conectar"
                }
            }
        }
    }

    private fun handleServerInfo(info: Map<String, Any>) {

        runOnUiThread {
            val webControlled = info["web_controlled"] as? Boolean ?: false

            if (webControlled) {

                webControlText.text = "🌐 Control desde WEB ✅"

                webControlText.setTextColor(getColor(android.R.color.holo_green_light))
            }

            // ✅ NUEVO: Mostrar versión del servidor

            val serverVersion = info["server_version"] as? String

            if (serverVersion != null) {

                infoText.text =
                    "• Servidor: $serverVersion\n" +
                            "• Canales gestionados desde WEB\n" +
                            "• Auto-recreación de streams: HABILITADA\n" +
                            "• Mantén presionado la latencia para recrear streams"
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

    private fun handleHeadsetConnection(connected: Boolean) {
        if (!::audioManager.isInitialized) return
        if (connected == headphonesConnected) return
        headphonesConnected = connected
        audioManager.mode = AudioManager.MODE_NORMAL
        if (connected) {
            audioManager.isSpeakerphoneOn = false
            if (wasMutedByHeadphoneLoss && isMuted) {
                toggleMute()
                showToast("Auriculares conectados: audio reanudado automáticamente")
            }
            // Recrear streams de audio automáticamente al conectar audífonos
            audioRenderer.recreateAllStreams()
            showToast("Streams de audio recreados (auriculares conectados)")
        } else {
            audioManager.isSpeakerphoneOn = true
            if (isConnected && !isMuted) {
                wasMutedByHeadphoneLoss = true
                toggleMute()
                showToast("Auriculares desconectados: stream sigue pero audio OFF en altavoz")
            }
            // Recrear streams de audio automáticamente al volver a parlante
            audioRenderer.recreateAllStreams()
            showToast("Streams de audio recreados (parlante)")
        }
    }

    private fun updateConnectionStatus(connected: Boolean, message: String) {

        isConnected = connected

        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread

            if (connected) {

                statusText.text = "🔴 $message"

                statusText.setTextColor(getColor(android.R.color.holo_green_light))

                connectButton.text = "🔴 Desconectar"

                connectButton.setBackgroundColor(getColor(android.R.color.holo_green_dark))

                updateServiceNotification("🔴 Recibiendo", "Audio en vivo")
            } else {

                statusText.text = message

                statusText.setTextColor(getColor(android.R.color.holo_orange_light))

                connectButton.text = "⚫ Conectar"

                connectButton.setBackgroundColor(getColor(android.R.color.holo_red_light))

                updateServiceNotification("📡 Buscando señal", message)
            }
        }
    }

    private fun disconnect() {

        audioClient.disconnect("Desconexión manual")

        stopForegroundService()

        runOnUiThread {
            statusText.text = "⚫ OFFLINE"

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

                            // rfStatusText.text = audioClient.getRFStatus() // eliminado

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

                            // rfStatusText.text = audioClient.getRFStatus() // eliminado
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

    private fun getDeviceUUID(): String {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        var uuid = prefs.getString(KEY_DEVICE_UUID, null)
        if (uuid.isNullOrEmpty()) {
            uuid = UUID.randomUUID().toString()
            prefs.edit().putString(KEY_DEVICE_UUID, uuid).apply()
            Log.d(TAG, "📦 Nuevo device_uuid generado: ${uuid.take(8)}...")
        }
        return uuid
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

        if (android.os.Build.VERSION.SDK_INT >= 33) {

            registerReceiver(
                monitorReceiver,
                IntentFilter(AudioStreamForegroundService.ACTION_CHANNEL_MONITOR_UPDATE),
                Context.RECEIVER_NOT_EXPORTED
            )
        } else {

            registerReceiver(
                monitorReceiver,
                IntentFilter(AudioStreamForegroundService.ACTION_CHANNEL_MONITOR_UPDATE)
            )
        }
        val headphoneFilter = IntentFilter().apply {
            addAction(AudioManager.ACTION_AUDIO_BECOMING_NOISY)
            addAction(Intent.ACTION_HEADSET_PLUG)
        }
        registerReceiver(headphoneReceiver, headphoneFilter)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            audioManager.registerAudioDeviceCallback(audioDeviceCallback, uiHandler)
        }
    }

    override fun onPause() {

        super.onPause()

        unregisterReceiver(monitorReceiver)
        unregisterReceiver(headphoneReceiver)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            audioManager.unregisterAudioDeviceCallback(audioDeviceCallback)
        }
    }

    override fun onDestroy() {

        super.onDestroy()

        stopMetricsUpdates()

        // No desconectar ni detener el servicio aquí, para que la transmisión siga al rotar

        audioRenderer.release()

        saveSessionPreferences()
    }

    /**
     * Configura Edge-to-Edge y padding para status bar/notch igual que MainActivity
     */
    private fun setupEdgeToEdgeInsets() {
        val mainContainer = findViewById<View>(R.id.native_audio_root)
        if (mainContainer != null) {
            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(mainContainer) { view, windowInsets ->
                val sysBarInsets = windowInsets.getInsets(
                    androidx.core.view.WindowInsetsCompat.Type.systemBars() or
                    androidx.core.view.WindowInsetsCompat.Type.displayCutout()
                )
                // Padding inferior igual a la barra de navegación
                view.setPadding(
                    view.paddingLeft,
                    sysBarInsets.top,
                    view.paddingRight,
                    sysBarInsets.bottom
                )
                windowInsets
            }
        }
    }

    private fun isHeadphonesConnected(): Boolean {
        if (!::audioManager.isInitialized) return false
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val headphoneTypes = setOf(
                AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
                AudioDeviceInfo.TYPE_WIRED_HEADSET,
                AudioDeviceInfo.TYPE_USB_HEADSET,
                AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
                AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
                AudioDeviceInfo.TYPE_USB_DEVICE,
                AudioDeviceInfo.TYPE_USB_ACCESSORY
            )
            audioManager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                .any { it.type in headphoneTypes }
        } else {
            audioManager.isWiredHeadsetOn || audioManager.isBluetoothA2dpOn
        }
    }
}
