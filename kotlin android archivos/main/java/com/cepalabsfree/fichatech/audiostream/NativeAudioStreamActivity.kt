package com.cepalabsfree.fichatech.audiostream

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.res.Configuration
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Process
import android.util.Log
import android.view.View
import android.view.ViewTreeObserver
import android.view.WindowManager
import android.widget.*
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.content.getSystemService
import androidx.lifecycle.lifecycleScope
import com.cepalabsfree.fichatech.R
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.AdView
import com.google.android.gms.ads.MobileAds
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.abs

/**
 * ✅ NativeAudioStreamActivity - MODIFICADA
 * - Usa AudioStreamService para segundo plano
 * - Funciona con pantalla bloqueada
 * - Sin foreground service en la Activity
 */
class NativeAudioStreamActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "AudioStreamActivity"
        private const val PREFS_NAME = "AudioStreamPrefs"
        private const val KEY_LAST_IP = "last_ip"
        private const val KEY_LAST_PORT = "last_port"
        private const val KEY_LAST_VOLUME = "last_volume"
        private const val METRICS_UPDATE_INTERVAL_MS = 250L
    }

    // ========== PERMISSIONS ==========
    private val requestNotificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            Log.d(TAG, "✅ Usuario concedió permiso POST_NOTIFICATIONS")
            showToast(getString(R.string.notifications_enabled))
            // Intentar conectar si había una conexión pendiente
            if (pendingConnect) {
                pendingConnect = false
                connectToServer()
            }
        } else {
            Log.w(TAG, "⚠️ Usuario negó permiso POST_NOTIFICATIONS")
            showToast(getString(R.string.notifications_disabled))
            // Mostrar diálogo explicativo
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle(getString(R.string.permission_required_title))
                .setMessage(getString(R.string.permission_required_message))
                .setPositiveButton(getString(R.string.go_to_settings)) { _, _ ->
                    val intent = android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                        data = android.net.Uri.parse("package:$packageName")
                    }
                    startActivity(intent)
                }
                .setNegativeButton(getString(R.string.cancel), null)
                .show()
        }
    }

    private val requestBatteryOptimizationLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        // Verificar si el permiso fue concedido después de volver de ajustes
        val isGranted = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
                getSystemService<android.os.PowerManager>()?.isIgnoringBatteryOptimizations(packageName) == true

        if (isGranted) {
            Log.d(TAG, "✅ Usuario concedió ignorar optimizaciones de batería")
            showToast(getString(R.string.battery_ignored))
            // Intentar conectar si había una conexión pendiente
            if (pendingConnect) {
                pendingConnect = false
                connectToServer()
            }
        } else {
            Log.w(TAG, "⚠️ Usuario negó ignorar optimizaciones de batería")
            showToast(getString(R.string.battery_active))
            // No mostrar diálogo, permitir conectar de todos modos y solicitar de nuevo la próxima vez
            if (pendingConnect) {
                pendingConnect = false
            }
        }
    }

    // Referencias UI
    private lateinit var ipEditText: EditText
    private lateinit var portEditText: EditText
    private lateinit var connectButton: Button
    private lateinit var masterVolumeSeekBar: SeekBar
    private lateinit var masterVolumeText: TextView
    private lateinit var muteButton: Button
    private lateinit var latencyText: TextView
    private lateinit var ultraLowLatencySwitch: Switch
    private lateinit var openMixerButton: ImageButton

    private lateinit var adViewAudioStream: AdView

    // Servicio
    private var audioStreamService: AudioStreamService? = null
    private var isServiceBound = false

    private var isConnected = false
    private var isMuted = false
    private var masterVolumeDb = 0f

    private var isMetricsActive = false
    private val uiHandler = Handler(Looper.getMainLooper())
    private var metricsUpdateRunnable: Runnable? = null

    // Latencia
    private var lastLatencyMs: Float = 0f
    private var latencySamples: MutableList<Float> = mutableListOf()
    private val LATENCY_AVG_WINDOW = 5

    // Connection al servicio
    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {
            Log.d(TAG, "✅ Servicio conectado")
            val binder = service as AudioStreamService.LocalBinder
            audioStreamService = binder.getService()
            isServiceBound = true

            // Configurar callbacks
            audioStreamService?.onConnectionStatusChanged = { connected, message ->
                updateConnectionStatus(connected, message)
            }

            audioStreamService?.onError = { error ->
                showError(error)
            }

            audioStreamService?.onAudioDataReceived = {
                runOnUiThread {
                    if (isConnected) {
                        val latency = audioStreamService?.getLatency() ?: 0f
                        updateLatencyUI(latency)
                    }
                }
            }

            // Sincronizar UI con estado actual
            val (connected, status) = audioStreamService?.getConnectionStatus() ?: Pair(false, "OFFLINE")
            updateConnectionStatus(connected, status)
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            Log.d(TAG, "🔓 Servicio desconectado")
            isServiceBound = false
            audioStreamService = null
        }
    }

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

        initializeViews()
        loadSessionPreferences()
