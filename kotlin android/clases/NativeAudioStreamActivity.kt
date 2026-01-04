package com.cepalabsfree.fichatech.audiostream

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
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
import androidx.core.view.WindowCompat
import androidx.lifecycle.lifecycleScope
import com.cepalabsfree.fichatech.R
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

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
    private var statusText: TextView? = null
    private var ipEditText: EditText? = null
    private var portEditText: EditText? = null
    private var connectButton: Button? = null
    private var masterVolumeSeekBar: SeekBar? = null
    private var masterVolumeText: TextView? = null
    private var muteButton: Button? = null
    private var latencyText: TextView? = null
    private var webControlText: TextView? = null
    private var infoText: TextView? = null

    private var channelStripContainer: LinearLayout? = null

    private var isConnected = false

    private var isConnecting = false
    private var isMuted = false

    private var masterVolumeDb = 0f
    private var volumeBeforeMute = 0f // ✅ NUEVO: Guardar volumen previo al mute

    // Foreground Service

    private var audioService: AudioStreamForegroundService? = null

    private var serviceBound = false

    private val serviceConnection =
        object : android.content.ServiceConnection {

            override fun onServiceConnected(name: ComponentName, service: IBinder) {

                val binder = service as AudioStreamForegroundService.AudioStreamBinder

                audioService = binder.getService()
                serviceBound = true
            }

            override fun onServiceDisconnected(name: android.content.ComponentName?) {

                audioService = null

                serviceBound = false
            }
        }

    // ✅ MODERNO: Job de corrutina para métricas (reemplaza Handler+Runnable)
    private var metricsJob: kotlinx.coroutines.Job? = null

    private val channelViews: MutableMap<Int, ChannelView> =
        mutableMapOf() // Asegúrate de poblar esto según tus canales

    private val activeChannelsLocal: MutableSet<Int> = mutableSetOf()

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

    private val headphoneReceiver =
        object : BroadcastReceiver() {
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

    private val audioDeviceCallback =
        object : AudioDeviceCallback() {
            override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>?) {
                handleHeadsetConnection(isHeadphonesConnected())
            }
            override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>?) {
                handleHeadsetConnection(isHeadphonesConnected())
            }
        }

    private var lastKnownMaxChannels = 8

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
        hideSystemBars()

        configureAudioSystemForLowLatency()

        initializeViews()

        // Inicializar vistas según la orientación inicial: si la Activity se lanza ya en LANDSCAPE
        // debemos preparar la consola de canales en lugar de los controles de portrait.
        val isLandscapeInitial =
            resources.configuration.orientation ==
                    android.content.res.Configuration.ORIENTATION_LANDSCAPE

        if (isLandscapeInitial) {
            initializeViewsLandscape()
            // Asegurar que la consola tenga vistas aunque no haya llegado info del servidor
            ensureChannelConsole(lastKnownMaxChannels)
            // Ocultar UI (modo inmersivo) para landscape inicial
            hideSystemUI()
        } else {
            initializeViews()
        }

        // ✅ CRÍTICO: Cargar preferencias ANTES de inicializar componentes de audio
        loadSessionPreferences()

        initializeAudioComponents()

        setupVolumeSeekBarListener() // Configurar listener DESPUÉS de cargar preferencias

        startMetricsUpdates()

        // Solicitar permiso de notificaciones (Android 13+)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {

            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) !=
                android.content.pm.PackageManager.PERMISSION_GRANTED
            ) {

                requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 100)
            }
        }

        // ✅ Configurar el manejador de botón atrás moderno (OnBackPressedDispatcher)
        onBackPressedDispatcher.addCallback(
            this,
            object : androidx.activity.OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (isConnected && serviceBound) {
                        Log.d(
                            TAG,
                            "📱 Usuario presionó atrás - Minimizando con transmisión activa"
                        )
                        showToast(
                            "Transmisión activa en background. Toca la notificación para volver."
                        )
                        finish()
                    } else {
                        Log.d(TAG, "📱 Usuario presionó atrás - Sin conexión activa")
                        finish()
                    }
                }
            }
        )

        Log.d(TAG, "✅ Activity creada - Fichatech Monitor")
    }

    // Evita recreación de la actividad al cambiar de orientación
    private fun hideSystemBars() {
        // Ocultar las barras del sistema (status bar y navigation bar)
        val windowInsetsController =
            androidx.core.view.WindowCompat.getInsetsController(window, window.decorView)
        windowInsetsController?.let {
            // Ocultar barras de estado y navegación
            it.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            // Comportamiento: las barras reaparecen cuando el usuario interactúa
            it.systemBarsBehavior =
                androidx.core.view.WindowInsetsControllerCompat
                    .BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }
    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {

        super.onConfigurationChanged(newConfig)

        val isLandscape =
            newConfig.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE

        Log.d(TAG, "🔁 onConfigurationChanged - isLandscape=$isLandscape")

        // Reemplazamos el layout para forzar que Android use la variante correcta
        // (si existe `layout-land/activity_native_receiver.xml`, se cargará automáticamente)
        setContentView(R.layout.activity_native_receiver)

        // Reaplica Edge-to-Edge y vuelve a ligar las vistas del nuevo layout
        setupEdgeToEdgeInsets()

        if (isLandscape) {
            // 🌄 LANDSCAPE: Solo mostrar consola de canales
            Log.d(TAG, "📱 Rotación a LANDSCAPE - Inicializando consola de canales")
            initializeViewsLandscape()
            try {
                ensureChannelConsole(lastKnownMaxChannels)

                // ✅ CORREGIDO: Aplicar estado en memoria del cliente ANTES de renderizar
                if (isConnected) {
                    val channels = audioClient.getPersistentChannels()
                    val gains = audioClient.getPersistentGains()
                    val pans = audioClient.getPersistentPans()

                    Log.d(TAG, "📡 Aplicando estado en memoria: ${channels.size} canales")

                    // Construir MixState desde el estado en memoria
                    if (channels.isNotEmpty() || gains.isNotEmpty()) {
                        val mixState =
                            NativeAudioClient.MixState(
                                channels = channels,
                                gains = gains,
                                pans = pans,
                                mutes = audioClient.getPersistentMutes(),
                                preListen = null,
                                solos = emptyList(),
                                masterGain = null
                            )
                        applyMixState(mixState)
                    }

                    // También solicitar del servidor como fallback por si hay cambios recientes
                    Log.d(TAG, "📡 Solicitando estado actualizado del servidor...")
                    audioClient.requestClientState()
                }
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Error poblando consola en landscape: ${e.message}")
            }
        } else {
            // 📱 PORTRAIT: Mostrar controles de conexión y volumen
            Log.d(TAG, "📱 Rotación a PORTRAIT - Inicializando controles")
            initializeViews()

            // ✅ CORREGIDO: Restaurar IP y puerto cuando vuelve a portrait
            loadSessionPreferences()

            // ✅ FIX: Sincronizar UI con volumen actual
            masterVolumeSeekBar?.setProgress((masterVolumeDb + 60).toInt(), false)
            masterVolumeText?.text = String.format("%.0f dB", masterVolumeDb)
            // Reconfigurar listener del seekbar
            setupVolumeSeekBarListener()
        }

        if (newConfig.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE) {
            hideSystemUI()
        }
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

        channelStripContainer = findViewById(R.id.channelStripContainer)

        connectButton?.setOnClickListener {
            if (isConnected) {

                disconnect()
            } else {

                connectToServer()
            }
        }

        // Control de volumen master
        masterVolumeSeekBar?.max = 72 // -60dB a +12dB

        // NO establecer progress aquí, se hará en loadSessionPreferences() después de cargar el
        // valor guardado

        muteButton?.setOnClickListener { toggleMute() }

        statusText?.text = "FICHATECH MONITOR"

        connectButton?.text = "Conectar"

        muteButton?.text = "🔊 Audio ON"

        // ✅ Actualizar estado de conexión después de inicializar vistas
        statusText?.text = if (isConnected) "Recibiendo" else "FICHATECH MONITOR"

        statusText?.setTextColor(
            if (isConnected) getColor(android.R.color.holo_green_light)
            else getColor(android.R.color.holo_orange_light)
        )

        connectButton?.text = if (isConnected) "Desconectar" else "Conectar"

        connectButton?.setBackgroundColor(
            if (isConnected) getColor(android.R.color.holo_green_dark)
            else getColor(android.R.color.holo_red_light)
        )

        muteButton?.text = "🔊 Audio ON"

        // ✅ Actualizar estado de conexión después de inicializar vistas
        updateConnectionStatus(isConnected, if (isConnected) "Recibiendo" else "OFFLINE")
    }

    // Configurar el listener del SeekBar DESPUÉS de cargar preferencias
    private fun setupVolumeSeekBarListener() {
        masterVolumeSeekBar?.setOnSeekBarChangeListener(
            object : SeekBar.OnSeekBarChangeListener {

                override fun onProgressChanged(
                    seekBar: SeekBar?,
                    progress: Int,
                    fromUser: Boolean
                ) {
                    if (fromUser) { // Solo procesar cambios del usuario, no de código
                        masterVolumeDb = (progress - 60).toFloat()
                        masterVolumeText?.text = String.format("%.0f dB", masterVolumeDb)
                        audioRenderer.setMasterGain(if (isMuted) -60f else masterVolumeDb)
                    }
                }

                override fun onStartTrackingTouch(seekBar: SeekBar?) {}

                override fun onStopTrackingTouch(seekBar: SeekBar?) {
                    saveSessionPreferences()
                }
            }
        )
    }

    // Landscape mode: solo mostrar el contenedor de canales
    private fun initializeViewsLandscape() {
        channelStripContainer = findViewById(R.id.channelStripContainer)
        Log.d(TAG, "🌄 Landscape: channelStripContainer inicializado")

        // Limpiar las vistas existentes para reconstruirlas en el nuevo contenedor
        if (channelViews.isNotEmpty()) {
            channelStripContainer?.removeAllViews()
            channelViews.clear()
            Log.d(TAG, "🔄 Vistas de canales limpias, listas para recrearse")
        }

        // Asegurar que el contenedor esté visible y que los controles de portrait (si existen)
        // no queden sobrepuestos. Esto soluciona el caso donde la Activity se abre desde
        // otra en landscape y la consola se queda oculta.
        try {
            channelStripContainer?.visibility = View.VISIBLE
            // Ocultar controles de portrait si fueron inflados
            statusText?.visibility = View.GONE
            ipEditText?.visibility = View.GONE
            portEditText?.visibility = View.GONE
            connectButton?.visibility = View.GONE
            masterVolumeSeekBar?.visibility = View.GONE
            masterVolumeText?.visibility = View.GONE
            muteButton?.visibility = View.GONE
            latencyText?.visibility = View.GONE
            webControlText?.visibility = View.GONE
            infoText?.visibility = View.GONE
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ Error ajustando visibilidad en landscape: ${e.message}")
        }
    }

    private fun initializeAudioComponents() {
        // Usar instancia singleton con UUID del dispositivo
        audioClient = NativeAudioClient.getInstance(getDeviceUUID())

        // Configurar callbacks
        audioClient.onAudioData = { audioData -> handleAudioData(audioData) }
        audioClient.onConnectionStatus = { connected, message ->
            updateConnectionStatus(connected, message)
        }
        audioClient.onServerInfo = { info -> handleServerInfo(info) }
        audioClient.onMixState = { mixState -> applyMixState(mixState) }
        audioClient.onError = { error ->
            lifecycleScope.launch {
                if (!isFinishing && !isDestroyed) {
                    showError("Error: $error")
                }
            }
        }

        // ✅ NUEVO: Callback para sincronización de controles desde servidor/web
        audioClient.onControlSync = { update -> handleControlSync(update) }

        // ✅ NUEVO: Callback de reconexión exitosa - reiniciar renderer y servicio
        audioClient.onReconnected = {
            lifecycleScope.launch {
                if (!isFinishing && !isDestroyed) {
                    Log.d(TAG, "🔌 Reconexión detectada - Reiniciando renderer y servicio")
                    try {
                        // Reiniciar renderer con streams Oboe
                        audioRenderer.start()
                        Log.d(TAG, "✅ OboeAudioRenderer reiniciado después de reconexión")

                        // Reiniciar servicio foreground
                        startForegroundService()
                        Log.d(TAG, "✅ ForegroundService reiniciado después de reconexión")
                    } catch (e: Exception) {
                        Log.e(TAG, "❌ Error reiniciando componentes: ${e.message}", e)
                    }
                }
            }
        }

        // Solo conectar si no está conectado
        if (!audioClient.isConnected()) {
            connectToServer()
        } else {
            updateConnectionStatus(true, "ONLINE")
        }

        // Crear renderer con el volumen cargado desde preferencias
        audioRenderer =
            OboeAudioRenderer.getInstance(this).apply {
                setMasterGain(masterVolumeDb)
                Log.d(TAG, "🔊 AudioRenderer inicializado con ganancia: $masterVolumeDb dB")
            }

        // Verificar estado de auriculares
        handleHeadsetConnection(isHeadphonesConnected())
    }

    /**
     * ✅ NUEVO: Manejar sincronización de controles desde servidor/web Actualiza UI sin disparar
     * callbacks al servidor (evita loops)
     */
    private fun handleControlSync(update: NativeAudioClient.ControlUpdate) {
        runOnUiThread {
            val channel = update.channel
            if (channel < 0) return@runOnUiThread

            val view = channelViews[channel] ?: return@runOnUiThread

            // Actualizar desde servidor (fromServer=true evita loops)
            update.active?.let { active ->
                view.activateChannel(active, fromServer = true)
                audioRenderer.setChannelActive(channel, active)
                if (active) activeChannelsLocal.add(channel)
                else activeChannelsLocal.remove(channel)
            }

            update.gain?.let { gain ->
                val gainDb =
                    (20f * kotlin.math.log10(gain.coerceAtLeast(0.0001f))).coerceIn(-60f, 12f)
                view.setGainDb(gainDb, fromServer = true)
                audioRenderer.updateChannelGain(channel, gainDb)
            }

            update.pan?.let { pan ->
                view.setPanValue(pan, fromServer = true)
                audioRenderer.updateChannelPan(channel, pan)
            }

            Log.d(TAG, "🔄 Control sync: ch=$channel, source=${update.source}")
        }
    }

    private fun applyMixState(mixState: NativeAudioClient.MixState) {
        try {
            val activeSet = mixState.channels.toSet()

            Log.d(TAG, "🔍 applyMixState recibido:")
            Log.d(TAG, "   Canales: ${mixState.channels}")
            Log.d(TAG, "   Gains: ${mixState.gains}")
            Log.d(TAG, "   Pans: ${mixState.pans}")
            Log.d(TAG, "   Mutes: ${mixState.mutes}")
            Log.d(TAG, "   ChannelViews existentes: ${channelViews.size}")

            // Actualizar copia local
            activeChannelsLocal.clear()
            activeChannelsLocal.addAll(activeSet)

            // Aplicar a renderer
            for (ch in 0 until 32) {
                audioRenderer.setChannelActive(ch, activeSet.contains(ch))
            }

            // Ganancia: viene como lineal (1.0 = 0dB)
            mixState.gains.forEach { (ch, linear) ->
                val safe = if (linear <= 0f) 0.0001f else linear
                val gainDb = (20f * kotlin.math.log10(safe)).coerceIn(-60f, 12f)
                audioRenderer.updateChannelGain(ch, gainDb)
            }

            // Pan: [-1..1]
            mixState.pans.forEach { (ch, pan) ->
                audioRenderer.updateChannelPan(ch, pan.coerceIn(-1f, 1f))
            }

            // Mute
            mixState.mutes.forEach { (ch, muted) ->
                if (muted) {
                    audioRenderer.updateChannelGain(ch, -60f)
                }
            }

            // ✅ UI: reflejar estado en la consola (fromServer=true evita loops)
            runOnUiThread {
                channelViews.forEach { (ch, view) ->
                    val isOn = activeSet.contains(ch)
                    view.activateChannel(isOn, fromServer = true)

                    val linear = mixState.gains[ch]
                    if (linear != null) {
                        val safe = if (linear <= 0f) 0.0001f else linear
                        val gainDb = (20f * kotlin.math.log10(safe)).coerceIn(-60f, 12f)
                        view.setGainDb(gainDb, fromServer = true)
                        Log.d(TAG, "   Aplicado Ch$ch: gain=$gainDb dB")
                    }

                    val pan = mixState.pans[ch]
                    if (pan != null) {
                        view.setPanValue(pan.coerceIn(-1f, 1f), fromServer = true)
                        Log.d(TAG, "   Aplicado Ch$ch: pan=${pan.coerceIn(-1f, 1f)}")
                    }
                }
            }

            Log.d(TAG, "✅ MixState aplicado: ${activeSet.size} canales activos")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error aplicando mix_state: ${e.message}", e)
        }
    }

    private fun saveSessionPreferences() {

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        prefs.edit().apply {
            putString(KEY_LAST_IP, ipEditText?.text.toString())

            putString(KEY_LAST_PORT, portEditText?.text.toString())

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

            ipEditText?.setText(lastIp)
        }

        if (!lastPort.isNullOrEmpty()) {

            portEditText?.setText(lastPort)
        }

        // Establecer masterVolumeDb primero (sin listener configurado aún)
        masterVolumeDb = savedVolume

        // Actualizar SeekBar sin disparar el listener (se configura después en
        // setupVolumeSeekBarListener)
        masterVolumeSeekBar?.setProgress(
            (savedVolume + 60).toInt(),
            false
        ) // false = no dispara listener

        // Actualizar el texto de volumen
        masterVolumeText?.text = String.format("%.0f dB", savedVolume)

        Log.d(TAG, "📂 Sesión cargada - Volumen: $savedVolume dB")
    }

    private fun toggleMute() {

        isMuted = !isMuted

        if (isMuted) {
            // ✅ NUEVO: Guardar volumen actual antes de mutear
            volumeBeforeMute = masterVolumeDb
            audioRenderer.setMasterGain(-60f)

            muteButton?.text = "🔇 Audio OFF"

            muteButton?.setBackgroundColor(getColor(android.R.color.holo_red_dark))
        } else {
            // ✅ NUEVO: Restaurar volumen guardado antes de mutear (NO usar masterVolumeDb actual)
            audioRenderer.setMasterGain(volumeBeforeMute)
            // ✅ IMPORTANTE: Actualizar masterVolumeDb al valor restaurado
            masterVolumeDb = volumeBeforeMute
            // ✅ Sincronizar seekbar sin disparar listener
            masterVolumeSeekBar?.setProgress((volumeBeforeMute + 60).toInt(), false)

            muteButton?.text = "🔊 Audio ON"

            muteButton?.setBackgroundColor(getColor(android.R.color.holo_green_dark))
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

        val serverIp = ipEditText?.text.toString().trim()

        if (serverIp.isEmpty()) {

            showToast("⚠️ Ingresa una dirección IP")

            return
        }

        val serverPort = portEditText?.text.toString().toIntOrNull() ?: 5101

        Log.d(TAG, "🔌 Conectando a $serverIp:$serverPort...")

        isConnecting = true

        connectButton?.isEnabled = false

        connectButton?.text = "🔄 Conectando..."

        updateStatusText(true)

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

                    connectButton?.isEnabled = true

                    connectButton?.text = if (isConnected) "Desconectar" else "Conectar"
                }
            }
        }
    }

    private fun handleServerInfo(info: Map<String, Any>) {

        runOnUiThread {
            val webControlled = info["web_controlled"] as? Boolean ?: false

            if (webControlled) {

                webControlText?.text = "🌐 Control desde WEB ✅"

                webControlText?.setTextColor(getColor(android.R.color.holo_green_light))
            }

            // ✅ Mostrar versión del servidor (sin referencias a recreación de streams)
            val serverVersion = info["server_version"] as? String

            if (serverVersion != null) {
                infoText?.text =
                    "•Verifica radio optimo de trabajo.\n" +
                            "•Los Canales son gestionados desde WEB.\n" +
                            "•Motor Oboe Transmitiendo en modo Ultra baja latencia."
            }

            val maxChannels =
                when (val v = info["max_channels"]) {
                    is Number -> v.toInt()
                    is String -> v.toIntOrNull()
                    else -> null
                }
                    ?: 8

            // Guardar el último valor conocido para poder poblar la consola al rotar
            lastKnownMaxChannels = maxChannels

            ensureChannelConsole(maxChannels)
        }
    }

    private fun ensureChannelConsole(maxChannels: Int) {
        if (channelStripContainer == null) return

        val count = maxChannels.coerceIn(1, Int.MAX_VALUE)

        if (channelViews.size == count) {
            return
        }

        channelStripContainer?.removeAllViews()
        channelViews.clear()

        val density = resources.displayMetrics.density
        val widthPx = (density * 110f).toInt()
        val gapPx = (density * 10f).toInt()

        for (ch in 0 until count) {
            val view = ChannelView(this)
            view.setChannelNumber(ch + 1)
            view.activateChannel(false)
            view.setGainDb(0f)
            view.setPanValue(0f)

            // Debounce por canal para ON/gain/pan
            var pendingGain: Float? = null
            var pendingPan: Float? = null
            var pendingActive: Boolean? = null
            val debounceHandler = Handler(Looper.getMainLooper())
            var debounceRunnable: Runnable? = null
            fun scheduleDebounceUpdate() {
                debounceRunnable?.let { debounceHandler.removeCallbacks(it) }
                debounceRunnable = Runnable {
                    val gain = pendingGain
                    val pan = pendingPan
                    val active = pendingActive
                    val channel = ch
                    // Solo enviar si hay algo pendiente
                    if (gain != null) {
                        audioClient.sendMixUpdate(gains = mapOf(channel to dbToLinear(gain)))
                        pendingGain = null
                    }
                    if (pan != null) {
                        audioClient.sendMixUpdate(pans = mapOf(channel to pan))
                        pendingPan = null
                    }
                    if (active != null) {
                        val channels =
                            if (active) activeChannelsLocal.plus(channel)
                            else activeChannelsLocal.minus(channel)
                        audioClient.sendMixUpdate(channels = channels.toList().sorted())
                        pendingActive = null
                    }
                }
                debounceHandler.postDelayed(debounceRunnable!!, 75)
            }

            view.onActiveChanged = { channel, active ->
                if (active) {
                    activeChannelsLocal.add(channel)
                } else {
                    activeChannelsLocal.remove(channel)
                }

                audioRenderer.setChannelActive(channel, active)
                pendingActive = active
                scheduleDebounceUpdate()
            }

            view.onGainDbChanged = { channel, gainDb ->
                audioRenderer.updateChannelGain(channel, gainDb)
                pendingGain = gainDb
                scheduleDebounceUpdate()
            }

            view.onPanChanged = { channel, pan ->
                audioRenderer.updateChannelPan(channel, pan)
                pendingPan = pan
                scheduleDebounceUpdate()
            }

            val lp = LinearLayout.LayoutParams(widthPx, LinearLayout.LayoutParams.MATCH_PARENT)
            lp.marginEnd = gapPx
            view.layoutParams = lp

            channelStripContainer?.addView(view)
            channelViews[ch] = view
        }
    }

    private fun dbToLinear(db: Float): Float {
        return Math.pow(10.0, (db / 20.0).toDouble()).toFloat()
    }

    /**
     * ✅ CORREGIDO: Usar renderMixedChannels para mezclar TODOS los canales en UN SOLO STREAM Oboe,
     * evitando race conditions y crashes.
     *
     * ANTES: Llamaba a renderChannelRF para cada canal → múltiples streams → crash AHORA: Acumula
     * todos los canales en un mapa y los mezcla en una sola llamada
     */
    private fun handleAudioData(audioData: NativeAudioClient.FloatAudioData) {
        if (audioData.activeChannels.isEmpty() || audioData.audioData.isEmpty()) {
            return
        }

        // Construir mapa de canal → datos de audio
        val channelDataMap = mutableMapOf<Int, FloatArray>()

        audioData.activeChannels.forEachIndexed { index, channelNumber ->
            if (index < audioData.audioData.size) {
                val channelAudio = audioData.audioData[index]
                if (channelAudio.isNotEmpty()) {
                    channelDataMap[channelNumber] = channelAudio
                }
            }
        }

        // Renderizar TODOS los canales mezclados en UN SOLO stream
        if (channelDataMap.isNotEmpty()) {
            audioRenderer.renderMixedChannels(channelDataMap, audioData.samplePosition)
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
            showToast("Audio optimizado para auriculares")
        } else {
            audioManager.isSpeakerphoneOn = true
            if (isConnected && !isMuted) {
                wasMutedByHeadphoneLoss = true
                toggleMute()
                showToast("Auriculares desconectados: stream sigue pero audio OFF en altavoz")
            }
            showToast("Audio optimizado para parlante")
        }
    }

    private fun updateConnectionStatus(connected: Boolean, message: String) {

        isConnected = connected

        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread

            if (connected) {

                statusText?.text = "$message"

                statusText?.setTextColor(getColor(android.R.color.holo_green_light))

                connectButton?.text = "Desconectar"

                connectButton?.setBackgroundColor(getColor(android.R.color.holo_green_dark))

                updateServiceNotification("📡 Fichatech Server", "Monitor de audio: transmitiendo")
            } else {

                statusText?.text = "FICHATECH MONITOR"

                statusText?.setTextColor(getColor(android.R.color.holo_orange_light))

                connectButton?.text = "Conectar"

                connectButton?.setBackgroundColor(getColor(android.R.color.holo_red_light))

                updateServiceNotification("Buscando señal", message)
            }
        }
    }

    private fun disconnect() {

        audioClient.disconnect("Desconexión manual")

        // ✅ CRÍTICO: Detener todos los streams Oboe antes de cerrar servicio
        try {
            audioRenderer.stop()
            Log.d(TAG, "✅ Streams Oboe detenidos en disconnect()")
        } catch (e: Exception) {
            Log.e(TAG, "⚠️ Error deteniendo streams: ${e.message}")
        }

        stopForegroundService()

        runOnUiThread {
            updateStatusText(false)

            connectButton?.text = "Conectar"

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

    /**
     * ✅ MODERNO Y SEGURO: Actualización de métricas usando lifecycleScope
     * - Respeta automáticamente el ciclo de vida de la Activity
     * - Se cancela automáticamente en onDestroy()
     * - Thread-safe y sin race conditions
     * - Validaciones robustas contra accesos a memoria nativa inválida
     */
    private fun startMetricsUpdates() {
        // Cancelar job anterior si existe
        metricsJob?.cancel()

        metricsJob = lifecycleScope.launch {
            while (isActive) {
                try {
                    // ✅ PROTECCIÓN: Validar estado antes de acceder a componentes nativos
                    if (isFinishing || isDestroyed || !::audioRenderer.isInitialized) {
                        break
                    }

                    if (isConnected) {
                        // ✅ SAFE: Acceso protegido a JNI/nativo
                        val latency = try {
                            audioRenderer.getLatencyMs()
                        } catch (e: Exception) {
                            Log.e(TAG, "⚠️ Error obteniendo latencia: ${e.message}")
                            0f
                        }

                        // ✅ SAFE: Actualizar UI solo si las vistas existen
                        withContext(Dispatchers.Main) {
                            if (!isFinishing && !isDestroyed) {
                                latencyText?.text = "${latency.toInt()} ms"

                                latencyText?.setTextColor(
                                    when {
                                        latency < 15 ->
                                            getColor(android.R.color.holo_green_light)
                                        latency < 30 ->
                                            getColor(android.R.color.holo_orange_light)
                                        else -> getColor(android.R.color.holo_red_light)
                                    }
                                )

                                // ✅ Detectar streams con fallos (solo informativo)
                                try {
                                    val stats = audioRenderer.getRFStats()
                                    val totalFailures = stats["total_failures"] as? Int ?: 0

                                    if (totalFailures > 5) {
                                        statusText?.text = "⚠️ Audio inestable"
                                        statusText?.setTextColor(
                                            getColor(android.R.color.holo_orange_light)
                                        )
                                    }
                                } catch (e: Exception) {
                                    Log.w(TAG, "⚠️ Error obteniendo stats: ${e.message}")
                                }
                            }
                        }
                    } else {
                        withContext(Dispatchers.Main) {
                            if (!isFinishing && !isDestroyed) {
                                latencyText?.text = "-- ms"
                            }
                        }
                    }

                    // ✅ Delay de 100ms para ultra baja latencia en UI
                    delay(100)
                } catch (e: Exception) {
                    Log.e(TAG, "❌ Error en loop de métricas: ${e.message}", e)
                    break
                }
            }
        }

        Log.d(TAG, "✅ Métricas iniciadas con lifecycleScope (auto-cancelable)")
    }

    /**
     * ✅ MODERNO: Detener métricas cancelando el job de corrutina
     */
    private fun stopMetricsUpdates() {
        metricsJob?.cancel()
        metricsJob = null
        Log.d(TAG, "✅ Métricas detenidas")
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

    private fun updateStatusText(isSearching: Boolean) {
        if (isSearching) {
            statusText?.text = "🔄 Buscando señal RF..."
        } else {
            statusText?.text = "FICHATECH MONITOR"
        }
    }

    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    override fun onResume() {

        super.onResume()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
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
        val headphoneFilter =
            IntentFilter().apply {
                addAction(AudioManager.ACTION_AUDIO_BECOMING_NOISY)
                addAction(Intent.ACTION_HEADSET_PLUG)
            }
        registerReceiver(headphoneReceiver, headphoneFilter)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            audioManager.registerAudioDeviceCallback(audioDeviceCallback, null)
        }

        if (resources.configuration.orientation ==
            android.content.res.Configuration.ORIENTATION_LANDSCAPE
        ) {
            hideSystemUI()
        }
    }

    override fun onPause() {

        super.onPause()

        unregisterReceiver(monitorReceiver)
        unregisterReceiver(headphoneReceiver)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            audioManager.unregisterAudioDeviceCallback(audioDeviceCallback)
        }

        // ✅ NUEVO: Guardar volumen y preferencias al salir de la app
        saveSessionPreferences()
    }

    override fun onDestroy() {

        super.onDestroy()

        stopMetricsUpdates()

        // NO liberar renderer ni desconectar audioClient aquí, para que el servicio siga
        // transmitiendo
        // try {
        //     audioRenderer.release()
        // } catch (e: Exception) {
        //     Log.w(TAG, "⚠️ Error liberando renderer: ${e.message}")
        // }

        saveSessionPreferences()

        Log.d(TAG, "✅ Activity destruida, pero el Service sigue activo")
    }

    /** Configura Edge-to-Edge y padding para status bar/notch igual que MainActivity */
    private fun setupEdgeToEdgeInsets() {
        val mainContainer = findViewById<View>(R.id.native_audio_root)
        if (mainContainer != null) {
            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(mainContainer) {
                    view,
                    windowInsets ->
                val sysBarInsets =
                    windowInsets.getInsets(
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
            val headphoneTypes =
                setOf(
                    AudioDeviceInfo.TYPE_WIRED_HEADPHONES,
                    AudioDeviceInfo.TYPE_WIRED_HEADSET,
                    AudioDeviceInfo.TYPE_USB_HEADSET,
                    AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
                    AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
                    AudioDeviceInfo.TYPE_USB_DEVICE,
                    AudioDeviceInfo.TYPE_USB_ACCESSORY
                )
            audioManager.getDevices(AudioManager.GET_DEVICES_OUTPUTS).any {
                it.type in headphoneTypes
            }
        } else {
            audioManager.isWiredHeadsetOn || audioManager.isBluetoothA2dpOn
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus &&
            resources.configuration.orientation ==
            android.content.res.Configuration.ORIENTATION_LANDSCAPE
        ) {
            hideSystemUI()
        }
    }

    /**
     * ✅ MODERNO: Oculta barra de estado y navegación en modo Landscape Usa WindowInsetsController
     * (API 30+) - método recomendado por Google Fallback a systemUiVisibility para dispositivos más
     * antiguos (API 16-29)
     */
    private fun hideSystemUI() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // API 30+: Método moderno con WindowInsetsController
            val controller = WindowCompat.getInsetsController(window, window.decorView)
            if (controller != null) {
                // Ocultar ambas barras (estado y navegación)
                controller.hide(
                    androidx.core.view.WindowInsetsCompat.Type.statusBars() or
                            androidx.core.view.WindowInsetsCompat.Type.navigationBars()
                )
                // Modo sticky: reaparecen temporalmente con interacción, luego se ocultan de nuevo
                controller.systemBarsBehavior =
                    androidx.core.view.WindowInsetsControllerCompat
                        .BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
            // También usa LAYOUT flags para que el contenido use toda la pantalla
            WindowCompat.setDecorFitsSystemWindows(window, false)
        } else {
            // API 16-29: Método legacy (fallback para compatibilidad)
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility =
                (View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
                        View.SYSTEM_UI_FLAG_FULLSCREEN or
                        View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                        View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                        View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
                        View.SYSTEM_UI_FLAG_LAYOUT_STABLE)
        }
    }
}
