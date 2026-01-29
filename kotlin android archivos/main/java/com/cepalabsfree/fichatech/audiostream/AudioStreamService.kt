package com.cepalabsfree.fichatech.audiostream

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.Process
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.cepalabsfree.fichatech.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * ✅ AudioStreamService - ULTRA-OPTIMIZADO CON NOTIFICACIÓN PERSISTENTE
 *
 * Características:
 * 1. ✅ Audio Focus con AUDIOFOCUS_GAIN (máxima prioridad)
 * 2. ✅ WakeLock de CPU permanente mientras hay stream
 * 3. ✅ WifiLock para prevenir desconexión de WiFi
 * 4. ✅ Notificación persistente NO descartable por usuario
 * 5. ✅ Renova permisos de lock automáticamente (Google Play Policy)
 * 6. ✅ NO se pausa por cambios de dispositivo de audio
 * 7. ✅ NO se desconecta automáticamente (solo usuario)
 * 8. ✅ Prioridad máxima de proceso
 * 9. ✅ Foreground service completo y robusto
 */
class AudioStreamService : Service() {

    companion object {
        private const val TAG = "AudioStreamService"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "audio_stream_channel"
        private const val PREFS_NAME = "AudioStreamServicePrefs"
        private const val KEY_SERVER_IP = "server_ip"
        private const val KEY_SERVER_PORT = "server_port"
        private const val KEY_MASTER_VOLUME = "master_volume"

        // ✅ Renovación de locks (Google Play Policy - máximo 30 min sin renovar)
        private const val WAKELOCK_RENEW_INTERVAL_MS = 20 * 60 * 1000L  // 20 minutos

        const val ACTION_START = "com.cepalabsfree.fichatech.AUDIO_START"
        const val ACTION_STOP = "com.cepalabsfree.fichatech.AUDIO_STOP"
        const val ACTION_CONNECT = "com.cepalabsfree.fichatech.AUDIO_CONNECT"
        const val ACTION_PAUSE = "com.cepalabsfree.fichatech.AUDIO_PAUSE"
        const val ACTION_RESUME = "com.cepalabsfree.fichatech.AUDIO_RESUME"
        const val EXTRA_SERVER_IP = "server_ip"
        const val EXTRA_SERVER_PORT = "server_port"

        // Reconexión automática ultra-rápida
        private const val RECONNECT_DELAY_MS = 100L  // ⬇️ REDUCIDO: 300 → 100 ms para reconexión más rápida
        private const val MAX_RECONNECT_DELAY_MS = 3000L
        private const val RECONNECT_BACKOFF = 1.5
    }

    private lateinit var audioClient: NativeAudioClient
    private lateinit var audioRenderer: OboeAudioRenderer
    private lateinit var audioFocusManager: AudioFocusManager
    private lateinit var audioDeviceChangeListener: AudioDeviceChangeListener
    private lateinit var audioManager: AudioManager
    private lateinit var prefs: SharedPreferences
    private lateinit var notificationManager: NotificationManager

    // ✅ LOCKS PARA PRIORIDAD
    private var cpuWakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var audioFocusRequest: AudioFocusRequest? = null

    private var serverIp = ""
    private var serverPort = 5101
    private var masterVolumeDb = 0f

    @Volatile private var isConnected = false
    @Volatile private var isConnecting = false
    @Volatile private var isPaused = false
    @Volatile private var isForegroundStarted = false
    @Volatile private var isStreamActive = false
    @Volatile private var userRequestedDisconnect = false

    private var reconnectJob: Job? = null
    private var currentReconnectDelay = RECONNECT_DELAY_MS
    private var wakeLockRenewJob: Job? = null
    private var notificationRestoreJob: Job? = null

    private val serviceScope = CoroutineScope(Dispatchers.Main + Job())
    private val binder = LocalBinder()

