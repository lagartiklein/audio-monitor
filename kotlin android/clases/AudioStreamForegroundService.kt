package com.cepalabsfree.fichatech.audiostream

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.net.wifi.WifiManager
import android.util.Log
import androidx.core.app.NotificationCompat
import com.cepalabsfree.fichatech.R
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import org.json.JSONObject

/**
 * ✅ Foreground Service para streaming de audio RF
 * Cumple con políticas de Google Play:
 * - Notificación persistente obligatoria
 * - Tipo: FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
 * - WakeLock y WifiLock gestionados correctamente
 */
class AudioStreamForegroundService : Service() {

    companion object {
        private const val TAG = "AudioStreamService"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "audio_stream_channel"
        private const val CHANNEL_NAME = "Audio RF Streaming"

        // Actions para control desde notificación
        const val ACTION_START = "com.cepalabsfree.fichatech.START_STREAM"
        const val ACTION_STOP = "com.cepalabsfree.fichatech.STOP_STREAM"
        const val ACTION_DISCONNECT = "com.cepalabsfree.fichatech.DISCONNECT_STREAM"
        const val ACTION_CHANNEL_MONITOR_UPDATE = "com.cepalabsfree.fichatech.CHANNEL_MONITOR_UPDATE"

        // Estado del servicio
        @Volatile
        var isRunning = false
            private set

        // ✅ Timeout para locks (5 minutos) - Cumple con políticas Google Play
        private const val LOCK_TIMEOUT_MS = 5 * 60 * 1000L  // 5 minutos
        private const val RENEWAL_INTERVAL_MS = 4 * 60 * 1000L  // Renovar cada 4 minutos

        // ✅ SharedFlow seguro para monitoreo de canales (reemplaza broadcasts inseguros)
        val channelStatesFlow = MutableSharedFlow<Map<Int, OboeAudioRenderer.ChannelState>>(
            replay = 1,
            extraBufferCapacity = 1
        )
    }

    private val binder = AudioStreamBinder()
    private var wifiLock: WifiManager.WifiLock? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var notificationManager: NotificationManager? = null

    // Instancia de OboeAudioRenderer para monitoreo y procesamiento de audio
    private lateinit var oboeAudioRenderer: OboeAudioRenderer

    // Callbacks para comunicación con Activity
    var onStopRequested: (() -> Unit)? = null
    var onDisconnectRequested: (() -> Unit)? = null

    inner class AudioStreamBinder : Binder() {
        fun getService(): AudioStreamForegroundService = this@AudioStreamForegroundService
    }

