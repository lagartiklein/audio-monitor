package com.cepalabsfree.fichatech.audiostream

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
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
import android.graphics.Color

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
        notificationManager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
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
            ACTION_DISCONNECT -> {
                stopForegroundService()
            }
        }
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
                "Monitor de audio activo."
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

            // ✅ NUEVO: Programar validación periódica de que la notificación sigue siendo visible
            // Este check garantiza que si la notificación se removió, se reinicia inmediatamente
            monitorHandler.postDelayed(object : Runnable {
                override fun run() {
                    if (isRunning) {
                        try {
                            // Intentar actualizar la notificación para validar que sigue en foreground
                            val notification = createNotification(
                                "🔴 Transmitiendo",
                                "Monitor de audio activo."
                            )
                            notificationManager?.notify(NOTIFICATION_ID, notification)
                        } catch (_: Exception) {
                            Log.w(TAG, "⚠️ Validación: notificación removida, intentando reinstaurar")
                            try {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                                    startForeground(
                                        NOTIFICATION_ID,
                                        createNotification("🔴 Transmitiendo", "Monitor de audio activo."),
                                        ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
                                    )
                                } else {
                                    startForeground(
                                        NOTIFICATION_ID,
                                        createNotification("🔴 Transmitiendo", "Monitor de audio activo.")
                                    )
                                }
                                Log.d(TAG, "✅ Notificación reinstaurada tras validación")
                            } catch (retryError: Exception) {
                                Log.e(TAG, "❌ Error reinstaurando notificación: ${retryError.message}")
                            }
                        }
                        // Programar siguiente validación cada 5 segundos
                        monitorHandler.postDelayed(this, 5000L)
                    }
                }
            }, 5000L)

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
            val wifiManager = getSystemService(WIFI_SERVICE) as WifiManager
            wifiLock = wifiManager.createWifiLock(
                WifiManager.WIFI_MODE_FULL_LOW_LATENCY ,
                "FichaTech:AudioStreamRF"
            ).apply {
                acquire()
                Log.d(TAG, "🔒 WifiLock adquirido")
            }

            // ✅ WakeLock - Mantiene CPU activa (con timeout)
            val powerManager = getSystemService(POWER_SERVICE) as PowerManager
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
     * ✅ NUEVO: Incluye lógica defensiva para reiniciar foreground si fue removido accidentalmente
     */
    fun updateNotification(title: String, message: String) {
        if (!isRunning) {
            Log.d(TAG, "⚠️ Servicio no está corriendo, ignorando actualización de notificación")
            return
        }

        try {
            val notification = createNotification(title, message)

            // ✅ Intentar actualizar notificación
            try {
                notificationManager?.notify(NOTIFICATION_ID, notification)
                Log.d(TAG, "🔔 Notificación actualizada: $title")
            } catch (e: Exception) {
                // Si falla, puede ser porque se removió el foreground
                // Intentar reiniciar foreground
                Log.w(TAG, "⚠️ Error actualizando notificación, intentando reiniciar foreground: ${e.message}")
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                        startForeground(
                            NOTIFICATION_ID,
                            notification,
                            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
                        )
                    } else {
                        startForeground(NOTIFICATION_ID, notification)
                    }
                    Log.d(TAG, "✅ Foreground reiniciado tras error de notificación")
                } catch (retryError: Exception) {
                    Log.e(TAG, "❌ Error reiniciando foreground: ${retryError.message}", retryError)
                }
            }
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
        // Intent para abrir la actividad principal al hacer click en la notificación
        val openIntent = Intent(this, NativeAudioStreamActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPendingIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(message)
            .setSmallIcon(R.drawable.logooficialdemo)
            .setOngoing(true)
            .setContentIntent(openPendingIntent)
            // Fondo negro transparente
            .setColor(Color.BLACK)
            .setColorized(true)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message).setBigContentTitle(title))
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setLights(0, 0, 0)
            .setSound(null)
            .setVibrate(longArrayOf())
            .setAutoCancel(false)
            .setSubText("")

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

    /**
     * ✅ CRÍTICO: Proteger contra deslizar la app de recientes
     * Si el usuario elimina la app de recientes, el sistema llama a onTaskRemoved()
     * Aquí reiniciamos el servicio para mantener la notificación persistente
     */
    override fun onTaskRemoved(rootIntent: Intent?) {
        Log.d(TAG, "⚠️ Aplicación eliminada de recientes - Reiniciando servicio foreground")

        // ✅ Reiniciar el servicio después de un pequeño delay
        // para darle tiempo al sistema de estabilizarse
        Handler(Looper.getMainLooper()).postDelayed({
            if (!isRunning) {
                Log.d(TAG, "🔄 Reiniciando servicio foreground tras onTaskRemoved")
                val restartIntent = Intent(this, AudioStreamForegroundService::class.java).apply {
                    action = ACTION_START
                }
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        startForegroundService(restartIntent)
                    } else {
                        @Suppress("DEPRECATION")
                        startService(restartIntent)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "❌ Error reiniciando servicio: ${e.message}", e)
                }
            }
        }, 500L) // 500ms delay

        super.onTaskRemoved(rootIntent)
    }
}