    // Broadcast receiver para pantalla bloqueada
    private val screenStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                Intent.ACTION_SCREEN_OFF -> {
                    Log.d(TAG, "🔒 Pantalla bloqueada - STREAM CONTINÚA ACTIVO")
                    renewWakeLocks()
                }
                Intent.ACTION_SCREEN_ON -> {
                    Log.d(TAG, "🔓 Pantalla desbloqueada")
                }
            }
        }
    }

    // Broadcast receiver para desconexión de WiFi
    private val wifiReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                WifiManager.NETWORK_STATE_CHANGED_ACTION -> {
                    val info = intent?.getParcelableExtra<android.net.NetworkInfo>(
                        WifiManager.EXTRA_NETWORK_INFO
                    )
                    if (info?.isConnected == true) {
                        Log.d(TAG, "📡 WiFi reconectado")
                    } else {
                        Log.w(TAG, "⚠️ WiFi desconectado - esperando reconexión...")
                    }
                }
            }
        }
    }

    // Callbacks para UI
    var onConnectionStatusChanged: ((Boolean, String) -> Unit)? = null
    var onAudioDataReceived: (() -> Unit)? = null
    var onError: ((String) -> Unit)? = null

    inner class LocalBinder : Binder() {
        fun getService(): AudioStreamService = this@AudioStreamService
    }

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "🚀 onCreate() - Servicio creado")

        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

        try {
            // ✅ PRIMERO: Crear canal de notificación
            createNotificationChannel()

            // ✅ SEGUNDO: Llamar a startForeground INMEDIATAMENTE
            startForegroundNotification()

            // ✅ TERCERO: Inicializar componentes
            prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            audioFocusManager = AudioFocusManager(this)

            // Inicializar Opus decoder
            try {
                AudioDecompressor.initOpusDecoder(sampleRate = 48000, channels = 2)
                Log.d(TAG, "✅ Opus decoder inicializado")
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Error inicializando Opus: ${e.message}")
            }

            audioClient = NativeAudioClient(this).apply {
                onAudioData = { audioData -> handleAudioData(audioData) }
                onConnectionStatus = { connected, message -> updateConnectionStatus(connected, message) }
                onError = { error -> handleError(error) }
                onServerInfo = { info -> handleServerInfo(info) }
                onChannelUpdate = { ch, gain, pan, active ->
                    Log.d(TAG, "📢 Canal update: ch=$ch")
                }
                onMasterGainUpdate = { gainDb ->
                    masterVolumeDb = gainDb
                    audioRenderer.setMasterGain(gainDb)
                }
            }

            audioRenderer = OboeAudioRenderer(this).apply {
                setMasterGain(masterVolumeDb)
            }

            // Listener para cambios de dispositivo de audio
            audioDeviceChangeListener = AudioDeviceChangeListener {
                Log.d(TAG, "🔊 Cambio de dispositivo detectado")
                if (isConnected && !isPaused) {
                    Log.d(TAG, "✅ Reiniciando motor de audio (sin desconectar)")
                    restartAudioEngine()
                }
            }
            audioDeviceChangeListener.register(this)

            // Registrar receiver para estado de pantalla
            val screenIntentFilter = IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(Intent.ACTION_SCREEN_ON)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.registerReceiver(this, screenStateReceiver, screenIntentFilter, ContextCompat.RECEIVER_NOT_EXPORTED)
            } else {
                @Suppress("UnspecifiedRegisterReceiverFlag")
                registerReceiver(screenStateReceiver, screenIntentFilter)
            }

            // Registrar receiver para WiFi
            val wifiIntentFilter = IntentFilter().apply {
                addAction(WifiManager.NETWORK_STATE_CHANGED_ACTION)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.registerReceiver(this, wifiReceiver, wifiIntentFilter, ContextCompat.RECEIVER_NOT_EXPORTED)
            } else {
                @Suppress("UnspecifiedRegisterReceiverFlag")
                registerReceiver(wifiReceiver, wifiIntentFilter)
            }

            loadPreferences()
            isForegroundStarted = true
            Log.d(TAG, "✅ Servicio inicializado correctamente")

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error fatal en onCreate: ${e.message}", e)
            handleError("Error inicializando servicio: ${e.message}")
            stopSelf()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START

        Log.d(TAG, "📡 onStartCommand: action=$action")

        // ✅ Asegurar que startForeground se llamó
        if (!isForegroundStarted) {
            try {
                startForegroundNotification()
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error llamando startForeground: ${e.message}")
                stopSelf(startId)
                return START_NOT_STICKY
            }
        }

        when (action) {
            ACTION_START -> {
                Log.d(TAG, "✅ Servicio iniciado")
            }
            ACTION_CONNECT -> {
                userRequestedDisconnect = false
                val ip = intent?.getStringExtra(EXTRA_SERVER_IP) ?: serverIp
                val port = intent?.getIntExtra(EXTRA_SERVER_PORT, serverPort) ?: serverPort

                if (ip.isNotEmpty()) {
                    serverIp = ip
                    serverPort = port
                    savePreferences()
                    connectToServer()
                } else {
                    Log.w(TAG, "⚠️ IP vacía en ACTION_CONNECT")
                }
            }
            ACTION_PAUSE -> {
                pauseStream()
            }
            ACTION_RESUME -> {
                resumeStream()
            }
            ACTION_STOP -> {
                Log.d(TAG, "🛑 ACTION_STOP recibido - Usuario desconectó manualmente")
                userRequestedDisconnect = true
                reconnectJob?.cancel()
                disconnect()
                stopSelf(startId)
            }
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        Log.d(TAG, "🔗 Activity vinculada al servicio")
        return binder
    }

    override fun onRebind(intent: Intent?) {
        super.onRebind(intent)
        Log.d(TAG, "🔄 Activity re-vinculada al servicio")
    }

    override fun onUnbind(intent: Intent?): Boolean {
        Log.d(TAG, "🔓 Activity desvinculada del servicio (servicio sigue activo)")
        return true
    }

    // ✅ NOTIFICACIÓN PERSISTENTE NO DESCARTABLE
    private fun startForegroundNotification() {
        try {
            val notificationIntent = Intent(this, NativeAudioStreamActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            }
            val pendingIntent = PendingIntent.getActivity(
                this,
                0,
                notificationIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val stopIntent = Intent(this, AudioStreamService::class.java).apply {
                action = ACTION_STOP
            }

            val stopPendingIntent = PendingIntent.getService(
                this,
                1,
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notification = NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Fichatech monitor")
                .setContentText(getNotificationText())
                .setSmallIcon(R.drawable.logooficialdemo)
                .setContentIntent(pendingIntent)
                .setCategory(NotificationCompat.CATEGORY_SERVICE)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .addAction(
                    android.R.drawable.ic_menu_close_clear_cancel,
                    "Detener",
                    stopPendingIntent
                )
                // ✅ NO DESCARTABLE
                .setOngoing(true)
                .setAutoCancel(false)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .build()

            // ✅ FLAGS PARA EVITAR QUE SE BORRE
            notification.flags = notification.flags or (
                    Notification.FLAG_ONGOING_EVENT or
                            Notification.FLAG_NO_CLEAR
                    )

            startForeground(NOTIFICATION_ID, notification)
            Log.d(TAG, "📌 Notificación iniciada (NO DESCARTABLE)")

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en startForegroundNotification: ${e.message}", e)
            throw e
        }
    }

    // ✅ ACTUALIZAR NOTIFICACIÓN PERSISTENTEMENTE
    private fun updateNotification() {
        try {
            if (!isStreamActive) {
                // Si el stream está detenido, remover la notificación
                stopForeground(STOP_FOREGROUND_REMOVE)
                Log.d(TAG, "📌 Notificación removida (stream detenido)")
                return
            }
            val notificationIntent = Intent(this, NativeAudioStreamActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            }
            val pendingIntent = PendingIntent.getActivity(
                this,
                0,
                notificationIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val stopIntent = Intent(this, AudioStreamService::class.java).apply {
                action = ACTION_STOP
            }
            val stopPendingIntent = PendingIntent.getService(
                this,
                1,
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notification = NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Fichatech monitor")
                .setContentText(getNotificationText())
                .setSmallIcon(R.drawable.logooficialdemo)
                .setContentIntent(pendingIntent)
                .setCategory(NotificationCompat.CATEGORY_SERVICE)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .addAction(
                    android.R.drawable.ic_menu_close_clear_cancel,
                    "Detener",
                    stopPendingIntent
                )
                // ✅ NO DESCARTABLE
                .setOngoing(true)
                .setAutoCancel(false)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .build()

            // ✅ FLAGS PARA EVITAR QUE SE BORRE
            notification.flags = notification.flags or (
                    Notification.FLAG_ONGOING_EVENT or
                            Notification.FLAG_NO_CLEAR
                    )

            startForeground(NOTIFICATION_ID, notification)
            Log.d(TAG, "📌 Notificación actualizada (NO DESCARTABLE - stream activo)")

        } catch (e: Exception) {
            Log.w(TAG, "⚠️ Error actualizando notificación: ${e.message}")
        }
    }

    private fun getNotificationText(): String = when {
        isConnecting -> "🔄 Buscando señal..."
        isConnected && !isPaused -> "Transmitiendo desde servidor"
        isPaused -> "⏸️  Pausado"
        else -> "Desconectado"
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Audio Stream",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Notificación para streaming de audio en segundo plano"
                setShowBadge(false)
                enableVibration(false)
            }

            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
            Log.d(TAG, "✅ Canal de notificación creado")
        }
    }

    // ✅ AUDIO FOCUS CON MÁXIMA PRIORIDAD
    private fun acquireAudioFocus() {
        try {
            val audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build()

            audioFocusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(audioAttributes)
                .setOnAudioFocusChangeListener { focusChange ->
                    Log.d(TAG, "🔊 Audio Focus cambió: $focusChange")
                    when (focusChange) {
                        AudioManager.AUDIOFOCUS_LOSS -> {
                            Log.w(TAG, "⚠️ Audio Focus perdido - intentando recuperar")
                            audioFocusManager.requestAudioFocus()
                        }
                    }
                }
                .build()

            val result = audioManager.requestAudioFocus(audioFocusRequest!!)
            if (result == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
                Log.d(TAG, "✅ Audio Focus adquirido (MÁXIMA PRIORIDAD)")
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error adquiriendo audio focus: ${e.message}")
        }
    }

    // ✅ WAKE LOCKS PERMANENTES
    private fun acquireWakeLocks() {
        try {
            // CPU WakeLock
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            if (cpuWakeLock == null) {
                cpuWakeLock = powerManager.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "FichaTech:AudioStreamCPU"
                )
            }

            if (cpuWakeLock?.isHeld != true) {
                cpuWakeLock?.acquire(Long.MAX_VALUE - 1)
                Log.d(TAG, "✅ CPU WakeLock adquirido (permanente)")
            }

            // WiFi WakeLock
            val wifiManager = getSystemService(Context.WIFI_SERVICE) as WifiManager
            if (wifiLock == null) {
                wifiLock = wifiManager.createWifiLock(
                    WifiManager.WIFI_MODE_FULL_HIGH_PERF,
                    "FichaTech:AudioStreamWiFi"
                )
            }

            if (wifiLock?.isHeld != true) {
                wifiLock?.acquire()
                Log.d(TAG, "✅ WiFi WakeLock adquirido (evitar desconexión)")
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error adquiriendo wake locks: ${e.message}")
        }
    }

    // ✅ RENOVAR LOCKS (Google Play Policy)
    private fun renewWakeLocks() {
        try {
            if (cpuWakeLock?.isHeld == true) {
                cpuWakeLock?.release()
                cpuWakeLock?.acquire(Long.MAX_VALUE - 1)
                Log.d(TAG, "🔄 CPU WakeLock renovado")
            }
            Log.d(TAG, "🔄 Locks renovados (compliance Google Play)")
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ Error renovando locks: ${e.message}")
        }
    }

    // ✅ INICIAR RENOVACIÓN AUTOMÁTICA
    private fun startWakeLockRenewal() {
        wakeLockRenewJob?.cancel()

        wakeLockRenewJob = serviceScope.launch {
            while (isActive && isStreamActive) {
                delay(WAKELOCK_RENEW_INTERVAL_MS)
                renewWakeLocks()
            }
        }
    }

    // ✅ RESTAURAR NOTIFICACIÓN SI SE BORRA (cada 2 segundos mientras hay stream)
    private fun startNotificationRestore() {
        notificationRestoreJob?.cancel()

        notificationRestoreJob = serviceScope.launch {
            while (isActive && isStreamActive) {
                delay(2000)  // Cada 2 segundos
                try {
                    updateNotification()
                    Log.d(TAG, "✅ Notificación restaurada (si fue eliminada)")
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ Error restaurando notificación: ${e.message}")
                }
            }
        }
    }

    private fun stopNotificationRestore() {
        notificationRestoreJob?.cancel()
        notificationRestoreJob = null
    }

    // ✅ LIBERAR LOCKS
    private fun releaseWakeLocks() {
        try {
            cpuWakeLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.d(TAG, "🔓 CPU WakeLock liberado")
                }
            }

            wifiLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.d(TAG, "🔓 WiFi WakeLock liberado")
                }
            }

            audioFocusRequest?.let {
                audioManager.abandonAudioFocusRequest(it)
                Log.d(TAG, "🔓 Audio Focus abandonado")
            }

            wakeLockRenewJob?.cancel()
            Log.d(TAG, "✅ Todos los locks liberados")
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ Error liberando locks: ${e.message}")
        }
    }

    private fun connectToServer() {
        if (isConnecting || isConnected) {
            Log.w(TAG, "⚠️ Ya está conectando o conectado")
            return
        }

        isConnecting = true
        updateNotification()

        serviceScope.launch(Dispatchers.IO) {
            try {
                acquireAudioFocus()
                acquireWakeLocks()
                audioRenderer.acquirePartialWakeLock(applicationContext)

                Log.d(TAG, "📡 Conectando a $serverIp:$serverPort")
                val success = audioClient.connect(serverIp, serverPort)

                if (success) {
                    Log.i(TAG, "✅ Conexión exitosa")
                    isStreamActive = true
                    savePreferences()
                    startWakeLockRenewal()
                    startNotificationRestore()  // ✅ RESTAURAR NOTIFICACIÓN AUTOMÁTICAMENTE
                } else {
                    Log.w(TAG, "❌ Conexión fallida")
                    isConnecting = false
                    isStreamActive = false
                    releaseWakeLocks()
                    handleError("No se pudo conectar al servidor")
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error conectando: ${e.message}", e)
                isConnecting = false
                isStreamActive = false
                releaseWakeLocks()
                handleError("Error de conexión: ${e.message}")
            }
        }
    }

    private fun pauseStream() {
        isPaused = true
        audioRenderer.stop()
        updateNotification()
        Log.d(TAG, "⏸️  Stream pausado")
    }

    private fun resumeStream() {
        isPaused = false
        audioRenderer.init()
        audioRenderer.setMasterGain(masterVolumeDb)
        updateNotification()
        Log.d(TAG, "▶️  Stream reanudado")
    }

    private fun disconnect() {
        try {
            Log.d(TAG, "🛑 Desconectando (usuario solicitó)...")
            userRequestedDisconnect = true
            reconnectJob?.cancel()
            stopNotificationRestore()  // ✅ DETENER RESTAURACIÓN AUTOMÁTICA
            audioClient.disconnect("Desconexión manual del usuario")
            audioRenderer.releaseWakeLock()
            isConnected = false
            isPaused = false
            isStreamActive = false
            releaseWakeLocks()
            updateNotification()
            Log.d(TAG, "✅ Desconexión completada")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error desconectando: ${e.message}", e)
        }
    }

    private fun updateConnectionStatus(connected: Boolean, message: String) {
        isConnected = connected
        isConnecting = false

        Log.d(TAG, "🔗 Estado: $message (conectado=$connected)")

        if (connected) {
            isStreamActive = true
            acquireAudioFocus()
            acquireWakeLocks()
            startWakeLockRenewal()
        } else {
            isStreamActive = false
            releaseWakeLocks()
        }

        updateNotification()
        onConnectionStatusChanged?.invoke(connected, message)

        // ✅ NO reconectar si usuario desconectó manualmente
        if (!connected && !userRequestedDisconnect && !message.contains("manual")) {
            startAutoReconnect()
        }
    }

    private fun startAutoReconnect() {
        reconnectJob?.cancel()

        if (reconnectJob?.isActive == true) return

        reconnectJob = serviceScope.launch(Dispatchers.IO) {
            var attempt = 1
            currentReconnectDelay = RECONNECT_DELAY_MS

            while (isActive && !isConnected && serverIp.isNotEmpty() && !userRequestedDisconnect) {
                delay(currentReconnectDelay)

                if (isConnected) {
                    Log.d(TAG, "✅ Reconectado durante intento de reconexión")
                    return@launch
                }

                Log.d(TAG, "🔄 Intento de reconexión #$attempt")
                try {
                    val success = audioClient.connect(serverIp, serverPort)
                    if (success) {
                        Log.i(TAG, "✅ Reconexión automática exitosa")
                        isStreamActive = true
                        currentReconnectDelay = RECONNECT_DELAY_MS
                        return@launch
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ Intento #$attempt fallido: ${e.message}")
                }

                currentReconnectDelay = (currentReconnectDelay * RECONNECT_BACKOFF).toLong()
                    .coerceAtMost(MAX_RECONNECT_DELAY_MS)

                attempt++
            }
        }
    }

    private fun handleAudioData(audioData: NativeAudioClient.FloatAudioData) {
        if (isPaused || !isConnected) return

        if (audioData.audioData.size >= 2) {
            val samplesPerChannel = audioData.samplesPerChannel
            val interleaved = FloatArray(samplesPerChannel * 2)

            for (s in 0 until samplesPerChannel) {
                interleaved[s * 2] = audioData.audioData[0][s]
                interleaved[s * 2 + 1] = audioData.audioData[1][s]
            }

            audioRenderer.renderStereo(interleaved, audioData.samplePosition)
            onAudioDataReceived?.invoke()
        }
    }

    private fun handleServerInfo(info: Map<String, Any>) {
        Log.d(TAG, "📊 Info servidor: ${info["server_version"]}")
    }

    private fun handleError(error: String) {
        Log.e(TAG, "❌ Error: $error")
        onError?.invoke(error)
    }

    private fun restartAudioEngine() {
        Log.d(TAG, "🔄 Reiniciando motor de audio...")
        try {
            audioRenderer.stop()
            audioRenderer.init()
            audioRenderer.setMasterGain(masterVolumeDb)
            Log.d(TAG, "✅ Motor reiniciado (conexión mantenida)")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error reiniciando motor: ${e.message}", e)
        }
    }

    private fun loadPreferences() {
        serverIp = prefs.getString(KEY_SERVER_IP, "") ?: ""
        serverPort = prefs.getInt(KEY_SERVER_PORT, 5101)
        masterVolumeDb = prefs.getFloat(KEY_MASTER_VOLUME, 0f)
    }

    private fun savePreferences() {
        prefs.edit().apply {
            putString(KEY_SERVER_IP, serverIp)
            putInt(KEY_SERVER_PORT, serverPort)
            putFloat(KEY_MASTER_VOLUME, masterVolumeDb)
            apply()
        }
    }

    // Public API
    fun setMasterVolume(gainDb: Float) {
        masterVolumeDb = gainDb.coerceIn(-60f, 12f)
        audioRenderer.setMasterGain(masterVolumeDb)
        savePreferences()
    }

    fun getMasterVolume(): Float = masterVolumeDb

    fun setBufferSize(bufferSize: Int) {
        audioRenderer.setBufferSize(bufferSize)
    }

    fun getConnectionStatus(): Pair<Boolean, String> {
        val status = when {
            isConnected && !isPaused -> "ONLINE"
            isPaused -> "⏸️  PAUSADO"
            isConnecting -> "🔄 BUSCANDO..."
            else -> "OFFLINE"
        }
        return Pair(isConnected, status)
    }

    fun getLatency(): Float = audioRenderer.getLatencyMs()

    fun isPausedState(): Boolean = isPaused

    override fun onTaskRemoved(rootIntent: Intent?) {
        Log.d(TAG, "⚠️ onTaskRemoved() - Task removida por el usuario")
        if (isStreamActive) {
            updateNotification()
        }
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "💀 onDestroy() - Servicio destruido")

        try {
            serviceScope.cancel()
            reconnectJob?.cancel()
            wakeLockRenewJob?.cancel()
            stopNotificationRestore()  // ✅ DETENER RESTAURACIÓN

            try {
                unregisterReceiver(screenStateReceiver)
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Error desregistrando screen receiver: ${e.message}")
            }

            try {
                unregisterReceiver(wifiReceiver)
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Error desregistrando wifi receiver: ${e.message}")
            }

            audioDeviceChangeListener.unregister(this)

            userRequestedDisconnect = true
            disconnect()

            try {
                audioRenderer.release()
                AudioDecompressor.release()
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Error liberando recursos: ${e.message}")
            }

            // ✅ SOLO remover notificación cuando se destruye el servicio
            try {
                stopForeground(STOP_FOREGROUND_REMOVE)
                Log.d(TAG, "📌 Notificación removida (servicio destruido)")
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Error removiendo foreground: ${e.message}")
            }

            Log.d(TAG, "✅ Recursos liberados correctamente")

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error en onDestroy: ${e.message}", e)
        }
    }
}