// Inicializar AdMob
        adViewAudioStream = findViewById(R.id.adViewAudioStream)
        MobileAds.initialize(this) {}
        val adRequest = AdRequest.Builder().build()
        adViewAudioStream.loadAd(adRequest)
        // Restaurar estado de conexión pendiente
        pendingConnect = savedInstanceState?.getBoolean("pendingConnect", false) ?: false

        // Iniciar servicio
        startAudioService()
        bindAudioService()

        Log.d(TAG, "✅ Activity creada")
    }

    private fun startAudioService() {
        val serviceIntent = Intent(this, AudioStreamService::class.java).apply {
            action = AudioStreamService.ACTION_START
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }

        Log.d(TAG, "🚀 Servicio iniciado")
    }

    private fun bindAudioService() {
        val serviceIntent = Intent(this, AudioStreamService::class.java)
        bindService(serviceIntent, serviceConnection, Context.BIND_AUTO_CREATE)
        Log.d(TAG, "🔗 Vinculado al servicio")
    }

    private fun initializeViews() {
        ipEditText = findViewById(R.id.ipEditText)
        ipEditText.inputType = InputType.TYPE_CLASS_TEXT
        portEditText = findViewById(R.id.portEditText)
        connectButton = findViewById(R.id.connectButton)
        masterVolumeSeekBar = findViewById(R.id.masterVolumeSeekBar)
        masterVolumeText = findViewById(R.id.masterVolumeText)
        muteButton = findViewById(R.id.muteButton)
        latencyText = findViewById(R.id.latencyText)
        ultraLowLatencySwitch = findViewById(R.id.ultraLowLatencySwitch)
        openMixerButton = findViewById(R.id.openMixerButton)

        ultraLowLatencySwitch.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                audioStreamService?.setBufferSize(32)
                showToast(getString(R.string.ultra_low_latency_mode))
            } else {
                audioStreamService?.setBufferSize(120)
                showToast(getString(R.string.compatibility_mode))
            }
        }

        openMixerButton.setOnClickListener {
            val ip = ipEditText.text.toString().trim()
            if (ip.isEmpty()) {
                showToast("Ingresa una IP primero")
                return@setOnClickListener
            }
            val url = "http://$ip:5100/"
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            startActivity(intent)
        }

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
                    audioStreamService?.setMasterVolume(if (isMuted) -60f else masterVolumeDb)
                    // Guardar volumen inmediatamente cuando cambia
                    saveSessionPreferences()
                }
                override fun onStartTrackingTouch(seekBar: SeekBar?) {}
                override fun onStopTrackingTouch(seekBar: SeekBar?) {}
            }
        )

        muteButton.setOnClickListener { toggleMute() }

        connectButton.text = getString(R.string.connect_button)
        muteButton.text = getString(R.string.audio_on)

        // Guardar preferencias al cambiar IP o puerto
        ipEditText.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                saveSessionPreferences()
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })

        portEditText.addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                saveSessionPreferences()
            }
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
        })
    }

    private var pendingConnect = false

    private fun connectToServer() {
        val serverIp = ipEditText.text.toString().trim()
        if (serverIp.isEmpty()) {
            showToast(getString(R.string.enter_ip_warning))
            return
        }

        val serverPort = portEditText.text.toString().toIntOrNull() ?: 5101

        connectButton.isEnabled = false
        connectButton.text = getString(R.string.connecting_button)

        // Enviar intención de conexión al servicio
        val intent = Intent(this, AudioStreamService::class.java).apply {
            action = AudioStreamService.ACTION_CONNECT
            putExtra(AudioStreamService.EXTRA_SERVER_IP, serverIp)
            putExtra(AudioStreamService.EXTRA_SERVER_PORT, serverPort)
        }

        // Si el permiso de notificaciones es requerido y no está concedido, esperar a que el usuario lo conceda
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            pendingConnect = true
            requestNotificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }

        // Si es necesario ignorar optimizaciones de batería, solicitar permiso
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
            !getSystemService<android.os.PowerManager>()?.isIgnoringBatteryOptimizations(packageName)!!) {
            pendingConnect = true
            requestBatteryOptimizationLauncher.launch(
                Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = android.net.Uri.parse("package:$packageName")
                }
            )
            // No retornar, permitir conectar de todos modos
        }

        startService(intent)
        Log.d(TAG, "📡 Solicitud de conexión enviada al servicio")
    }

    private fun disconnect() {
        val intent = Intent(this, AudioStreamService::class.java).apply {
            action = AudioStreamService.ACTION_STOP
        }
        startService(intent)

        isConnected = false
        connectButton.text = getString(R.string.connect_button)
        saveSessionPreferences()
        Log.d(TAG, "🛑 Desconexión solicitada")
    }

    private fun toggleMute() {
        isMuted = !isMuted
        if (isMuted) {
            audioStreamService?.setMasterVolume(-60f)
            muteButton.text = getString(R.string.audio_off)
            muteButton.setBackgroundColor(android.graphics.Color.parseColor("#FF4081"))
            muteButton.setTextColor(android.graphics.Color.WHITE)
        } else {
            audioStreamService?.setMasterVolume(masterVolumeDb)
            muteButton.text = getString(R.string.audio_on)
            muteButton.setBackgroundColor(android.graphics.Color.BLACK)
            muteButton.setTextColor(android.graphics.Color.WHITE)
        }
    }

    private fun togglePause() {
        val isPaused = audioStreamService?.isPausedState() ?: false
        val action = if (isPaused) AudioStreamService.ACTION_RESUME else AudioStreamService.ACTION_PAUSE
        val intent = Intent(this, AudioStreamService::class.java).apply {
            this.action = action
        }
        startService(intent)
    }

    private fun updateConnectionStatus(connected: Boolean, message: String) {
        isConnected = connected

        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread

            if (connected) {
                connectButton.text = getString(R.string.disconnect_button)
                connectButton.setBackgroundColor(android.graphics.Color.parseColor("#FF4081"))
                connectButton.setTextColor(android.graphics.Color.WHITE)
                connectButton.isEnabled = true

                try {
                    window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                } catch (_: Exception) {}

                // Mostrar latencia inmediatamente al conectar
                val latency = audioStreamService?.getLatency() ?: 0f
                latencyText.text = "${latency.toInt()} ms"
                latencyText.setTextColor(
                    when {
                        latency < 15 -> getColor(android.R.color.white)
                        latency < 30 -> getColor(android.R.color.holo_orange_light)
                        else -> getColor(android.R.color.holo_red_light)
                    }
                )
            } else {
                connectButton.text = getString(R.string.connect_button)
                connectButton.setBackgroundColor(android.graphics.Color.BLACK)
                connectButton.setTextColor(android.graphics.Color.WHITE)
                connectButton.isEnabled = true

                try {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                } catch (_: Exception) {}
                latencyText.text = "-- ms"
            }
        }
    }

    private fun saveSessionPreferences() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().apply {
            putString(KEY_LAST_IP, ipEditText.text.toString())
            putString(KEY_LAST_PORT, portEditText.text.toString())
            putFloat(KEY_LAST_VOLUME, masterVolumeDb)
            apply()
        }
    }

    private fun loadSessionPreferences() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val lastIp = prefs.getString(KEY_LAST_IP, "") ?: ""
        val lastPort = prefs.getString(KEY_LAST_PORT, "5101") ?: "5101"
        val lastVolume = prefs.getFloat(KEY_LAST_VOLUME, 0f)

        if (lastIp.isNotEmpty()) {
            ipEditText.setText(lastIp)
        }
        portEditText.setText(lastPort)

        masterVolumeDb = lastVolume
        masterVolumeSeekBar.progress = (lastVolume + 60).toInt()
        masterVolumeText.text = String.format("%.0f dB", lastVolume)
    }

    private fun updateLatencyUI(newLatency: Float) {
        // Agregar muestra y mantener ventana
        latencySamples.add(newLatency)
        if (latencySamples.size > LATENCY_AVG_WINDOW) latencySamples.removeAt(0)
        val avgLatency = latencySamples.average().toFloat()
        // Solo actualizar si cambia significativamente (>2ms)
        if (kotlin.math.abs(avgLatency - lastLatencyMs) > 2f || latencySamples.size == 1) {
            latencyText.text = "${avgLatency.toInt()} ms"
            latencyText.setTextColor(
                when {
                    avgLatency < 15 -> getColor(android.R.color.white)
                    avgLatency < 30 -> getColor(android.R.color.holo_orange_light)
                    else -> getColor(android.R.color.holo_red_light)
                }
            )
            lastLatencyMs = avgLatency
        }
    }

    private fun startMetricsUpdates() {
        if (isMetricsActive) return
        isMetricsActive = true
        metricsUpdateRunnable = object : Runnable {
            override fun run() {
                if (!isFinishing && !isDestroyed && isMetricsActive && isServiceBound) {
                    runOnUiThread {
                        if (isConnected) {
                            val latency = audioStreamService?.getLatency() ?: 0f
                            updateLatencyUI(latency)
                        } else {
                            latencyText.text = "-- ms"
                        }
                    }
                    if (isMetricsActive) {
                        uiHandler.postDelayed(this, 250) // Actualiza cada 250 ms
                    }
                }
            }
        }

        uiHandler.post(metricsUpdateRunnable!!)
        Log.d(TAG, "👁️ Métricas iniciadas")
    }

    private fun stopMetricsUpdates() {
        isMetricsActive = false
        metricsUpdateRunnable?.let { uiHandler.removeCallbacks(it) }
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

    override fun onResume() {
        super.onResume()
        startMetricsUpdates()
        adViewAudioStream.resume()

        // Verificar si hay una conexión pendiente y permisos concedidos
        if (pendingConnect) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
                getSystemService<android.os.PowerManager>()?.isIgnoringBatteryOptimizations(packageName) == true) {
                Log.d(TAG, "🔄 Conexión pendiente detectada - conectando...")
                pendingConnect = false
                connectToServer()
            }
        }

        Log.d(TAG, "👁️ Activity visible")
    }

    override fun onPause() {
        super.onPause()
        stopMetricsUpdates()
        adViewAudioStream.pause()

        Log.d(TAG, "😴 Activity pausada")
    }

    override fun onDestroy() {
        super.onDestroy()
        stopMetricsUpdates()

        if (isServiceBound) {
            unbindService(serviceConnection)
            isServiceBound = false
        }

        adViewAudioStream.destroy()

        Log.d(TAG, "💀 Activity destruida")
    }

    private fun setupEdgeToEdgeInsets() {
        val mainContainer = findViewById<View>(R.id.native_audio_root)
        if (mainContainer != null) {
            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(mainContainer) { view, windowInsets ->
                view.setPadding(view.paddingLeft, 0, view.paddingRight, 0)
                windowInsets
            }
        }
    }

    private fun hideSystemUI() {
        val controller = androidx.core.view.WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemUI()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean("pendingConnect", pendingConnect)
    }
}