    private val monitorHandler = Handler(Looper.getMainLooper())
    private val lockRenewalHandler = Handler(Looper.getMainLooper())
    private val lockRenewalRunnable = object : Runnable {
        override fun run() {
            renewLocks()
            lockRenewalHandler.postDelayed(this, RENEWAL_INTERVAL_MS)
        }
    }
    private val monitorRunnable = object : Runnable {
        override fun run() {
            // Suponiendo que tienes una instancia de OboeAudioRenderer llamada oboeAudioRenderer
            val channelStates = oboeAudioRenderer.getAllChannelStates()

            // Emitir nuevo estado de canales a través de SharedFlow
            channelStatesFlow.tryEmit(channelStates)

            monitorHandler.postDelayed(this, 200)
        }
    }

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "🎵 Servicio de streaming creado")
        notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        createNotificationChannel()
        // ✅ Usar singleton para compartir instancia con activity
        oboeAudioRenderer = OboeAudioRenderer.getInstance(this)
        monitorHandler.post(monitorRunnable)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "📡 onStartCommand: ${intent?.action}")

        when (intent?.action) {
            ACTION_START -> {
                startForegroundService()
            }
            ACTION_STOP -> {
                onStopRequested?.invoke()
                updateNotification("⏸️ Pausado", "Transmisión pausada")
            }
            ACTION_DISCONNECT -> {
                onDisconnectRequested?.invoke()
                stopForegroundService()
            }
        }

        // START_STICKY: el servicio se reinicia si Android lo mata
        return START_STICKY
    }

    private fun startForegroundService() {
        if (isRunning) {
            Log.d(TAG, "⚠️ Servicio ya está corriendo")
            return
        }

        try {
            // ✅ Crear notificación ANTES de startForeground()
            val notification = createNotification(
                "🔴 Transmitiendo",
                "Monitor de audio activo - Toca para abrir"
            )

            // ✅ Iniciar foreground con tipo específico (requerido Android 14+)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
                )
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
                )
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }

            // ✅ Adquirir locks DESPUÉS de startForeground()
            acquireLocks()
            // ✅ Iniciar renovación periódica de locks
            lockRenewalHandler.postDelayed(lockRenewalRunnable, RENEWAL_INTERVAL_MS)
            isRunning = true

            Log.d(TAG, "✅ Servicio foreground iniciado - Notificación persistente visible")

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error iniciando servicio: ${e.message}", e)
            stopSelf()
        }
    }

    private fun stopForegroundService() {
        Log.d(TAG, "🛑 Deteniendo servicio foreground")
        releaseLocks()
        isRunning = false

        // ✅ NUEVO: Cancelar notificación cuando se detiene el stream
        try {
            notificationManager?.cancel(NOTIFICATION_ID)
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ Error cancelando notificación: ${e.message}")
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }

        stopSelf()
    }

    private fun acquireLocks() {
        try {
            // ✅ WifiLock - Mantiene WiFi en full performance (sin timeout directo, renovado manualmente)
            val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            wifiLock = wifiManager.createWifiLock(
                WifiManager.WIFI_MODE_FULL_LOW_LATENCY ,
                "FichaTech:AudioStreamRF"
            ).apply {
                acquire()
                Log.d(TAG, "🔒 WifiLock adquirido")
            }

            // ✅ WakeLock - Mantiene CPU activa (con timeout)
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "FichaTech:AudioStreamCPU"
            ).apply {
                acquire(LOCK_TIMEOUT_MS)
                Log.d(TAG, "🔒 WakeLock adquirido (timeout: ${LOCK_TIMEOUT_MS}ms)")
            }

        } catch (e: Exception) {
            Log.e(TAG, "❌ Error adquiriendo locks: ${e.message}", e)
        }
    }

    private fun releaseLocks() {
        // Detener renovación de locks
        lockRenewalHandler.removeCallbacks(lockRenewalRunnable)

        try {
            wifiLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.d(TAG, "🔓 WifiLock liberado")
                }
            }
            wifiLock = null

            wakeLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.d(TAG, "🔓 WakeLock liberado")
                }
            }
            wakeLock = null

        } catch (e: Exception) {
            Log.e(TAG, "⚠️ Error liberando locks: ${e.message}")
        }
    }

    private fun renewLocks() {
        try {
            // ✅ WifiLock: No renovar para evitar interrupciones en ultra baja latencia
            // (se mantiene adquirido hasta detener el servicio)

            // Renueva el WakeLock si está activo
            wakeLock?.let {
                if (it.isHeld) {
                    it.acquire(LOCK_TIMEOUT_MS)
                    Log.d(TAG, "🔄 WakeLock renovado")
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "⚠️ Error renovando locks: ${e.message}")
        }
    }

    /**
     * ✅ Actualiza la notificación con nuevo estado
     * La notificación permanece visible mientras isRunning = true
     */
    fun updateNotification(title: String, message: String) {
        if (!isRunning) {
            Log.d(TAG, "⚠️ Servicio no está corriendo, ignorando actualización de notificación")
            return
        }

        try {
            val notification = createNotification(title, message)
            notificationManager?.notify(NOTIFICATION_ID, notification)
            Log.d(TAG, "🔔 Notificación actualizada: $title")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Error actualizando notificación: ${e.message}", e)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_LOW // LOW para evitar sonidos molestos
            ).apply {
                description = "Notificación de streaming de audio en tiempo real"
                setShowBadge(false)
                enableVibration(false)
                setSound(null, null)
                // ✅ NUEVO: No permitir que el usuario cancele el canal
                // (La notificación solo desaparece cuando se detiene el stream)
            }
            notificationManager?.createNotificationChannel(channel)
            Log.d(TAG, "📢 Canal de notificación creado")
        }
    }

    private fun createNotification(title: String, message: String): Notification {
        // Intent para abrir la activity al tocar la notificación
        val openIntent = Intent(this, NativeAudioStreamActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPendingIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Intent para desconectar
        val disconnectIntent = Intent(this, AudioStreamForegroundService::class.java).apply {
            action = ACTION_DISCONNECT
        }
        val disconnectPendingIntent = PendingIntent.getService(
            this, 1, disconnectIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // ✅ NUEVO: Intent para pausar/reanudar
        val pauseIntent = Intent(this, AudioStreamForegroundService::class.java).apply {
            action = ACTION_STOP
        }
        val pausePendingIntent = PendingIntent.getService(
            this, 2, pauseIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(message)
            .setSmallIcon(R.drawable.logooficialdemo) // Tu icono de app
            .setOngoing(true) // ✅ CRÍTICO: No se puede deslizar para cerrar
            .setContentIntent(openPendingIntent)
            
            // ✅ NUEVO: Estilo mejorado (compatibilidad con notificaciones modernas)
            .setStyle(NotificationCompat.BigTextStyle()
                .bigText(message)
                .setBigContentTitle(title))
            
            // ✅ Acción "Volver a la App"
            .addAction(
                android.R.drawable.ic_menu_view,
                "Abrir",
                openPendingIntent
            )
            // ✅ Acción "Pausar"
            .addAction(
                android.R.drawable.ic_media_pause,
                "Pausar",
                pausePendingIntent
            )
            // ✅ Acción "Desconectar" (destructiva)
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                "Desconectar",
                disconnectPendingIntent
            )
            
            // ✅ Categoría y prioridad (compatibilidad Google Play)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            
            // ✅ NUEVO: Color de acento (más moderno en Android 5+)
            .setColor(getColor(android.R.color.holo_blue_light))
            
            // ✅ NUEVO: Desactivar luz LED y sonidos (para no molestar)
            .setLights(0, 0, 0)
            .setSound(null)
            .setVibrate(longArrayOf())
            
            // ✅ NUEVO: AutoCancel solo en ciertos casos
            .setAutoCancel(false)

        // ✅ NUEVO: Si es Android 12+, usar Material Design 3 colors
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            builder.setColorized(true)
        }

        return builder.build()
    }

    override fun onBind(intent: Intent?): IBinder {
        Log.d(TAG, "🔗 Cliente conectado al servicio")
        return binder
    }

    override fun onDestroy() {
        Log.d(TAG, "💀 Servicio destruido")
        releaseLocks()
        isRunning = false
        monitorHandler.removeCallbacks(monitorRunnable)
        lockRenewalHandler.removeCallbacks(lockRenewalRunnable)
        if (this::oboeAudioRenderer.isInitialized) {
            // ✅ CRÍTICO: Solo detener streams, NO destruir engine (para permitir reconexión)
            // El engine es singleton y se reutiliza en reconexiones
            oboeAudioRenderer.stop()
        }
        super.onDestroy()
    }
}